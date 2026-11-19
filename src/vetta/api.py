import hmac
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import generate_latest
from pydantic import BaseModel, Field, SecretStr

from vetta import __version__
from vetta.config import Settings
from vetta.jobs import JobRecord, JobStore
from vetta.metrics import jobs_submitted, registry
from vetta.orchestrator import run_harness
from vetta.postgres_store import PostgresJobStore
from vetta.queue import create_celery_app
from vetta.schemas import HarnessState

logger = logging.getLogger(__name__)
RunFunction = Callable[[str, int, Settings], HarnessState]
bearer_scheme = HTTPBearer(auto_error=False)


class RunRequest(BaseModel):
    task_spec: str = Field(min_length=1, max_length=20_000)
    max_iterations: int | None = Field(default=None, ge=1, le=10)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    uptime_seconds: float
    database_status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool | str]


class MetricsResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    total_jobs: int
    jobs_by_status: dict[str, int]


def create_app(
    settings: Settings | None = None,
    runner: RunFunction = run_harness,
) -> FastAPI:
    resolved_settings = settings or Settings()
    if resolved_settings.database_url:
        store = PostgresJobStore(resolved_settings.database_url)
    else:
        resolved_settings.ensure_database_directory()
        store = JobStore(resolved_settings.database_path)
    started_at = datetime.now(UTC)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        resolved_settings.ensure_database_directory()
        resolved_settings.validate_credentials()
        store.initialize()
        yield

    app = FastAPI(
        title="Vetta Verification API",
        version=__version__,
        description=(
            "Production-ready task submission and verification API with operational "
            "health, readiness, and performance telemetry."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    app.state.settings = resolved_settings
    app.state.job_store = store
    app.state.started_at = started_at

    submit_attempts: dict[str, list[float]] = {}
    queue_app = None
    if resolved_settings.broker_url:
        queue_app = create_celery_app(
            resolved_settings.broker_url,
            resolved_settings.result_backend,
        )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-ms"] = str(
            round((time.perf_counter() - started) * 1000, 2)
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if resolved_settings.environment.lower() == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception):
        logger.exception("Unhandled API error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected internal error occurred."},
        )

    def authenticate(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer_scheme),
        ],
    ) -> None:
        expected: SecretStr | None = resolved_settings.api_token
        if expected is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API authentication is not configured.",
            )
        if credentials is None or not hmac.compare_digest(
            credentials.credentials,
            expected.get_secret_value(),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid bearer token is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def process_job(job_id: str, payload: RunRequest) -> None:
        store.update(job_id, "running")
        try:
            max_iterations = payload.max_iterations or resolved_settings.max_iterations
            result = runner(payload.task_spec, max_iterations, resolved_settings)
            store.update(job_id, "completed", result=result)
        except Exception:
            logger.exception("Harness job %s failed", job_id)
            store.update(
                job_id,
                "failed",
                error="The harness run failed. See service logs for details.",
            )

    @app.get("/health", response_model=HealthResponse, tags=["operations"])
    def health() -> HealthResponse:
        database_status = store.ping()["database"]
        uptime_seconds = (datetime.now(UTC) - started_at).total_seconds()
        return HealthResponse(
            status="ok",
            service=resolved_settings.app_name,
            version=__version__,
            environment=resolved_settings.environment,
            uptime_seconds=uptime_seconds,
            database_status=database_status,
        )

    @app.get("/ready", response_model=ReadinessResponse, tags=["operations"])
    def readiness() -> ReadinessResponse:
        ping = store.ping()
        checks = {
            "database": ping["healthy"],
            "api_token_configured": resolved_settings.api_token is not None,
            "openai_credentials_configured": resolved_settings.openai_api_key is not None,
        }
        return ReadinessResponse(
            status="ready" if all(value is True for value in checks.values()) else "degraded",
            checks=checks,
        )

    @app.get("/metrics", response_model=MetricsResponse, tags=["operations"])
    def metrics() -> MetricsResponse:
        summary = store.summary()
        uptime_seconds = (datetime.now(UTC) - started_at).total_seconds()
        return MetricsResponse(
            status="ok",
            version=__version__,
            uptime_seconds=uptime_seconds,
            total_jobs=summary["total"],
            jobs_by_status={
                key: summary.get(key, 0)
                for key in ("queued", "running", "completed", "failed")
            },
        )

    @app.get("/metrics/prometheus", include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(
            content=generate_latest(registry),
            media_type="text/plain; version=0.0.4",
        )

    @app.post(
        "/v1/runs",
        response_model=JobRecord,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["runs"],
        dependencies=[Depends(authenticate)],
    )
    def submit_run(
        payload: RunRequest,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> JobRecord:
        now = time.monotonic()
        client_ip = request.client.host if request.client else "unknown"
        if resolved_settings.trust_proxy:
            forwarded = request.headers.get("X-Forwarded-For", client_ip)
            client_ip = forwarded.split(",", 1)[0].strip()
        recent = [
            timestamp
            for timestamp in submit_attempts.get(client_ip, [])
            if now - timestamp < 60
        ]
        if len(recent) >= resolved_settings.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Submission rate limit exceeded. Try again later.",
            )
        recent.append(now)
        submit_attempts[client_ip] = recent
        job = store.create(str(uuid4()))
        jobs_submitted.inc()
        if queue_app is not None:
            queue_app.send_task(
                "vetta.execute_run",
                args=[
                    job.id,
                    payload.task_spec,
                    payload.max_iterations or resolved_settings.max_iterations,
                ],
                task_id=job.id,
                retry=True,
            )
        else:
            background_tasks.add_task(process_job, job.id, payload)
        return job

    @app.get(
        "/v1/runs/{job_id}",
        response_model=JobRecord,
        tags=["runs"],
        dependencies=[Depends(authenticate)],
    )
    def get_run(job_id: str) -> JobRecord:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
        return record

    return app


app = create_app()


def main() -> None:
    import uvicorn

    Settings().validate_credentials()
    uvicorn.run("vetta.api:app", host="0.0.0.0", port=8000)
