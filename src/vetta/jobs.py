import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from vetta.schemas import HarnessState

JobStatus = Literal["queued", "running", "completed", "failed"]


class JobRecord(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    result: HarnessState | None = None
    error: str | None = None


class JobStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path, timeout=10) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT
                )
                """
            )

    def ping(self) -> dict[str, str | bool]:
        with sqlite3.connect(self.database_path, timeout=10) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
        healthy = quick_check is not None and quick_check[0] == "ok"
        return {
            "database": "ok" if healthy else "degraded",
            "healthy": healthy,
            "details": quick_check[0] if quick_check else "Database check unavailable",
        }

    def summary(self) -> dict[str, int]:
        with sqlite3.connect(self.database_path, timeout=10) as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status"
            ).fetchall()
        summary = {"queued": 0, "running": 0, "completed": 0, "failed": 0, "total": 0}
        for status, count in rows:
            summary[status] = count
            summary["total"] += count
        return summary

    def create(self, job_id: str) -> JobRecord:
        now = datetime.now(UTC)
        with sqlite3.connect(self.database_path, timeout=10) as connection:
            connection.execute(
                "INSERT INTO jobs (id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (job_id, "queued", now.isoformat(), now.isoformat()),
            )
        return JobRecord(id=job_id, status="queued", created_at=now, updated_at=now)

    def update(
        self,
        job_id: str,
        status: JobStatus,
        result: HarnessState | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        result_json = result.model_dump_json() if result is not None else None
        with sqlite3.connect(self.database_path, timeout=10) as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status = ?, updated_at = ?, result_json = ?, error = ?
                WHERE id = ?
                """,
                (status, now.isoformat(), result_json, error, job_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown job: {job_id}")

    def get(self, job_id: str) -> JobRecord | None:
        with sqlite3.connect(self.database_path, timeout=10) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None

        result_json = row["result_json"]
        result = HarnessState.model_validate_json(result_json) if result_json else None
        return JobRecord(
            id=row["id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result=result,
            error=row["error"],
        )
