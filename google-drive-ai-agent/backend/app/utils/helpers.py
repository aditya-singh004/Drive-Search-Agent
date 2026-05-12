"""Small reusable helpers (dates, MIME hints, string safety)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional


def new_session_id() -> str:
    """Generate a client-safe opaque session identifier."""
    return str(uuid.uuid4())


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_relative_date_phrase(phrase: str) -> Optional[str]:
    """
    Best-effort parse for common relative phrases → ISO date (UTC midnight).

    The LLM should emit explicit ISO datetimes in Drive `q`; this is only a
    fallback for utilities or tests.
    """
    p = phrase.strip().lower()
    today = utc_now().date()
    if p in {"today", "this day"}:
        d = today
    elif p in {"yesterday"}:
        d = today - timedelta(days=1)
    elif p in {"last week", "past week", "this week"}:
        d = today - timedelta(days=7)
    elif p in {"last month", "past month"}:
        d = today - timedelta(days=30)
    else:
        return None
    return f"{d.isoformat()}T00:00:00"


def escape_drive_query_value(value: str) -> str:
    """
    Escape single quotes for Drive `q` string literals.

    Drive uses backslash to escape quotes inside single-quoted strings.
    """
    return value.replace("\\", "\\\\").replace("'", "\\'")


def mime_friendly_label(mime: str) -> str:
    """Human-readable short label for common MIME types."""
    mapping = {
        "application/pdf": "PDF",
        "application/vnd.google-apps.document": "Google Doc",
        "application/vnd.google-apps.spreadsheet": "Google Sheet",
        "application/vnd.google-apps.presentation": "Google Slides",
        "application/vnd.google-apps.folder": "Folder",
        "image/png": "PNG Image",
        "image/jpeg": "JPEG Image",
        "image/gif": "GIF Image",
        "text/plain": "Text",
        "text/csv": "CSV",
    }
    return mapping.get(mime, mime.split("/")[-1].replace(".", " ").title())


def suggest_followups(last_query_summary: str) -> list[str]:
    """Generate lightweight suggestion chips for the UI."""
    base = [
        "Show only PDFs",
        "Only files modified this week",
        "Search inside file content for 'budget'",
        "Narrow to spreadsheets",
    ]
    if "pdf" in last_query_summary.lower():
        return ["Show Google Docs instead", "Newest first", "Files from last month"] + base[:2]
    return base
