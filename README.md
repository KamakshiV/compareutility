# Reconiq

POC application to compare **two or more** files (Excel, PDF, or SAP tabular exports) with a **FastAPI** backend, **LangGraph** orchestration, optional **OpenAI / Azure OpenAI** narrative, and a **React** UI.

## Stack (as implemented)

| Layer | Choice |
| --- | --- |
| Frontend | React (Vite + TypeScript) |
| API | Python FastAPI |
| Agents | LangGraph |
| LLM | OpenAI or Azure OpenAI (optional) |
| Excel | Polars + DuckDB |
| PDF | PyMuPDF + pdfplumber |
| Reports | xlsxwriter |
| Storage | Local disk (default) or Azure Blob |
| Metadata | PostgreSQL |
| Jobs | FastAPI `BackgroundTasks` (POC) |

## Backend layout (matches proposed architecture)

```
backend/app/
├── main.py                 # FastAPI entry
├── api/
│   ├── routes_upload.py    # file upload API
│   ├── routes_jobs.py      # comparison jobs API
│   ├── routes_reports.py   # Excel report download
│   └── routes_health.py
├── agents/                 # LangGraph orchestration
│   ├── graph.py            # state machine wiring
│   ├── ingestion_agent.py
│   ├── schema_profiler_agent.py
│   ├── mapping_agent.py
│   ├── rule_agent.py
│   ├── execution_controller_agent.py
│   ├── insight_agent.py
│   └── report_narration_agent.py
├── services/               # connectors + deterministic engine + reports
│   ├── excel_parser.py
│   ├── pdf_parser.py
│   ├── reconciliation_engine.py
│   ├── report_generator.py
│   ├── storage_service.py
│   └── …
├── db/
│   ├── database.py         # async engine + sessions
│   ├── models.py           # SQLAlchemy metadata tables
│   └── job_repository.py
└── models/
    └── schemas.py          # Pydantic request/response models
```

## Deploy frontend on Vercel

1. In the [Vercel dashboard](https://vercel.com), **Add New Project** and import this repo (or connect GitHub).
2. Set **Root Directory** to `frontend` (not the monorepo root).
3. Framework preset **Vite**; build output `dist` (already set in `frontend/vercel.json`).
4. Under **Environment Variables**, add:
   - `VITE_API_BASE` — full origin of your deployed FastAPI API, e.g. `https://api.yourdomain.com` (no trailing slash). Local dev uses `http://127.0.0.1:8000` from `frontend/.env`.
5. On the **API server**, set `CORS_ORIGINS` in `backend/.env` to include your Vercel site origin, e.g. `https://your-app.vercel.app` (comma-separated if you have several). Restart the API after changing it.

The browser only talks to your FastAPI backend; Vercel hosts static assets and the SPA. Keep secrets (OpenAI keys, DB URL, Azure) on the server, not in Vercel, except public values like `VITE_API_BASE`.

## Prerequisites

- Docker (for PostgreSQL)
- Python 3.9+ (3.11+ recommended)
- Node.js 20+

## Run locally

Start services in this order: **PostgreSQL → backend → frontend**.

### 1. PostgreSQL (Docker)

From the **repository root** (where `docker-compose.yml` lives):

```bash
docker compose up -d postgres
```

The container maps Postgres to **host port 5433** (not 5432) so a local PostgreSQL on your machine does not receive app connections by mistake. Ensure `DATABASE_URL` in `backend/.env` points at `127.0.0.1:5433` (see `backend/.env.example`).

### 2. Backend (FastAPI)

Open a **new terminal**:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp -n .env.example .env     # first run only; won't overwrite an existing .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API root: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- OpenAPI docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 3. Frontend (React / Vite)

Open **another terminal**:

```bash
cd frontend
npm install
cp -n .env.example .env     # first run only
npm run dev
```

- UI: [http://127.0.0.1:5173](http://127.0.0.1:5173)

**Default local setup:** leave `VITE_API_BASE` **unset** in `frontend/.env`. The dev server proxies `/api/*` to `http://127.0.0.1:8000`, so the browser stays same-origin and you avoid CORS. Ensure the API listens on **8000**.

**Optional:** set `VITE_API_BASE=http://127.0.0.1:8000` (or another port) only if you want the browser to call the API directly — then set `CORS_ORIGINS` in `backend/.env` to match your UI origin (scheme + host + port) and restart uvicorn.

### Troubleshooting

- **Browser shows `Failed to fetch` when uploading or comparing:** (1) Start Postgres (`docker compose up -d postgres`) and the API (`uvicorn … --port 8000`). (2) Prefer **no** `VITE_API_BASE` in `frontend/.env` so `npm run dev` uses the `/api` proxy; restart the dev server after changing `.env`. (3) If you use a direct `VITE_API_BASE` URL instead, add your exact page origin to `CORS_ORIGINS` in `backend/.env`. (4) Deployed UI on **HTTPS** (e.g. Vercel) cannot call `http://127.0.0.1:8000` on your laptop — use a public API URL in `VITE_API_BASE` or run the UI locally.

- **`Address already in use` on port 8000:** Another process (often a previous `uvicorn`) is bound to that port. Stop it, or run the API on another port, e.g. `uvicorn app.main:app --reload --host 0.0.0.0 --port 8001`. If you use the Vite proxy, change `frontend/vite.config.ts` `proxy['/api'].target` to that port (or switch to `VITE_API_BASE` with a matching URL).

  ```bash
  lsof -iTCP:8000 -sTCP:LISTEN
  kill <PID>
  ```

- **Do not paste narrative text into the shell** (e.g. “(Ctrl+C)”); only run the commands above.

- **Database migration:** On startup the API runs `ALTER TABLE … ADD COLUMN IF NOT EXISTS` for `key_field_names` and `narrative_field_names` on `comparison_jobs` (because `create_all` does not alter existing tables). Restart uvicorn after pulling changes. You can still run the same statements manually if you prefer.

## File types

- **Excel**: `.xlsx` / `.xls` — first sheet is loaded; **File A → File B** key-based compare (first uploaded file is A, second is B). Exactly **two** spreadsheet files per job.
- **PDF**: text extraction (PyMuPDF) plus optional pdfplumber sample; unified diff of line-oriented text.
- **SAP (POC)**: upload JSON exports with shape `{"columns": [...], "rows": [[...], ...]}` and set form field **kind override** to `sap` (extension alone is not enough).

## Keys and narrative labels (Excel / SAP)

Upload **exactly two** files: **File A** (baseline, first in upload order) and **File B** (second).

1. **Key fields** — columns that together match a row in A to a row in B (composite keys allowed).
2. **Narrative fields** — columns whose values lead the **wording** in exports (e.g. pick «Document» so summaries read *«250078» — only «Delivery Date» differs…* even if the key is Document + Line).

The UI loads headers from `GET /files/{file_id}/columns` (first file). Example job body:

```json
{
  "file_ids": ["…", "…"],
  "key_field_names": ["Document", "Line"],
  "narrative_field_names": ["Document"]
}
```

If `narrative_field_names` is omitted, the API defaults it to `key_field_names`.

**PDF-only** jobs omit both lists. Every selected column name must exist in **both** files.

Compare is **one-way** (A → B): keys present only in B are not listed. Value-mismatch logic (PDF §4.2) uses only keys that appear **exactly once** in each file.

## Export format (Excel + PDF)

Successful jobs expose:

- **Excel** (`GET /jobs/{id}/report`): workbook with:
  - **Export** — `Issue`, **Category** (`Missing in File B` / `Value mismatch (same key)`), **Discrepancy** (uses **narrative fields** for the opening «…» label), then source columns (value-mismatch rows show **File A** values).
  - **By record** — narrative label, technical record key, field count, and summary text.
  - **Field deltas** — one row per differing field (aligned with PDF §4.2): label from narrative columns, field name, File A / File B values, variance, category.
  - **Summary** — JSON metadata (`tabular_export` is summarized by row count to avoid duplication).

- **PDF discrepancy report** (`GET /jobs/{id}/export.pdf`) for spreadsheets:
  - **4.1 Missing in File B** — File A rows whose key does not appear in File B.
  - **4.2 Value mismatch** — same key once per file, differing non-key fields; the first column is built from **narrative fields**.

Document **PDF** comparisons (scanned/text PDFs) use a single **Text comparison** section built from the line-level diff (no spreadsheet schema).

If more than two spreadsheet files are attached to a job, **only the first two** are compared; see `files_ignored_note` in the comparison JSON when applicable.

Row caps: `MAX_EXPORT_ROWS` / `MAX_PDF_SECTION_ROWS` in `app/services/export_tabular.py` and `app/services/tabular_pdf_sections.py`.

## Optional: LLM summary

In `backend/.env`, set `USE_LLM_SUMMARY=true` and either:

- `OPENAI_API_KEY` for OpenAI, or
- `OPENAI_API_KEY` + `OPENAI_API_BASE` + `OPENAI_API_VERSION` + `OPENAI_DEPLOYMENT_NAME` for Azure OpenAI.

When enabled, the **LangGraph** pipeline calls the model at several stages (advisory text only; **reconciliation stays deterministic**):

| Stage | Output field | Role |
| --- | --- | --- |
| Ingestion | `ingest_notes.llm_notes` | Quick checks on file pairing and readiness |
| Schema profiler | `schema_profile.llm_notes` | POC limitations for Excel / PDF / SAP |
| Mapping | `column_mapping.llm_notes` | Risks around keys and same-name columns |
| Rules | `recommended_rules.llm_notes` | How to read policy metadata and edge cases |
| Insight | `llm_summary` (job JSON) | Executive bullets over the full comparison result |

All of these appear under `result_json.agent_trace` in the job response (except the final insight, which is also top-level `llm_summary`). Turn off with `USE_LLM_SUMMARY=false` to avoid API calls and latency.

**Cost / latency:** with LLMs enabled, each successful job performs **five** model calls (ingestion, profiling, mapping, rules, insight). Disable the flag for fastest deterministic-only runs.

## Optional: Azure Blob

Set `AZURE_STORAGE_CONNECTION_STRING` and `AZURE_CONTAINER_NAME` in `backend/.env`. Without them, files are stored under `STORAGE_LOCAL_PATH`.

## Production hardening

- Swap `BackgroundTasks` for **Celery + Redis** (Redis service is already in `docker-compose.yml`).
- Add Alembic migrations instead of `create_all` on startup.
- Harden SAP integration (HANA client, RFC, or governed ODBC) instead of JSON exports.
# compareutility
