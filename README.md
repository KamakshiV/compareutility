# Reconiq

POC application to compare **two Excel workbooks** (File A → File B) with a **FastAPI** backend, **LangGraph** orchestration, optional **OpenAI / Azure OpenAI** narrative, and a **React** UI.

## Stack (as implemented)

| Layer | Choice |
| --- | --- |
| Frontend | React (Vite + TypeScript) |
| API | Python FastAPI |
| Agents | LangGraph |
| LLM | OpenAI or Azure OpenAI (optional) |
| Excel | Polars + openpyxl / xlrd |
| Reports | xlsxwriter + ReportLab (PDF) |
| Storage | Local disk (default) or Azure Blob |
| Metadata | PostgreSQL |
| Jobs | FastAPI `BackgroundTasks` (POC) |

## Backend layout (matches proposed architecture)

```
backend/app/
├── main.py                 # FastAPI entry
├── api/
│   ├── routes_upload.py    # file upload API
│   ├── routes_jobs.py      # jobs + Excel (`/report`) + PDF (`/export.pdf`) downloads
│   └── routes_health.py
├── agents/                 # LangGraph orchestration
│   ├── graph.py            # state machine wiring
│   ├── ingestion_agent.py
│   ├── schema_profiler_agent.py
│   ├── mapping_agent.py
│   ├── rule_agent.py
│   ├── execution_controller_agent.py
│   ├── discrepancy_identification_agent.py
│   ├── insight_agent.py
│   └── report_narration_agent.py
├── services/               # connectors + deterministic engine + reports
│   ├── excel_parser.py
│   ├── reconciliation_engine.py
│   ├── reconciliation_analysis.py
│   ├── excel_pdf_sections.py
│   ├── pdf_discrepancy_report.py
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

## Production deployment (recommended stack)

Target setup:

| Layer | Service |
| --- | --- |
| **Frontend** | [Vercel](https://vercel.com) |
| **Backend** | [Render](https://render.com) (Docker Web Service) |
| **Database** | [Supabase](https://supabase.com) Postgres |
| **AI** | [OpenAI](https://platform.openai.com) API (`USE_LLM_SUMMARY` + `OPENAI_API_KEY`) |

Repo files that help: `render.yaml` (Render Blueprint), `backend/Dockerfile` (API image).

### 1. Supabase Postgres

1. Create a project → **Project Settings → Database**.
2. Copy the **URI** connection string (direct `5432` is simplest with this app).
3. Convert it for SQLAlchemy **asyncpg**:
   - Change the scheme from `postgresql://` to **`postgresql+asyncpg://`**.
   - Append **`?ssl=require`** (Supabase requires TLS), e.g.  
     `postgresql+asyncpg://postgres:YOUR_PASSWORD@db.xxxxx.supabase.co:5432/postgres?ssl=require`
4. If the DB password contains `@`, `:`, or `/`, **URL-encode** it.

The API runs `create_all` + small `ALTER … IF NOT EXISTS` patches on startup, so tables are created on first boot (no separate migration step required for the POC).

### 2. Render (backend)

1. **New → Blueprint** and connect the repo, *or* **New → Web Service** and point at this repo.
2. Use **`backend`** as the **root directory** (or deploy from the repo root using `render.yaml`, which sets `rootDir: backend`).
3. **Docker** build (`backend/Dockerfile`). Render sets **`PORT`**; the image already uses it.
4. **Health check path:** `/health`.
5. **Environment variables** (Render dashboard — mark secrets as **Secret**):

   | Variable | Example / notes |
   | --- | --- |
   | `DATABASE_URL` | Supabase URI with `postgresql+asyncpg://` and `?ssl=require` — name must be exactly **`DATABASE_URL`** (Render **Environment** tab; not only a local `.env` file). |
   | `CORS_ORIGINS` | `https://your-app.vercel.app,https://your-app-git-main-xxx.vercel.app` (every Vercel origin you use, comma-separated, **no** trailing slashes) |
   | `OPENAI_API_KEY` | From OpenAI (keep **only** on Render) |
   | `USE_LLM_SUMMARY` | `true` or `false` |
   | `STORAGE_LOCAL_PATH` | e.g. `/var/data/storage` (optional; see note below) |
   | `AZURE_STORAGE_CONNECTION_STRING` | **Recommended on Render** — durable blob storage for uploads and reports (with `AZURE_CONTAINER_NAME`). |

**Ephemeral disk:** On Render’s **free** tier, local file storage is wiped on redeploy while Postgres still lists old `uploaded_files` rows, so `POST /jobs` can fail with a missing file under `STORAGE_LOCAL_PATH`. Re-upload after each deploy, or configure **Azure Blob** (`AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CONTAINER_NAME`). The API returns **HTTP 410** with that explanation when the blob is missing.

### 3. Vercel (frontend)

1. **Add New Project** → import the same repo.
2. **Root Directory:** `frontend`.
3. Framework **Vite**; output `dist` (see `frontend/vercel.json`).
4. **Environment variable:** `VITE_API_BASE` = your Render service URL, e.g. `https://reconiq-api.onrender.com` (**HTTPS**, no trailing slash).  
   Production and **Preview** deployments can use the same API URL, or separate Render services if you prefer.

### 4. OpenAI

- Set `OPENAI_API_KEY` on **Render** (not in Vercel).
- Set `USE_LLM_SUMMARY=true` when you want pipeline + insight LLM calls; `false` for deterministic-only (no OpenAI usage).

### 5. Order of operations

1. Supabase project + `DATABASE_URL`  
2. Render deploy + verify `https://<your-service>.onrender.com/health`  
3. Vercel `VITE_API_BASE` → that API URL  
4. Update Render `CORS_ORIGINS` to match your real Vercel URLs, **redeploy** if needed  

**Free-tier caveat:** Render free web services **sleep** after idle time; the first request after sleep can take tens of seconds. Upgrade or use a keep-alive ping if that matters for demos.

**Render build error: `Could not open requirements file ... requirements.txt`:** The service is using the **monorepo root** as its working directory. Fix one of these ways:

1. **Docker (recommended):** In the service **Settings**, set **Root Directory** to `backend`, ensure **Environment** is **Docker**, and **Dockerfile Path** `Dockerfile` (file is `backend/Dockerfile`). Clear any custom **Build Command** that runs `pip install` at the repo root.
2. **Native Python:** Set **Root Directory** to `backend`, **Build Command** `pip install -r requirements.txt`, **Start Command** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, **Python version** 3.11+.

Then **Manual Deploy → Clear build cache & deploy**.

**Render runtime error: `Could not import module "main"`:** The start command must reference this app’s module path **`app.main:app`**, not `main:app`. In the service **Settings** → **Start Command**, set:

`uvicorn app.main:app --host 0.0.0.0 --port $PORT`

With **Root Directory** `backend`, a `backend/Procfile` is included so Render’s Python runtime can pick up the correct `web` command automatically.

**Render crashes during “Waiting for application startup” / lifespan:** The app opens a DB connection and runs `create_all` + column patches. Check **Render → Logs** for the full traceback (the app now logs **`Database startup failed`** with the underlying error).

1. **`DATABASE_URL` not set** or still local — see earlier notes.
2. **Scheme** must be **`postgresql+asyncpg://`**, not `postgresql://` alone.
3. **Password** in the URL must match Supabase; special characters **URL-encoded**.
4. **IPv4 vs IPv6:** Render is often IPv4-only; Supabase **direct** (`db…:5432`) can be IPv6-only. If logs show timeout / network unreachable, open Supabase **Connect** and use the **Session pooler** URI (often port **6543**), still converted to `postgresql+asyncpg://` + `?ssl=require`.
5. **Python version:** `backend/runtime.txt` pins **3.11.x**; set Render’s Python version or use Docker so you are not on an experimental 3.14 runtime.

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

- **Database migration:** On startup the API runs `ALTER TABLE … ADD COLUMN IF NOT EXISTS` for `key_field_names`, `narrative_field_names`, and `ordered_file_ids` on `comparison_jobs` (because `create_all` does not alter existing tables). Restart uvicorn after pulling changes. You can still run the same statements manually if you prefer.

## File types

- **Excel**: `.xlsx` / `.xlsm` / `.xls` — first sheet is loaded; **File A → File B** key-based compare (first uploaded file is A, second is B). Exactly **two** files per job.

## Keys and narrative labels

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

Every selected column name must exist in **both** files.

Compare is **one-way** (A → B): keys present only in B are not listed. Value-mismatch logic uses only keys that appear **exactly once** in each file.

## Export format (Excel + PDF)

Successful jobs expose:

- **Excel** (`GET /jobs/{id}/report`): workbook with **Export**, **By record**, **Field deltas**, optional **LLM discrepancies**, and **Summary** (JSON metadata).
- **PDF** (`GET /jobs/{id}/export.pdf`): ReportLab document with material / itemized summary sections, **Missing in File B**, **Value mismatch**, and (when LLM discrepancy ID is enabled) an **LLM-identified discrepancies** section at the top.

If more than two spreadsheet files are attached to a job, **only the first two** are compared; see `files_ignored_note` in the comparison JSON when applicable.

Row caps: `MAX_EXPORT_ROWS` in `app/services/export_tabular.py`; PDF table body rows per section capped in `app/services/pdf_discrepancy_report.py` and `app/services/excel_pdf_sections.py`; value-mismatch field rows cap in `app/services/reconciliation_analysis.py`.

## Optional: LLM summary

In `backend/.env`, set `USE_LLM_SUMMARY=true` and either:

- `OPENAI_API_KEY` for OpenAI, or
- `OPENAI_API_KEY` + `OPENAI_API_BASE` + `OPENAI_API_VERSION` + `OPENAI_DEPLOYMENT_NAME` for Azure OpenAI.

When enabled, the **LangGraph** pipeline calls the model at several stages (advisory text only; **reconciliation stays deterministic**):

| Stage | Output field | Role |
| --- | --- | --- |
| Ingestion | `ingest_notes.llm_notes` | Quick checks on file pairing and readiness |
| Schema profiler | `schema_profile.llm_notes` | POC limitations for Excel (first sheet) |
| Mapping | `column_mapping.llm_notes` | Risks around keys and same-name columns |
| Rules | `recommended_rules.llm_notes` | How to read policy metadata and edge cases |
| Insight | `llm_summary` (job JSON) | Executive bullets over the full comparison result |

All of these appear under `result_json.agent_trace` in the job response (except the final insight, which is also top-level `llm_summary`). Turn off with `USE_LLM_SUMMARY=false` to avoid API calls and latency.

**Cost / latency:** with LLMs enabled, each successful job performs **five** model calls (ingestion, profiling, mapping, rules, insight). Disable the flag for fastest deterministic-only runs.

**Observability:** each invocation logs at **INFO** via `app.agents.llm_tools`: **`Starting LLM service for "<purpose>" via Agent [<stage>] …`** before the model call, and **`Finished LLM service for "<purpose>" via Agent [<stage>]: success …`** (or **`: error …`**) after. Default purposes map from stage (`ingestion` → ingestion readiness review, etc.). Visible in `uvicorn` stdout/stderr (e.g. Render **Logs**).

## Optional: Azure Blob

Set `AZURE_STORAGE_CONNECTION_STRING` and `AZURE_CONTAINER_NAME` in `backend/.env`. Without them, files are stored under `STORAGE_LOCAL_PATH`.

## Production hardening

- Swap `BackgroundTasks` for **Celery + Redis** (Redis service is already in `docker-compose.yml`).
- Add Alembic migrations instead of `create_all` on startup.
- Optional: second-sheet / multi-sheet Excel, or CSV ingestion, as product needs grow.
# compareutility

If you ever need to start from scratch (3 terminals)
1 — Postgres (repo root):
cd /Users/kamakshi/Documents/AgenticAI-IK/CompareUtility && docker compose up -d postgres
2 — Backend:
cd /Users/kamakshi/Documents/AgenticAI-IK/CompareUtility/backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
3 — Frontend:
cd /Users/kamakshi/Documents/AgenticAI-IK/CompareUtility/frontend && npm run dev
Open http://127.0.0.1:5173 (with default .env, requests use the Vite /api proxy to port 8000).