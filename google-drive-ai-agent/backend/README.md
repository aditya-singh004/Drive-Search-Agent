# Backend (FastAPI + LangGraph)

This service exposes the conversational agent and Google Drive search tool.

## Quick start

From this directory (`backend/`):

1. Create a virtual environment (recommended) and install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in values.

3. Run the API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open docs at `http://127.0.0.1:8000/docs`.

## Notes

- The LangGraph workflow lives in `app/agent/graph.py`.
- Drive queries are always scoped to `GOOGLE_DRIVE_FOLDER_ID` inside `app/services/drive_service.py`.
- For full project documentation, see the repository root `README.md`.
