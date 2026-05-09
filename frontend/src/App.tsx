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
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [kindOverride, setKindOverride] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [keyColumns, setKeyColumns] = useState<string[]>([])
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [selectedNarrative, setSelectedNarrative] = useState<string[]>([])
  const [columnsError, setColumnsError] = useState<string | null>(null)

  const allPdf =
    files.length >= 2 && files.every((f) => f.kind === 'pdf')
  const needsKeyFields = files.length >= 2 && !allPdf

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
        const res = await getFileColumns(files[0].id)
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
  }, [needsKeyFields, files])

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

  const onPick = async (list: FileList | null) => {
    if (!list?.length) return
    setError(null)
    setBusy(true)
    try {
      const uploaded: UploadedFile[] = []
      for (const f of Array.from(list)) {
        const ko = kindOverride.trim() || undefined
        uploaded.push(await uploadFile(f, ko))
      }
      setFiles((prev) => [...prev, ...uploaded])
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
    if (needsKeyFields && files.length !== 2) {
      setError('Spreadsheet compare uses exactly two files: upload File A first, then File B.')
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
    <div className="app">
      <header className="header">
        <h1>Reconiq</h1>
        <p className="tagline">
          Compare Excel, PDF, or SAP export (JSON) files. For spreadsheets, upload exactly two files: the
          first is <strong>File A</strong> (baseline), the second <strong>File B</strong>. Pick key columns to
          match rows, then pick narrative columns for how differences are described in the export.
        </p>
      </header>

      <section className="panel">
        <h2>1. Upload files</h2>
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
        <label className="file-input">
          <input
            type="file"
            multiple
            disabled={busy}
            onChange={(e) => void onPick(e.target.files)}
          />
          <span>{busy ? 'Uploading…' : 'Choose files'}</span>
        </label>

        {files.length > 0 && (
          <ul className="file-list">
            {files.map((f, i) => (
              <li key={f.id}>
                <strong>{f.original_name}</strong>
                <span className="meta">{f.kind}</span>
                {needsKeyFields && i < 2 && (
                  <span className="meta">{i === 0 ? 'File A' : 'File B'}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        {needsKeyFields && files.length > 2 && (
          <p className="error">
            Remove extra files — spreadsheet jobs require exactly two uploads (File A, then File B).
          </p>
        )}
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
  )
}

export default App
