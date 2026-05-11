import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createJob,
  exportPdfUrl,
  getFileColumns,
  getJob,
  getOpenaiModelOptions,
  reportUrl,
  uploadFile,
  type Job,
  type UploadedFile,
} from './api'
import './App.css'

function App() {
  const [fileA, setFileA] = useState<UploadedFile | null>(null)
  const [fileB, setFileB] = useState<UploadedFile | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [keyColumns, setKeyColumns] = useState<string[]>([])
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [selectedNarrative, setSelectedNarrative] = useState<string[]>([])
  const [columnsError, setColumnsError] = useState<string | null>(null)
  const [llmModels, setLlmModels] = useState<string[]>(['gpt-4o-mini'])
  const [selectedOpenaiModel, setSelectedOpenaiModel] = useState('gpt-4o-mini')
  const [toast, setToast] = useState<string | null>(null)
  const [clock, setClock] = useState(() => new Date())

  const showToast = useCallback((message: string) => {
    setToast(message)
  }, [])

  useEffect(() => {
    if (!toast) return
    const id = window.setTimeout(() => setToast(null), 9000)
    return () => window.clearTimeout(id)
  }, [toast])

  useEffect(() => {
    let cancelled = false
    void getOpenaiModelOptions()
      .then((opts) => {
        if (cancelled) return
        setLlmModels(opts.models)
        setSelectedOpenaiModel(opts.default)
      })
      .catch(() => {
        /* keep built-in fallback list */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const timeZoneIana = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, [])
  const timeZoneShort = useMemo(() => {
    const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(clock)
    return parts.find((p) => p.type === 'timeZoneName')?.value ?? ''
  }, [clock])

  useEffect(() => {
    const id = window.setInterval(() => setClock(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const files = useMemo(
    () => [fileA, fileB].filter((f): f is UploadedFile => f != null),
    [fileA, fileB],
  )

  const needsKeyFields = fileA != null && fileB != null

  useEffect(() => {
    if (!needsKeyFields) {
      setKeyColumns([])
      setSelectedKeys([])
      setSelectedNarrative([])
      setColumnsError(null)
      return
    }
    let cancelled = false
    setColumnsError(null)
    ;(async () => {
      try {
        const res = await getFileColumns(fileA!.id)
        if (cancelled) return
        setKeyColumns(res.columns)
        setSelectedKeys([])
        setSelectedNarrative([])
      } catch (e) {
        if (!cancelled) {
          setKeyColumns([])
          setColumnsError(null)
          showToast(e instanceof Error ? e.message : String(e))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [needsKeyFields, fileA, showToast])

  const toggleKey = useCallback((name: string) => {
    setSelectedKeys((prev) =>
      prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name],
    )
  }, [])

  const toggleNarrative = useCallback((name: string) => {
    setSelectedNarrative((prev) =>
      prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name],
    )
  }, [])

  const onPickSlot = async (slot: 'a' | 'b', list: FileList | null) => {
    const raw = list?.[0]
    if (!raw) return
    setError(null)
    setBusy(true)
    try {
      const uploaded = await uploadFile(raw)
      if (slot === 'a') {
        setFileA(uploaded)
      } else {
        setFileB(uploaded)
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const canRun = useMemo(() => {
    if (files.length < 2) return false
    if (files.length !== 2) return false
    return (
      selectedKeys.length >= 1 &&
      selectedNarrative.length >= 1 &&
      keyColumns.length >= 1 &&
      !columnsError
    )
  }, [
    files.length,
    selectedKeys.length,
    selectedNarrative.length,
    keyColumns.length,
    columnsError,
  ])

  const runCompare = async () => {
    if (files.length < 2) {
      setError('Select at least two Excel files.')
      return
    }
    if (fileA == null || fileB == null) {
      setError('Choose both File A and File B.')
      return
    }
    if (selectedKeys.length < 1) {
      setError('Select at least one column as the record key.')
      return
    }
    if (selectedNarrative.length < 1) {
      setError('Select at least one column to drive the report wording (narrative labels).')
      return
    }
    setError(null)
    setBusy(true)
    try {
      const j = await createJob(files.map((f) => f.id), selectedKeys, selectedNarrative, selectedOpenaiModel)
      setJob(j)
    } catch (e) {
      showToast(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const startOver = useCallback(() => {
    window.location.reload()
  }, [])

  const pollJob = useCallback(async () => {
    if (!job?.id) return
    if (job.status === 'succeeded' || job.status === 'failed') return
    try {
      const j = await getJob(job.id)
      setJob(j)
    } catch {
      /* ignore transient errors while polling */
    }
  }, [job?.id, job?.status])

  useEffect(() => {
    if (!job?.id) return
    if (job.status === 'succeeded' || job.status === 'failed') return
    const t = setInterval(pollJob, 1200)
    return () => clearInterval(t)
  }, [job?.id, job?.status, pollJob])

  return (
    <div className="site-shell">
      <header className="site-header">
        <div className="site-header-inner">
          <div className="site-header-brand">
            <h1 className="site-header-title">ReconIQ</h1>
            <p className="site-header-sub">Reconciliation workspace</p>
          </div>
          <div className="site-header-clock" aria-live="polite">
            <time className="site-header-time" dateTime={clock.toISOString()}>
              {clock.toLocaleTimeString(undefined, {
                hour: 'numeric',
                minute: '2-digit',
                second: '2-digit',
              })}
            </time>
            <p className="site-header-tz">
              <span className="site-header-tz-short">{timeZoneShort}</span>
              <span className="site-header-tz-sep" aria-hidden="true">
                {' '}
                ·{' '}
              </span>
              <span className="site-header-tz-iana">{timeZoneIana}</span>
            </p>
          </div>
        </div>
      </header>

      <main className="app-main">
        <div className="page">
          <div className="intro-card">
            <p className="tagline">
              Compare two Excel workbooks (<strong>File A</strong> baseline vs <strong>File B</strong>). Pick key
              columns to match rows and narrative columns for export wording. Only <code>.xlsx</code>,{' '}
              <code>.xlsm</code>, and <code>.xls</code> are supported; the first sheet of each file is compared.
            </p>
          </div>

          <section className="panel">
            <h2>1. Upload File A and File B</h2>
            <div className="file-slots">
              <div className="file-slot">
                <span className="file-slot-label">File A (baseline)</span>
                <label className="file-input">
                  <input
                    type="file"
                    accept=".xlsx,.xlsm,.xls"
                    disabled={busy}
                    onChange={(e) => {
                      void onPickSlot('a', e.target.files)
                      e.currentTarget.value = ''
                    }}
                  />
                  <span>{busy ? 'Uploading…' : fileA ? 'Replace file…' : 'Choose file…'}</span>
                </label>
                {fileA && (
                  <p className="file-chosen">
                    <strong>{fileA.original_name}</strong>
                    <span className="meta">{fileA.kind}</span>
                  </p>
                )}
              </div>
              <div className="file-slot">
                <span className="file-slot-label">File B (compare to)</span>
                <label className="file-input">
                  <input
                    type="file"
                    accept=".xlsx,.xlsm,.xls"
                    disabled={busy}
                    onChange={(e) => {
                      void onPickSlot('b', e.target.files)
                      e.currentTarget.value = ''
                    }}
                  />
                  <span>{busy ? 'Uploading…' : fileB ? 'Replace file…' : 'Choose file…'}</span>
                </label>
                {fileB && (
                  <p className="file-chosen">
                    <strong>{fileB.original_name}</strong>
                    <span className="meta">{fileB.kind}</span>
                  </p>
                )}
              </div>
            </div>
          </section>

          {needsKeyFields && (
            <section className="panel">
              <h2>2. Select key field(s)</h2>
              <p className="hint">
                Choose one or more columns that together identify each row for matching File A to File B (e.g.
                Document ID, or ID + Line). These are validated on both files.
              </p>
              {columnsError && <p className="error">{columnsError}</p>}
              {!columnsError && keyColumns.length > 0 && (
                <ul className="key-list">
                  {keyColumns.map((col) => (
                    <li key={col}>
                      <label className="key-option">
                        <input
                          type="checkbox"
                          checked={selectedKeys.includes(col)}
                          onChange={() => toggleKey(col)}
                        />
                        <span>{col}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {needsKeyFields && (
            <section className="panel">
              <h2>3. Select narrative field(s)</h2>
              <p className="hint">
                Choose one or more columns whose values should lead the wording in the Excel export (e.g. only
                «Document» for summaries, even if the key is Document + Line). Often this is a single human-readable
                identifier.
              </p>
              {columnsError && <p className="error">{columnsError}</p>}
              {!columnsError && keyColumns.length > 0 && (
                <ul className="key-list">
                  {keyColumns.map((col) => (
                    <li key={`narr-${col}`}>
                      <label className="key-option">
                        <input
                          type="checkbox"
                          checked={selectedNarrative.includes(col)}
                          onChange={() => toggleNarrative(col)}
                        />
                        <span>{col}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          <section className="panel">
            <h2>4. Run comparison</h2>
            <label className="field">
              <span>OpenAI model (for pipeline summaries when USE_LLM_SUMMARY is enabled)</span>
              <select
                className="select-input"
                value={selectedOpenaiModel}
                onChange={(e) => setSelectedOpenaiModel(e.target.value)}
                aria-label="OpenAI model for optional LLM steps"
              >
                {llmModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <p className="hint run-actions-hint">
              Start over reloads the page so you can run a new comparison from a clean state.
            </p>
            <div className="run-actions">
              <button type="button" className="primary" disabled={busy || !canRun} onClick={runCompare}>
                {busy ? 'Working…' : 'Compare'}
              </button>
              <button type="button" className="secondary" onClick={startOver}>
                Start over
              </button>
            </div>
          </section>

          {error && <p className="error">{error}</p>}

          {job && (
            <section className="panel">
              <h2>Result</h2>
              <p className="status">
                Status: <code>{job.status}</code>
              </p>
              {job.key_field_names && job.key_field_names.length > 0 && (
                <p className="key-summary">
                  Key field(s): <code>{job.key_field_names.join(', ')}</code>
                </p>
              )}
              {job.narrative_field_names && job.narrative_field_names.length > 0 && (
                <p className="key-summary">
                  Narrative field(s): <code>{job.narrative_field_names.join(', ')}</code>
                </p>
              )}
              {job.openai_model && (
                <p className="key-summary">
                  OpenAI model: <code>{job.openai_model}</code>
                </p>
              )}
              {job.error_message && <p className="error">{job.error_message}</p>}
              {job.result_json && (
                <pre className="json">{JSON.stringify(job.result_json, null, 2)}</pre>
              )}
              {job.status === 'succeeded' && (
                <p className="downloads">
                  {job.report_storage_key && (
                    <a className="download" href={reportUrl(job.id)} target="_blank" rel="noreferrer">
                      Download Excel report
                    </a>
                  )}
                  <a className="download" href={exportPdfUrl(job.id)} target="_blank" rel="noreferrer">
                    Download PDF report
                  </a>
                </p>
              )}
            </section>
          )}
        </div>
      </main>

      <footer className="site-footer">
        <div className="site-footer-inner">
          <div className="site-footer-columns">
            <section className="site-footer-block" aria-labelledby="footer-about-heading">
              <h2 id="footer-about-heading" className="site-footer-heading">
                About us
              </h2>
              <p className="site-footer-text">
                <strong>Reconiq</strong> is a Turiaixis reconciliation tool for Excel: match rows by key, surface
                missing keys and value deltas, and download a structured Excel report. We believe{' '}
                <em>speed is easy, precision is earned</em> — the product is built to make that precision repeatable
                in your workflows.
              </p>
            </section>
            <section className="site-footer-block" aria-labelledby="footer-contact-heading">
              <h2 id="footer-contact-heading" className="site-footer-heading">
                Contact us
              </h2>
              <p className="site-footer-text">
                For demos, integrations, or enterprise deployment, reach out through your Turiaixis representative or
                the contact channel your organization uses for vendor engagement.
              </p>
            </section>
          </div>
          <div className="site-footer-bar">
            <span className="site-footer-mark">© {new Date().getFullYear()} Turiaixis</span>
            <div className="site-footer-logo" aria-label="Turiaixis">
              <img src="/turiaixis-logo.png" alt="Turiaixis — Speed is easy, Precision is earned" width={220} height={72} />
            </div>
          </div>
        </div>
      </footer>

      {toast && (
        <div className="toast-wrap" role="alert" aria-live="assertive">
          <div className="toast">
            <p className="toast-message">{toast}</p>
            <button type="button" className="toast-dismiss" onClick={() => setToast(null)} aria-label="Dismiss">
              ×
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
