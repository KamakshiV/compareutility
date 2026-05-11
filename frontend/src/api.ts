/**
 * - If `VITE_API_BASE` is set (non-empty): call that URL directly.
 * - If unset/empty in dev: use `/api` and rely on Vite proxy → http://127.0.0.1:8000 (same origin, no CORS).
 * - Production build without env: fall back to localhost (set `VITE_API_BASE` on Vercel etc.).
 */
function resolveApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE
  const trimmed = raw == null ? '' : String(raw).trim()
  if (trimmed !== '') {
    return trimmed.replace(/\/$/, '')
  }
  if (import.meta.env.DEV) {
    return '/api'
  }
  return 'http://127.0.0.1:8000'
}

const API_BASE = resolveApiBase()

/**
 * Turn FastAPI / JSON error bodies into a single line for users.
 * e.g. `{"detail":"Column 'x' not found..."}` → human message (not raw JSON).
 */
export function formatApiErrorResponseBody(bodyText: string): string {
  const raw = bodyText.trim()
  if (!raw) return 'Request failed.'
  try {
    const j = JSON.parse(raw) as { detail?: unknown }
    if (j && typeof j === 'object' && 'detail' in j) {
      const d = j.detail
      if (typeof d === 'string') return d
      if (Array.isArray(d)) {
        return d
          .map((item) => {
            if (typeof item === 'string') return item
            if (item && typeof item === 'object' && 'msg' in item) {
              return String((item as { msg: string }).msg)
            }
            return JSON.stringify(item)
          })
          .join(' ')
      }
    }
  } catch {
    /* not JSON */
  }
  return raw
}

async function throwIfNotOk(res: Response): Promise<void> {
  if (res.ok) return
  const text = await res.text()
  throw new Error(formatApiErrorResponseBody(text))
}

function networkErrorMessage(cause: unknown): string {
  const proxyHint =
    API_BASE === '/api'
      ? 'Requests use the Vite dev proxy (`/api` → port 8000). Start the backend on 8000 and use `npm run dev`. '
      : `Requests go to ${API_BASE}. Start the backend there, or clear VITE_API_BASE in frontend/.env to use the dev proxy. `
  const corsHint =
    API_BASE !== '/api'
      ? 'If the page origin differs from CORS_ORIGINS in backend/.env, add it and restart uvicorn. '
      : ''
  const hint = proxyHint + corsHint + 'See README → Run locally.'
  if (cause instanceof TypeError && String(cause.message).toLowerCase().includes('fetch')) {
    return `${hint} (browser reported: ${cause.message})`
  }
  return `${hint} (${cause instanceof Error ? cause.message : String(cause)})`
}

/** Wraps fetch so connection/CORS failures show a clear message instead of only "Failed to fetch". */
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init)
  } catch (e) {
    throw new Error(networkErrorMessage(e))
  }
}

export type UploadedFile = {
  id: string
  original_name: string
  kind: string
  created_at: string
}

export type FileColumns = {
  file_id: string
  columns: string[]
  kind: string
}

export type Job = {
  id: string
  status: string
  error_message: string | null
  result_json: Record<string, unknown> | null
  report_storage_key: string | null
  key_field_names: string[] | null
  narrative_field_names: string[] | null
  openai_model: string | null
  created_at: string
  updated_at: string
  file_ids: string[]
}

export type OpenaiModelOptions = {
  models: string[]
  default: string
}

export async function uploadFile(file: File, kindOverride?: string): Promise<UploadedFile> {
  const form = new FormData()
  form.append('file', file)
  if (kindOverride) form.append('kind_override', kindOverride)

  const res = await apiFetch(`${API_BASE}/files`, {
    method: 'POST',
    body: form,
  })
  await throwIfNotOk(res)
  return res.json()
}

export async function getFileColumns(fileId: string): Promise<FileColumns> {
  const res = await apiFetch(`${API_BASE}/files/${fileId}/columns`)
  await throwIfNotOk(res)
  return res.json()
}

export async function getOpenaiModelOptions(): Promise<OpenaiModelOptions> {
  const res = await apiFetch(`${API_BASE}/jobs/openai-model-options`)
  await throwIfNotOk(res)
  return res.json()
}

export async function createJob(
  fileIds: string[],
  keyFieldNames?: string[],
  narrativeFieldNames?: string[],
  openaiModel?: string,
): Promise<Job> {
  const body: Record<string, unknown> = { file_ids: fileIds }
  if (keyFieldNames !== undefined && keyFieldNames.length > 0) {
    body.key_field_names = keyFieldNames
  }
  if (narrativeFieldNames !== undefined && narrativeFieldNames.length > 0) {
    body.narrative_field_names = narrativeFieldNames
  }
  if (openaiModel !== undefined && openaiModel.trim() !== '') {
    body.openai_model = openaiModel.trim()
  }
  const res = await apiFetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  await throwIfNotOk(res)
  return res.json()
}

export async function getJob(id: string): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/jobs/${id}`)
  await throwIfNotOk(res)
  return res.json()
}

export function reportUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/report`
}

export function exportPdfUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/export.pdf`
}
