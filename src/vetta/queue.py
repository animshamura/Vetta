from celery import Celery


def create_celery_app(broker_url: str, result_backend: str | None = None) -> Celery:
    app = Celery("vetta", broker=broker_url, backend=result_backend)
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        task_time_limit=900,
        task_soft_time_limit=840,
        broker_transport_options={
            "visibility_timeout": 1800,
        },
        task_default_queue="vetta",
        task_routes={"vetta.execute_run": {"queue": "vetta"}},
    )
    return app
