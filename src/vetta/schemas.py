from typing import Literal

from pydantic import BaseModel, Field


class SensorReport(BaseModel):
    passed: bool
    ast_valid: bool
    security_violations: list[str] = Field(default_factory=list)
    test_passed: bool
    test_output: str = ""


class CritiqueItem(BaseModel):
    severity: Literal["CRITICAL", "MAJOR", "MINOR"]
    category: Literal["LOGIC", "SECURITY", "EDGE_CASE", "SPEC_MISMATCH"]
    description: str
    suggested_fix: str


class EvaluationVerdict(BaseModel):
    approved: bool
    confidence_score: float = Field(ge=0.0, le=1.0)
    critiques: list[CritiqueItem] = Field(default_factory=list)
    summary: str


class HarnessMetrics(BaseModel):
    total_tokens_used: int = 0
    maker_calls: int = 0
    checker_calls: int = 0
    duration_seconds: float = 0.0


class HarnessState(BaseModel):
    task_spec: str
    max_iterations: int = 4
    current_iteration: int = 0
    current_code: str = ""
    current_tests: str = ""
    last_sensor_report: SensorReport | None = None
    last_verdict: EvaluationVerdict | None = None
    history: list[str] = Field(default_factory=list)
    status: Literal["RUNNING", "APPROVED", "FAILED_MAX_RETRIES"] = "RUNNING"
    metrics: HarnessMetrics = Field(default_factory=HarnessMetrics)


class MakerArtifact(BaseModel):
    code: str
    unit_tests: str
    reasoning: str
