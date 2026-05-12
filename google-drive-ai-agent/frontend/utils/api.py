"""HTTP client helpers for talking to the FastAPI backend."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

import httpx


def post_chat(
    *,
    base_url: str,
    message: str,
    session_id: Optional[str],
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Call POST /chat and return JSON."""
    url = base_url.rstrip("/") + "/chat"
    payload: dict[str, Any] = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def astream_chat(
    *,
    base_url: str,
    message: str,
    session_id: Optional[str],
    timeout_s: float = 120.0,
) -> AsyncIterator[dict[str, Any]]:
    """Consume POST /chat/stream as NDJSON objects."""
    url = base_url.rstrip("/") + "/chat/stream"
    payload: dict[str, Any] = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = (line or "").strip()
                if not line:
                    continue
                yield json.loads(line)
