import hmac
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, SecretStr

from hernness.config import Settings
from hernness.jobs import JobRecord, JobStore
from hernness.orchestrator import run_harness
from hernness.schemas import HarnessState

logger = logging.getLogger(__name__)
RunFunction = Callable[[str, int, Settings], HarnessState]
bearer_scheme = HTTPBearer(auto_error=False)


class RunRequest(BaseModel):
    task_spec: str = Field(min_length=1, max_length=20_000)
    max_iterations: int | None = Field(default=None, ge=1, le=10)


class HealthResponse(BaseModel):
    status: str


def create_app(
    settings: Settings | None = None,
    runner: RunFunction = run_harness,
) -> FastAPI:
    resolved_settings = settings or Settings()
    store = JobStore(resolved_settings.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        resolved_settings.validate_credentials()
        store.initialize()
        yield

    app = FastAPI(
        title="Hernness Verification API",
        version="1.0.0",
        description="Submit code-generation tasks and retrieve their verification results.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.state.settings = resolved_settings
    app.state.job_store = store

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
        return HealthResponse(status="ok")

    @app.post(
        "/v1/runs",
        response_model=JobRecord,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["runs"],
        dependencies=[Depends(authenticate)],
    )
    def submit_run(payload: RunRequest, background_tasks: BackgroundTasks) -> JobRecord:
        job = store.create(str(uuid4()))
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
    uvicorn.run("hernness.api:app", host="0.0.0.0", port=8000)
