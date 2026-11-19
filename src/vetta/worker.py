import structlog

from vetta.config import Settings
from vetta.jobs import JobStore
from vetta.metrics import jobs_completed, jobs_failed
from vetta.orchestrator import run_harness
from vetta.postgres_store import PostgresJobStore
from vetta.queue import create_celery_app

logger = structlog.get_logger()
settings = Settings()

if settings.database_url:
    store = PostgresJobStore(settings.database_url)
else:
    settings.ensure_database_directory()
    store = JobStore(settings.database_path)

store.initialize()

if not settings.broker_url:
    raise RuntimeError("VETTA_BROKER_URL must be configured for worker mode.")

celery_app = create_celery_app(settings.broker_url, settings.result_backend)


@celery_app.task(name="vetta.execute_run", bind=True)
def execute_run(self, job_id: str, task_spec: str, max_iterations: int) -> None:
    logger.info("vetta.run.started", job_id=job_id)
    store.update(job_id, "running")
    try:
        result = run_harness(task_spec, max_iterations, settings)
        store.update(job_id, "completed", result=result)
        jobs_completed.inc()
        logger.info("vetta.run.completed", job_id=job_id)
    except Exception:
        logger.exception("vetta.run.failed", job_id=job_id)
        jobs_failed.inc()
        store.update(
            job_id,
            "failed",
            error="The harness run failed. See service logs for details.",
        )
        raise


def main() -> None:
    celery_app.worker_main([
        "worker",
        "--loglevel=INFO",
        "--concurrency=2",
        "--queues=vetta",
    ])
