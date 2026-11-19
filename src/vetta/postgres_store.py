from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import JSON, DateTime, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from vetta.jobs import JobRecord
from vetta.schemas import HarnessState

JobStatus = Literal["queued", "running", "completed", "failed"]


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class PostgresJobStore:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self.engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def ping(self) -> dict[str, str | bool]:
        with Session(self.engine) as session:
            session.execute(select(1))
        return {"database": "ok", "healthy": True, "details": "PostgreSQL reachable"}

    def summary(self) -> dict[str, int]:
        with Session(self.engine) as session:
            summary = {"queued": 0, "running": 0, "completed": 0, "failed": 0, "total": 0}
            for status in ("queued", "running", "completed", "failed"):
                count = len(session.scalars(select(Job).where(Job.status == status)).all())
                summary[status] = count
                summary["total"] += count
            return summary

    def create(self, job_id: str) -> JobRecord:
        now = datetime.now(UTC)
        with Session(self.engine) as session:
            session.add(Job(id=job_id, status="queued", created_at=now, updated_at=now))
            session.commit()
        return JobRecord(id=job_id, status="queued", created_at=now, updated_at=now)

    def update(
        self,
        job_id: str,
        status: JobStatus,
        result: HarnessState | None = None,
        error: str | None = None,
    ) -> None:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(f"Unknown job: {job_id}")
            job.status = status
            job.updated_at = datetime.now(UTC)
            job.result = result.model_dump(mode="json") if result is not None else None
            job.error = error
            session.commit()

    def get(self, job_id: str) -> JobRecord | None:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return None
            result = HarnessState.model_validate(job.result) if job.result else None
            return JobRecord(
                id=job.id,
                status=job.status,
                created_at=job.created_at,
                updated_at=job.updated_at,
                result=result,
                error=job.error,
            )
