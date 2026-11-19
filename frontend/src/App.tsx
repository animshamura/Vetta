import { useEffect, useState, type FormEvent } from 'react'
import './App.css'

type JobStatus = 'queued' | 'running' | 'completed' | 'failed'
type ConnectionStatus = 'unknown' | 'checking' | 'online' | 'offline'

interface SensorReport {
  passed: boolean
  ast_valid: boolean
  security_violations: string[]
  test_passed: boolean
  test_output: string
}

interface Critique {
  severity: 'CRITICAL' | 'MAJOR' | 'MINOR'
  category: 'LOGIC' | 'SECURITY' | 'EDGE_CASE' | 'SPEC_MISMATCH'
  description: string
  suggested_fix: string
}

interface HarnessResult {
  task_spec: string
  max_iterations: number
  current_iteration: number
  current_code: string
  current_tests: string
  last_sensor_report: SensorReport | null
  last_verdict: {
    approved: boolean
    confidence_score: number
    critiques: Critique[]
    summary: string
  } | null
  history: string[]
  status: 'RUNNING' | 'APPROVED' | 'FAILED_MAX_RETRIES'
  metrics: {
    total_tokens_used: number
    maker_calls: number
    checker_calls: number
    duration_seconds: number
  }
}

interface Job {
  id: string
  status: JobStatus
  created_at: string
  updated_at: string
  result: HarnessResult | null
  error: string | null
}

const initialSpec = `Implement an enterprise-grade ThreadSafeLRUCache in Python:
- __init__(self, capacity: int) with validation (capacity > 0).
- get(self, key) -> Any: returns the value or raises KeyError if missing.
- put(self, key, value) -> None: inserts or updates a key, evicting the oldest item at capacity.
- Must be thread-safe using threading.Lock.
- Both get and put should run in O(1) time.`

const initialApiUrl = import.meta.env.VITE_API_BASE_URL ?? ''

function apiUrl(base: string, path: string): string {
  return `${base.trim().replace(/\/+$/, '')}${path}`
}

async function responseError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string'
    ) {
      return body.detail
    }
  } catch {
    // Fall back to the HTTP status when the server does not return JSON.
  }
  return `Request failed (${response.status} ${response.statusText}).`
}

function App() {
  const [apiBase, setApiBase] = useState(initialApiUrl)
  const [token, setToken] = useState('')
  const [spec, setSpec] = useState(initialSpec)
  const [maxIterations, setMaxIterations] = useState(3)
  const [connection, setConnection] = useState<ConnectionStatus>('unknown')
  const [job, setJob] = useState<Job | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [copyFeedback, setCopyFeedback] = useState('')
  const activeJobId = job?.id
  const activeJobStatus = job?.status

  useEffect(() => {
    if (
      !activeJobId ||
      activeJobStatus === 'completed' ||
      activeJobStatus === 'failed'
    ) return

    let active = true
    let timeoutId: number | undefined

    const poll = async () => {
      try {
        const response = await fetch(apiUrl(apiBase, `/v1/runs/${activeJobId}`), {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok) throw new Error(await responseError(response))

        const updatedJob = (await response.json()) as Job
        if (!active) return
        setJob(updatedJob)
        if (updatedJob.status === 'completed' || updatedJob.status === 'failed') return
        timeoutId = window.setTimeout(poll, 1500)
      } catch (pollError) {
        if (!active) return
        setError(pollError instanceof Error ? pollError.message : 'Could not retrieve run status.')
      }
    }

    timeoutId = window.setTimeout(poll, 800)
    return () => {
      active = false
      if (timeoutId !== undefined) window.clearTimeout(timeoutId)
    }
  }, [activeJobId, activeJobStatus, apiBase, token])

  async function checkConnection() {
    setConnection('checking')
    setError('')
    try {
      const response = await fetch(apiUrl(apiBase, '/health'))
      if (!response.ok) throw new Error(await responseError(response))
      setConnection('online')
    } catch (connectionError) {
      setConnection('offline')
      setError(
        connectionError instanceof Error
          ? connectionError.message
          : 'Unable to reach the API.',
      )
    }
  }

  async function submitRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setJob(null)
    setIsSubmitting(true)

    try {
      const response = await fetch(apiUrl(apiBase, '/v1/runs'), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ task_spec: spec, max_iterations: maxIterations }),
      })
      if (!response.ok) throw new Error(await responseError(response))
      setJob((await response.json()) as Job)
      setConnection('online')
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to submit run.')
      setConnection('offline')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function copyText(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopyFeedback(`${label} copied`)
      window.setTimeout(() => setCopyFeedback(''), 1800)
    } catch {
      setError(`Could not copy ${label.toLowerCase()}.`)
    }
  }

  function downloadText(filename: string, text: string) {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  }

  function resetConsole() {
    setJob(null)
    setError('')
    setCopyFeedback('')
  }

  const result = job?.result
  const runApproved = result?.status === 'APPROVED'

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Vetta home">
          <span className="brand-mark" aria-hidden="true">V</span>
          <span>vetta<span className="brand-period">.</span></span>
        </a>
        <div className="topbar-right">
          <span className={`connection-indicator ${connection}`} aria-live="polite">
            <span className="connection-dot" />
            {connection === 'online'
              ? 'API connected'
              : connection === 'checking'
                ? 'Checking API'
                : connection === 'offline'
                  ? 'API unavailable'
                  : 'Not connected'}
          </span>
          <span className="environment-tag">TEST CONSOLE</span>
        </div>
      </header>

      <section className="hero">
        <div className="eyebrow"><span className="eyebrow-line" />AI CODE VERIFICATION</div>
        <h1>Build it. Test it.<br /><span>Challenge it.</span></h1>
        <p>Run a maker-checker cycle and inspect every step of the verification pipeline.</p>
      </section>

      <section className="overview-grid" aria-label="Verification overview">
        <div className="overview-card">
          <span className="overview-label">PIPELINE</span>
          <strong>Maker → Sandbox → Reviewer</strong>
          <small>Deterministic checks before execution.</small>
        </div>
        <div className="overview-card emphasis">
          <span className="overview-label">THREAT MODEL</span>
          <strong>Security-first validation</strong>
          <small>AST + import guard + sandbox execution.</small>
        </div>
        <div className="overview-card">
          <span className="overview-label">OPERATIONS</span>
          <strong>Production telemetry</strong>
          <small>Health, readiness, and queue metrics.</small>
        </div>
      </section>

      <section className="connection-panel" aria-label="API connection settings">
        <div className="connection-copy">
          <span className="section-index">01</span>
          <div>
            <h2>Connect to your API</h2>
            <p>Your token stays in this browser session and is never saved.</p>
          </div>
        </div>
        <div className="connection-fields">
          <label className="field">
            <span>API base URL</span>
            <input
              value={apiBase}
              onChange={(event) => {
                setApiBase(event.target.value)
                setConnection('unknown')
              }}
              placeholder="Local dev uses the Vite proxy"
              type="url"
              autoComplete="url"
            />
          </label>
          <label className="field">
            <span>Bearer token</span>
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="VETTA_API_TOKEN"
              type="password"
              autoComplete="off"
            />
          </label>
          <button
            className="button button-secondary connect-button"
            type="button"
            onClick={checkConnection}
            disabled={connection === 'checking'}
          >
            {connection === 'checking' ? 'Checking…' : 'Check API'}
          </button>
        </div>
      </section>

      <div className="workspace">
        <section className="request-card">
          <div className="card-heading">
            <div>
              <span className="section-index">02 / NEW RUN</span>
              <h2>Describe the task</h2>
            </div>
            <span className="request-method">POST /v1/runs</span>
          </div>

          <form onSubmit={submitRun}>
            <label className="field spec-field">
              <span>Task specification <span className="required-mark">*</span></span>
              <textarea
                value={spec}
                onChange={(event) => setSpec(event.target.value)}
                maxLength={20_000}
                required
                rows={11}
                placeholder="Describe the Python code you want the maker to implement…"
              />
              <span className="field-hint">{spec.length.toLocaleString()} / 20,000 characters</span>
            </label>

            <label className="field iteration-field">
              <span>Maximum iterations</span>
              <div className="iteration-control">
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={maxIterations}
                  onChange={(event) => setMaxIterations(Number(event.target.value))}
                />
                <output>{maxIterations}</output>
              </div>
              <span className="field-hint">The maker can revise its work after failures or review feedback.</span>
            </label>

            <button
              className="button button-primary submit-button"
              type="submit"
              disabled={isSubmitting || connection !== 'online' || !token.trim() || !spec.trim()}
            >
              <span>{isSubmitting ? 'Submitting run…' : 'Start verification run'}</span>
              {!isSubmitting && <span className="button-arrow" aria-hidden="true">↗</span>}
            </button>
            {!token.trim() && <p className="form-note">Enter your bearer token to enable a run.</p>}
            {token.trim() && connection !== 'online' && <p className="form-note">Check the API connection before starting a run.</p>}
          </form>
        </section>

        <section className="result-card" aria-live="polite">
          <div className="card-heading result-heading">
            <div>
              <span className="section-index">03 / RUN OUTPUT</span>
              <h2>Verification result</h2>
            </div>
            <div className="result-actions">
              {copyFeedback && <span className="copy-feedback" role="status">{copyFeedback}</span>}
              {job && <button className="button button-secondary compact-button" type="button" onClick={resetConsole}>New run</button>}
              {job && <StatusBadge status={job.status} />}
            </div>
          </div>

          {error && (
            <div className="error-banner" role="alert">
              <span className="error-icon">!</span>
              <div><strong>Request error</strong><p>{error}</p></div>
            </div>
          )}

          {job && result && (
            <div className="status-rail" aria-label="Run diagnostics">
              <div className="status-pill">
                <span className="status-swatch" />
                <strong>{result.status}</strong>
              </div>
              <div className="status-pill muted">
                <span className="status-swatch neutral" />
                <strong>{result.last_sensor_report?.test_passed ? 'Sandbox pass' : 'Sandbox review'}</strong>
              </div>
              <div className="status-pill muted">
                <span className="status-swatch neutral" />
                <strong>{result.last_verdict?.approved ? 'Approved by checker' : 'Awaiting approval'}</strong>
              </div>
            </div>
          )}

          {!job ? (
            <div className="empty-state">
              <div className="empty-orbit" aria-hidden="true">
                <span className="orbit-center">V</span>
                <span className="orbit-node node-one" />
                <span className="orbit-node node-two" />
                <span className="orbit-node node-three" />
              </div>
              <h3>Ready when you are</h3>
              <p>Submit a task to watch generation, testing, and review unfold here.</p>
              <div className="pipeline-preview">
                <span>MAKER</span><i /><span>TESTS</span><i /><span>CHECKER</span>
              </div>
            </div>
          ) : (
            <div className="run-output">
              <div className="job-meta">
                <span>RUN ID</span>
                <code title={job.id}>{job.id}</code>
              </div>
              {job.status === 'queued' || job.status === 'running' ? (
                <div className="progress-state">
                  <span className="loader" />
                  <div>
                    <strong>{job.status === 'queued' ? 'Run queued' : 'Verification in progress'}</strong>
                    <p>The maker, sandbox, and checker are working through the pipeline.</p>
                  </div>
                </div>
              ) : job.error ? (
                <div className="error-banner job-error" role="alert">
                  <span className="error-icon">!</span>
                  <div><strong>Run failed</strong><p>{job.error}</p></div>
                </div>
              ) : result ? (
                <>
                  <div className={`verdict-card ${runApproved ? 'approved' : 'rejected'}`}>
                    <span className="verdict-icon" aria-hidden="true">{runApproved ? '✓' : '×'}</span>
                    <div className="verdict-copy">
                      <span className="verdict-label">PIPELINE {runApproved ? 'APPROVED' : 'NOT APPROVED'}</span>
                      <strong>{result.status === 'APPROVED' ? 'Ready for your review' : 'Iteration limit reached'}</strong>
                      <p>{result.last_verdict?.summary ?? 'No checker verdict was returned.'}</p>
                    </div>
                    {result.last_verdict && (
                      <div className="confidence">
                        <strong>{Math.round(result.last_verdict.confidence_score * 100)}%</strong>
                        <span>confidence</span>
                      </div>
                    )}
                  </div>

                  <div className="metric-grid">
                    <Metric label="ITERATIONS" value={`${result.current_iteration} / ${result.max_iterations}`} />
                    <Metric label="TOKENS" value={result.metrics.total_tokens_used.toLocaleString()} />
                    <Metric label="DURATION" value={`${result.metrics.duration_seconds.toFixed(1)}s`} />
                  </div>

                  <div className="insight-grid">
                    <InsightCard
                      title="AST Security"
                      value={result.last_sensor_report?.ast_valid ? 'PASS' : 'BLOCKED'}
                      tone={result.last_sensor_report?.ast_valid ? 'good' : 'warn'}
                    />
                    <InsightCard
                      title="Dangerous Calls"
                      value={String(result.last_sensor_report?.security_violations.length ?? 0)}
                      tone={(result.last_sensor_report?.security_violations.length ?? 0) === 0 ? 'good' : 'warn'}
                    />
                    <InsightCard
                      title="Reviewer" 
                      value={result.last_verdict?.approved ? 'APPROVED' : 'REVIEW'}
                      tone={result.last_verdict?.approved ? 'good' : 'neutral'}
                    />
                  </div>

                  {result.last_sensor_report && (
                    <div className="sensor-summary">
                      <div className="subsection-title">DETERMINISTIC CHECKS</div>
                      <div className="sensor-list">
                        <Sensor label="Syntax check" passed={result.last_sensor_report.ast_valid} />
                        <Sensor
                          label="Forbidden source patterns"
                          passed={result.last_sensor_report.security_violations.length === 0}
                        />
                        <Sensor label="Sandbox tests" passed={result.last_sensor_report.test_passed} />
                      </div>
                      {result.last_sensor_report.security_violations.length > 0 && (
                        <ul className="violation-list">
                          {result.last_sensor_report.security_violations.map((violation) => (
                            <li key={violation}>{violation}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {result.last_verdict?.critiques.map((critique, index) => (
                    <article className="critique" key={`${critique.category}-${index}`}>
                      <div className="critique-meta">
                        <span className={`severity ${critique.severity.toLowerCase()}`}>
                          {critique.severity}
                        </span>
                        <span>{critique.category.replaceAll('_', ' ')}</span>
                      </div>
                      <p>{critique.description}</p>
                      <small>Suggested fix: {critique.suggested_fix}</small>
                    </article>
                  ))}

                  <div className="artifact-list">
                    {result.current_code && (
                      <details className="artifact">
                        <summary>
                          <span>Generated Python code</span>
                          <span className="artifact-actions">
                            <button type="button" onClick={(event) => { event.preventDefault(); void copyText(result.current_code, 'Python code') }}>Copy</button>
                            <button type="button" onClick={(event) => { event.preventDefault(); downloadText('solution.py', result.current_code) }}>Download</button>
                            <span className="artifact-type">.py</span>
                          </span>
                        </summary>
                        <pre><code>{result.current_code}</code></pre>
                      </details>
                    )}
                    {result.current_tests && (
                      <details className="artifact">
                        <summary>
                          <span>Generated pytest tests</span>
                          <span className="artifact-actions">
                            <button type="button" onClick={(event) => { event.preventDefault(); void copyText(result.current_tests, 'Pytest tests') }}>Copy</button>
                            <button type="button" onClick={(event) => { event.preventDefault(); downloadText('test_solution.py', result.current_tests) }}>Download</button>
                            <span className="artifact-type">TESTS</span>
                          </span>
                        </summary>
                        <pre><code>{result.current_tests}</code></pre>
                      </details>
                    )}
                    {result.last_sensor_report?.test_output && (
                      <details className="artifact">
                        <summary><span>Sandbox output</span><span className="artifact-type">LOG</span></summary>
                        <pre><code>{result.last_sensor_report.test_output}</code></pre>
                      </details>
                    )}
                  </div>

                  {result.history.length > 0 && (
                    <div className="history">
                      <div className="subsection-title">RUN HISTORY</div>
                      {result.history.map((entry, index) => (
                        <div className="history-row" key={`${entry}-${index}`}>
                          <span className="history-dot" />{entry}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : null}
            </div>
          )}
        </section>
      </div>

      <footer className="footer">
        <span>VETTA <span className="footer-dot">/</span> VERIFICATION WORKBENCH</span>
        <span>Generated code is untrusted. Review before use.</span>
      </footer>
    </main>
  )
}

function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`status-badge ${status}`}><span />{status}</span>
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>
}

function InsightCard({
  title,
  value,
  tone,
}: {
  title: string
  value: string
  tone: 'good' | 'warn' | 'neutral'
}) {
  return (
    <div className={`insight-card ${tone}`}>
      <small>{title}</small>
      <strong>{value}</strong>
    </div>
  )
}

function Sensor({ label, passed }: { label: string; passed: boolean }) {
  return (
    <div className="sensor-row">
      <span className={`sensor-check ${passed ? 'passed' : 'failed'}`}>{passed ? '✓' : '×'}</span>
      <span>{label}</span>
      <strong>{passed ? 'PASS' : 'FAIL'}</strong>
    </div>
  )
}

export default App
