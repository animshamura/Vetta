from prometheus_client import CollectorRegistry, Counter, Gauge

registry = CollectorRegistry()
jobs_submitted = Counter(
    "vetta_jobs_submitted_total",
    "Number of verification jobs submitted",
    registry=registry,
)
jobs_completed = Counter(
    "vetta_jobs_completed_total",
    "Number of verification jobs completed",
    registry=registry,
)
jobs_failed = Counter(
    "vetta_jobs_failed_total",
    "Number of verification jobs failed",
    registry=registry,
)
sandbox_containers = Gauge(
    "vetta_sandbox_containers",
    "Sandbox containers currently managed by this process",
    registry=registry,
)
