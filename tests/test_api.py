from fastapi.testclient import TestClient
from pydantic import SecretStr

from vetta.api import create_app
from vetta.config import Settings
from vetta.schemas import HarnessState


def make_settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key=SecretStr("test-openai-key"),
        api_token=SecretStr("test-api-token"),
        database_path=tmp_path / "jobs.sqlite3",
    )


def test_run_submission_persists_result_and_requires_auth(tmp_path) -> None:
    settings = make_settings(tmp_path)

    def runner(task_spec: str, max_iterations: int, _: Settings) -> HarnessState:
        return HarnessState(
            task_spec=task_spec,
            max_iterations=max_iterations,
            current_iteration=1,
            status="APPROVED",
        )

    with TestClient(create_app(settings, runner)) as client:
        unauthorized = client.post("/v1/runs", json={"task_spec": "write a function"})
        assert unauthorized.status_code == 401

        response = client.post(
            "/v1/runs",
            headers={"Authorization": "Bearer test-api-token"},
            json={"task_spec": "write a function", "max_iterations": 2},
        )

        assert response.status_code == 202
        job = response.json()
        assert job["status"] == "queued"

        result_response = client.get(
            f"/v1/runs/{job['id']}",
            headers={"Authorization": "Bearer test-api-token"},
        )

    assert result_response.status_code == 200
    record = result_response.json()
    assert record["status"] == "completed"
    assert record["result"]["status"] == "APPROVED"
    assert record["result"]["max_iterations"] == 2


def test_unknown_run_returns_not_found(tmp_path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get(
            "/v1/runs/missing",
            headers={"Authorization": "Bearer test-api-token"},
        )

    assert response.status_code == 404


def test_failed_runner_is_reported_without_leaking_exception_details(tmp_path) -> None:
    def runner(_: str, __: int, ___: Settings) -> HarnessState:
        raise RuntimeError("sensitive internal detail")

    with TestClient(create_app(make_settings(tmp_path), runner)) as client:
        response = client.post(
            "/v1/runs",
            headers={"Authorization": "Bearer test-api-token"},
            json={"task_spec": "write a function"},
        )
        job_id = response.json()["id"]
        result_response = client.get(
            f"/v1/runs/{job_id}",
            headers={"Authorization": "Bearer test-api-token"},
        )

    assert response.status_code == 202
    assert result_response.status_code == 200
    assert result_response.json()["status"] == "failed"
    assert "sensitive internal detail" not in result_response.text


def test_health_endpoint_does_not_require_auth(tmp_path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "vetta"
    assert payload["version"] == "1.0.0"
    assert payload["database_status"] == "ok"


def test_readiness_and_metrics_endpoints_report_service_state(tmp_path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        readiness = client.get("/ready")
        metrics = client.get("/metrics")

    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["status"] == "ok"
    assert payload["jobs_by_status"]["queued"] == 0
    assert payload["jobs_by_status"]["failed"] == 0
    assert payload["version"] == "1.0.0"


def test_configured_frontend_origin_can_make_authenticated_requests(tmp_path) -> None:
    settings = make_settings(tmp_path)
    settings.cors_origins = ["https://console.example.com"]

    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/v1/runs",
            headers={
                "Origin": "https://console.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://console.example.com"


def test_security_headers_are_added(tmp_path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_run_submission_is_rate_limited(tmp_path) -> None:
    settings = make_settings(tmp_path)
    settings.requests_per_minute = 2

    with TestClient(create_app(settings)) as client:
        headers = {"Authorization": "Bearer test-api-token"}
        first = client.post("/v1/runs", headers=headers, json={"task_spec": "first"})
        second = client.post("/v1/runs", headers=headers, json={"task_spec": "second"})
        limited = client.post("/v1/runs", headers=headers, json={"task_spec": "third"})

    assert first.status_code == 202
    assert second.status_code == 202
    assert limited.status_code == 429
