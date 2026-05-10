import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createJob,
  exportPdfUrl,
  getFileColumns,
  getJob,
  reportUrl,
  uploadFile,
  type Job,
  type UploadedFile,
} from './api'
import './App.css'

function App() {
  const [fileA, setFileA] = useState<UploadedFile | null>(null)
  const [fileB, setFileB] = useState<UploadedFile | null>(null)
  const [kindOverride, setKindOverride] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [keyColumns, setKeyColumns] = useState<string[]>([])
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [selectedNarrative, setSelectedNarrative] = useState<string[]>([])
  const [columnsError, setColumnsError] = useState<string | null>(null)
  const [clock, setClock] = useState(() => new Date())

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

  const allPdf =
    fileA != null && fileB != null && fileA.kind === 'pdf' && fileB.kind === 'pdf'
  const needsKeyFields = fileA != null && fileB != null && !allPdf

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
          setColumnsError(e instanceof Error ? e.message : String(e))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [needsKeyFields, fileA])

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
      const ko = kindOverride.trim() || undefined
      const uploaded = await uploadFile(raw, ko)
      if (slot === 'a') {
        setFileA(uploaded)
      } else {
        setFileB(uploaded)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const canRun = useMemo(() => {
    if (files.length < 2) return false
    if (allPdf) return true
    if (files.length !== 2) return false
    return (
      selectedKeys.length >= 1 &&
      selectedNarrative.length >= 1 &&
      keyColumns.length >= 1 &&
      !columnsError
    )
  }, [
    files.length,
    allPdf,
    selectedKeys.length,
    selectedNarrative.length,
    keyColumns.length,
    columnsError,
  ])

  const runCompare = async () => {
    if (files.length < 2) {
      setError('Select at least two files.')
      return
    }
    if (needsKeyFields && (fileA == null || fileB == null)) {
      setError('Choose both File A and File B.')
      return
    }
    if (needsKeyFields && selectedKeys.length < 1) {
      setError('Select at least one column as the record key.')
      return
    }
    if (needsKeyFields && selectedNarrative.length < 1) {
      setError('Select at least one column to drive the report wording (narrative labels).')
      return
    }
    setError(null)
    setBusy(true)
    try {
      const j = await createJob(
        files.map((f) => f.id),
        allPdf ? undefined : selectedKeys,
        allPdf ? undefined : selectedNarrative,
      )
      setJob(j)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

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
              Compare Excel, PDF, or SAP export (JSON) files. Use <strong>File A</strong> for the baseline and{' '}
              <strong>File B</strong> for the file to compare against (two separate uploads so order is never
              ambiguous). For spreadsheets, pick key columns to match rows, then narrative columns for export
              wording.
            </p>
          </div>

      <section className="panel">
        <h2>1. Upload File A and File B</h2>
        <p className="hint">
          For SAP POC exports, use JSON with <code>columns</code> and <code>rows</code>, and set kind
          override to <code>sap</code>.
        </p>
        <label className="field">
          <span>Optional kind override</span>
          <input
            value={kindOverride}
            onChange={(e) => setKindOverride(e.target.value)}
            placeholder="e.g. sap"
          />
        </label>
        <div className="file-slots">
          <div className="file-slot">
            <span className="file-slot-label">File A (baseline)</span>
            <label className="file-input">
              <input
                type="file"
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
            Choose one or more columns whose values should lead the wording in the Excel and PDF output (e.g.
            only «Document» for summaries, even if the key is Document + Line). Often this is a single
            human-readable identifier.
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
        <h2>{needsKeyFields ? '4. Run comparison' : '2. Run comparison'}</h2>
        <button type="button" className="primary" disabled={busy || !canRun} onClick={runCompare}>
          {busy ? 'Working…' : 'Compare'}
        </button>
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
          {job.error_message && <p className="error">{job.error_message}</p>}
          {job.result_json && (
            <pre className="json">{JSON.stringify(job.result_json, null, 2)}</pre>
          )}
          {job.status === 'succeeded' && job.report_storage_key && (
            <p className="downloads">
              <a className="download" href={reportUrl(job.id)} target="_blank" rel="noreferrer">
                Download Excel report
              </a>
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
                <strong>Reconiq</strong> is a Turiaixis reconciliation tool for structured business data: match
                rows across Excel and SAP-style exports, surface missing keys and value deltas, and download Excel
                and PDF reports. We believe <em>speed is easy, precision is earned</em> — the product is built to
                make that precision repeatable in your workflows.
              </p>
            </section>
            <section className="site-footer-block" aria-labelledby="footer-contact-heading">
              <h2 id="footer-contact-heading" className="site-footer-heading">
                Contact us
              </h2>
              <p className="site-footer-text">
                For demos, integrations, or enterprise deployment, reach out through your Turiaixis representative
                or the contact channel your organization uses for vendor engagement.
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
    </div>
  )
}

export default App
