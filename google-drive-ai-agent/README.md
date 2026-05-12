# Google Drive AI Search Agent

Production-style demo: a **conversational assistant** that turns natural language into **Google Drive `q` queries**, executes **`files.list`**, and returns **structured, linkable results**. The stack is **Streamlit → FastAPI → LangGraph (tool calling) → Google Drive API**.

![Architecture](https://img.shields.io/badge/stack-Streamlit%20%7C%20FastAPI%20%7C%20LangGraph%20%7C%20Drive-blue)

## Features

- **Natural language** search, filters, and follow-ups (“now only the finance PDFs”).
- **LangGraph** agent with **tool calling** and **multi-turn session memory** (`session_id`).
- **Drive `q` coverage**: `name`, `name contains`, `mimeType`, `fullText`, `modifiedTime`, multi-clause `and` / `or`, always scoped to a folder + `trashed=false`.
- **Semantic re-ranking** (optional): embedding similarity re-orders the current result set (`ENABLE_SEMANTIC_RERANK`).
- **Streaming** NDJSON endpoint for a typing-style UX (`POST /chat/stream`).
- **Polished Streamlit UI**: dark theme, cards, expandable results, tool logs, query explanations.

## Architecture

```mermaid
flowchart LR
  U[User] --> ST[Streamlit UI]
  ST -->|HTTP POST /chat| API[FastAPI]
  API --> AG[LangGraph Agent]
  AG --> TL[DriveSearchTool]
  TL --> DV[Google Drive API files.list]
  DV --> TL
  TL --> AG
  AG --> API
  API --> ST
```

## Repository layout

```
google-drive-ai-agent/
├── backend/                 # FastAPI + LangGraph + Drive service
├── frontend/                # Streamlit chat client
├── docker-compose.yml       # Optional all-in-one run
└── secrets/                 # Put service-account.json here (see secrets/README.txt)
```

## Prerequisites

- **Python 3.11+** recommended (some LangChain warnings appear on very new Python versions like 3.14, but the code imports cleanly).
- **OpenAI API key** for `gpt-4o-mini` (override with `OPENAI_MODEL`).
- **Google Cloud project** with **Drive API** enabled.
- A **service account** JSON key and a **Drive folder** shared with that service account (Viewer access is sufficient).

## Google Cloud setup (high level)

1. Create/select a GCP project.
2. Enable **Google Drive API**.
3. Create a **service account** and download a JSON key.
4. Copy the target **Drive folder ID** from the folder URL.
5. In Drive, **share the folder** with the service account email (`…@….iam.gserviceaccount.com`).

## Environment variables

Copy `backend/.env.example` → `backend/.env` and set:

| Variable | Purpose |
|---------|---------|
| `OPENAI_API_KEY` | OpenAI key |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Absolute or relative path to the service account JSON |
| `GOOGLE_DRIVE_FOLDER_ID` | Folder to scope all searches |

Optional:

- `OPENAI_MODEL` (default `gpt-4o-mini`)
- `CORS_ORIGINS` (comma-separated; include your Streamlit origin)
- `DRIVE_PAGE_SIZE` (default `25`)
- `ENABLE_SEMANTIC_RERANK` (`true`/`false`)
- `BACKEND_PUBLIC_URL` (used by docs/examples)

## Run locally

### 1) Backend

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env   # Windows: copy; macOS/Linux: cp
# edit .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health: `GET http://127.0.0.1:8000/health`  
Readiness (checks key file path): `GET http://127.0.0.1:8000/ready`

### 2) Frontend

```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

From the repository root you can also run:

```bash
streamlit run frontend/app.py
```

Set `BACKEND_URL` (optional) if the API is not on `http://127.0.0.1:8000`.

## API contract

### `POST /chat`

Request:

```json
{ "message": "Find PDF reports from last month", "session_id": "optional-uuid" }
```

Response (trimmed):

```json
{
  "response": "…natural language summary…",
  "results": [
    {
      "id": "…",
      "name": "…",
      "mimeType": "application/pdf",
      "modifiedTime": "2026-04-12T18:22:10.000Z",
      "webViewLink": "https://drive.google.com/file/d/…/view"
    }
  ],
  "session_id": "…",
  "drive_q_used": "((…) and 'FOLDER_ID' in parents and trashed=false)",
  "tool_logs": ["…"],
  "query_explanation": "…",
  "semantic_ranked": true,
  "error": null,
  "suggestions": ["Show only PDFs", "Only files modified this week"]
}
```

### `POST /chat/stream`

Returns **NDJSON** lines:

- `{"type":"meta", ...}`
- `{"type":"token", "text":"…"}` (word-chunked assistant text)
- `{"type":"final", ...}` (same fields as `/chat` plus structured `results`)

## Docker

1. Put your key at `secrets/service-account.json` (or adjust the volume in `docker-compose.yml`).
2. Create `backend/.env` with at least:

```
OPENAI_API_KEY=...
GOOGLE_SERVICE_ACCOUNT_FILE=/app/service-account.json
GOOGLE_DRIVE_FOLDER_ID=...
```

3. Run:

```bash
docker compose up --build
```

- API: `http://localhost:8000`
- UI: `http://localhost:8501`

## Deploy on Render (backend + frontend)

Host **two** Web Services from this repo: one Docker image for the API, one for Streamlit. Dockerfiles listen on Render’s **`PORT`** (`backend/Dockerfile`, `frontend/Dockerfile`).

### 1) Push the project to GitHub

Render builds from your repository.

### 2) Create the **API** service

1. **New → Web Service →** connect repo.
2. **Runtime:** Docker.
3. **Root Directory** depends on how the repo is laid out on GitHub:
   - If the repo root **only** contains this app (`backend/`, `frontend/` at the top): leave **Root Directory** empty.
   - If the app lives in a subfolder (e.g. `AI Agent` repo with `google-drive-ai-agent/backend/...`): set **Root Directory** to `google-drive-ai-agent`.
4. If configuring manually (paths are **relative to Root Directory** if set, else repo root):
   - **Dockerfile Path:** `backend/Dockerfile`
   - **Docker build context:** `backend`
5. **Health Check Path:** `/health`

**Environment variables** (Environment tab):

| Key | Value |
|-----|--------|
| `OPENAI_API_KEY` | Your OpenAI key |
| `GOOGLE_DRIVE_FOLDER_ID` | Your Drive folder ID |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path where the JSON key file is mounted (see Secret Files below) |
| `CORS_ORIGINS` | Your Streamlit site URL, e.g. `https://drive-search-ui.onrender.com` (comma-separated if multiple) |

**Service account JSON on Render:** do **not** commit the key. Use **Environment → Secret Files**: upload your JSON and note the **mount path** Render shows (often under `/etc/secrets/`). Set `GOOGLE_SERVICE_ACCOUNT_FILE` to that **exact path** (e.g. `/etc/secrets/google-service-account.json`).

Deploy and copy the API URL, e.g. `https://drive-search-api.onrender.com`.

### 3) Create the **Streamlit** service

1. **New → Web Service →** same repo.
2. Use the **same Root Directory** rule as the API (empty vs `google-drive-ai-agent`).
3. **Dockerfile Path:** `frontend/Dockerfile`
4. **Docker build context:** `frontend`

**Environment:**

| Key | Value |
|-----|--------|
| `BACKEND_URL` | `https://<your-api-name>.onrender.com` (HTTPS, no trailing slash) |

Redeploy if needed. Open the Streamlit URL and chat.

### 4) Optional: Blueprint

Repo root may include **`render.yaml`**. Paths in that file are relative to the **Git repo root**. If your app is nested (e.g. `google-drive-ai-agent/backend`), the committed `render.yaml` uses `./google-drive-ai-agent/...`. If your repo root **is** the app folder only, edit `render.yaml` and remove the `google-drive-ai-agent/` prefix from `dockerfilePath` and `dockerContext`.

Use **New → Blueprint** to create both services; then fill **sync: false** secrets in the dashboard (`OPENAI_API_KEY`, paths, `CORS_ORIGINS`, `BACKEND_URL`).

### Render build error: `lstat .../backend: no such file or directory`

Render is looking for `backend/` at the **wrong** place. Fix one of these:

- Set **Root Directory** to `google-drive-ai-agent` (if that is the folder that contains `backend/` and `frontend/` in your GitHub repo), **or**
- Push a repo whose **root** is the `google-drive-ai-agent` folder (so `backend/` exists at the top level), **or**
- If you use Blueprint, align `dockerfilePath` / `dockerContext` in `render.yaml` with your real folder names.

### Notes

- **Cold starts:** Free tier sleeps idle services; first request can take ~30–60s.
- **Order:** Deploy API first → set `BACKEND_URL` on UI → set `CORS_ORIGINS` on API to the UI URL → redeploy API if CORS blocks the browser.

## Example queries

- “Find resumes”
- “PDFs about finance modified in April”
- “Search inside files for ‘budget’”
- “Show only spreadsheets from last week”
- Follow-up: “Now narrow to marketing” / “Only PDFs” / “Sort idea: show the newest first” (the agent will refine the Drive `q`)

## Screenshots

> Add your own screenshots here after first successful run (Drive + OpenAI configured):
>
> 1. Streamlit chat with results expanded  
> 2. FastAPI `/docs` showing `POST /chat`

## Tech stack

- **FastAPI**: HTTP API, validation, CORS, streaming response.
- **LangGraph**: cyclic agent + tool execution with memory-friendly message reducers.
- **LangChain OpenAI**: chat model + tool binding + embeddings (re-rank).
- **Google API Python Client**: `drive.files().list` with `q`.
- **Streamlit**: rapid polished UI with custom CSS.

## Reliability & security notes

- Never commit service account JSON or `.env`.
- The backend **always** appends folder scope + `trashed=false` in `drive_service.py` even if the model forgets.
- Rate limits and invalid `q` strings surface as **user-safe** errors.

## Future improvements

- **Vector index** (Chroma/FAISS) over file text for true corpus semantic search beyond re-ranking.
- **Shared session store** (Redis) for multi-worker deployments.
- **OAuth user delegation** instead of a service account where appropriate.
- **Inline file preview** via Drive export where MIME types allow.
- **Stronger query validation** / sandboxing for `q` fragments.


