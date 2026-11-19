# Vetta

Vetta is an API and CLI for an AI-assisted Python code-generation and verification
workflow. Given a task specification, it asks a maker model to produce Python code and
pytest tests, applies deterministic source checks, runs the tests in a restricted Docker
container, and asks a separate checker model to review successful results. The cycle can
repeat with test failures or reviewer feedback until the artifact is approved or the
iteration limit is reached.

> The AST checks are not a security boundary. Do not execute untrusted code on a host
> containing sensitive data. Docker isolation is defense in depth, not a substitute for
> a dedicated hardened worker platform.

## What the system does

The project has two ways to start the same verification workflow:

- **HTTP API:** A client submits a task specification to `POST /v1/runs`. The API creates
  a run record, schedules the work in a FastAPI background task, and returns a run ID.
  Clients can check its status and result with `GET /v1/runs/{run_id}`. These run
  endpoints require a bearer token; `/health` is public.
- **Command-line interface:** `hernness` or `python run_harness.py` starts a run directly
  and prints the final state as JSON.

For each run, the orchestrator performs these steps:

1. **Generate:** The maker model receives the specification and returns a code artifact,
   tests, and its reasoning.
2. **Screen:** A deterministic Python AST check rejects syntax errors and selected
   forbidden imports or built-ins in the generated source.
3. **Test:** If the source passes screening, pytest runs against it in a Docker
   sandbox with networking disabled, resource limits, a timeout, a read-only filesystem,
   and a non-root user.
4. **Review:** Only after tests pass, the checker model reviews the specification, code,
   tests, and test output. It either approves the result or returns critiques.
5. **Retry and report:** When screening, testing, or review fails, the maker can try
   again with the preceding failure or critiques, up to the configured iteration limit.
   The final run state includes the code, tests, sensor report, checker verdict,
   iteration history, and model usage metrics.

The API persists queued, running, completed, or failed run records and results in SQLite.
This is a code-generation and verification pipeline—not a guarantee that generated code
is secure or production-ready. Review its output before using it, and treat both
deterministic checks and model approval as advisory safeguards.

## Requirements

- Python 3.11 or newer
- Docker Engine accessible to the process running Hernness
- An OpenAI API key
- A prebuilt sandbox image (instructions below)

## Local setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` and a long random `HERNESS_API_TOKEN` in `.env`. Build the
restricted test image once:

```powershell
docker build -f docker/sandbox.Dockerfile -t hernness-sandbox:py311 .
```

The sandbox image includes a pinned pytest version. It is not downloaded at run time.

## Run the API

```powershell
hernness-api
```

Alternatively:

```powershell
uvicorn hernness.api:app --host 127.0.0.1 --port 8000
```

The API listens on port 8000. Interactive API documentation is available at
`/docs`; `/health`, `/ready`, and `/metrics` are unauthenticated operational endpoints.
`/health` reports service identity and uptime, `/ready` validates critical dependencies,
and `/metrics` exposes queue counts and runtime telemetry. Requests include an
`X-Request-ID` header for traceability and standardized processing telemetry.
Submit and retrieve runs using a bearer token:

```powershell
$headers = @{ Authorization = "Bearer $env:HERNESS_API_TOKEN" }
$body = @{ task_spec = "Implement a thread-safe LRU cache"; max_iterations = 3 } |
    ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/runs `
    -Headers $headers -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/runs/$($run.id)" -Headers $headers
```

`POST /v1/runs` returns HTTP 202 and a job identifier. The returned job status may
already be complete for short jobs. Job records and results are stored in SQLite at
`HERNESS_DATABASE_PATH` (default: `data/herness.sqlite3`).

## Run the CLI

The `run_harness.py` source-checkout entry point is also available:

```powershell
python run_harness.py
hernness --spec "Implement a thread-safe LRU cache"
hernness --spec-file .\task.txt --max-iterations 3
```

The CLI uses the same OpenAI and Docker configuration as the API and prints the final
run state as JSON.

## React test console

The React interface in `frontend/` lets you connect to the API, submit a task, follow
its status, and inspect generated code, tests, checker feedback, and sandbox output.
Run the API and frontend in separate terminals:

```powershell
# Terminal 1: from the project root, after configuring .env and Docker
hernness-api

# Terminal 2
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. In the console, enter the same
`HERNESS_API_TOKEN` configured for the API, then use **Check API** or submit a run.
During local development, Vite proxies `/health` and `/v1` to `http://127.0.0.1:8000`.
The token remains in browser memory and is not saved to local storage.

To host the frontend on a different domain, set `VITE_API_BASE_URL` to the API's base
URL when building the frontend and add the frontend origin to `HERNESS_CORS_ORIGINS` on
the API, for example:

```text
HERNESS_CORS_ORIGINS=["https://your-console.example"]
```

Only allow frontend origins you control. The bearer token is sent by the browser to the
API; use HTTPS for any deployed frontend or API.

## Configuration

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | Yes | — | OpenAI API credential |
| `HERNESS_API_TOKEN` | Yes for API | — | Bearer token protecting run endpoints |
| `HERNESS_DATABASE_PATH` | No | `data/herness.sqlite3` | SQLite job database |
| `HERNESS_MAKER_MODEL` | No | `gpt-4o` | Code-generation model |
| `HERNESS_CHECKER_MODEL` | No | `o3-mini` | Review model |
| `HERNESS_SANDBOX_IMAGE` | No | `hernness-sandbox:py311` | Locally available sandbox image |
| `HERNESS_SANDBOX_TIMEOUT_SECONDS` | No | `30` | Per-test-run timeout (1–300 seconds) |
| `HERNESS_MAX_ITERATIONS` | No | `4` | Default maximum iterations (1–10) |

## Sandbox controls

Each test run uses a temporary read-only workspace, disabled networking, a read-only
container filesystem, dropped Linux capabilities, `no-new-privileges`, a non-root
container user, memory/CPU/process limits, and a timeout. The container is removed when
execution finishes. Docker must be configured with the required resource and security
features; do not expose an unauthenticated Docker daemon.

## Enterprise-grade operational hardening

The service is ready for more production-oriented deployments thanks to:

- structured request metadata and trace IDs (`X-Request-ID` and `X-Process-Time-ms`)
- explicit operational health endpoints: `/health`, `/ready`, and `/metrics`
- dependency-aware startup validation for OpenAI credentials, API token, and SQLite readiness
- safe internal error handling that avoids leaking sensitive implementation details
- deterministic CORS configuration for approved frontend origins

## Development

```powershell
python -m pytest
```

The API currently runs jobs as FastAPI background tasks in the API process. SQLite
persists job records, but this execution model does not provide durable queue delivery
or horizontal worker scaling. For multi-replica production deployments, move execution
to a separately managed worker queue and use a shared database before scaling out.
