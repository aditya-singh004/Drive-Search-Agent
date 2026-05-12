"""FastAPI route definitions."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from openai import APIError as OpenAIAPIError

from app.agent.graph import DriveSearchAgent
from app.agent.memory import memory_store
from app.agent.tools import DriveToolContext
from app.core.config import get_settings
from app.models.schemas import ChatRequest, ChatResponse, DriveFileItem, HealthResponse
from app.services.drive_service import DriveServiceError
from app.utils.helpers import suggest_followups

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse()


@router.get("/ready")
async def ready() -> JSONResponse:
    """
    Readiness probe: validates configuration and Drive credential file presence.

    Returns 200 when the service can safely accept traffic.
    """
    try:
        settings = get_settings()
        path = settings.service_account_path
        if not path.is_file():
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "detail": f"Service account file missing: {path}",
                },
            )
        return JSONResponse(status_code=200, content={"ready": True})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Readiness check failed")
        return JSONResponse(
            status_code=503,
            content={"ready": False, "detail": str(exc)},
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """
    Conversational endpoint: LangGraph agent + optional Google Drive tool execution.

    Maintains multi-turn state when `session_id` is reused (or returned from a prior call).
    """
    settings = get_settings()
    session_id, _sess = memory_store.get_or_create_session(req.session_id)
    history = memory_store.snapshot(session_id)

    tool_ctx = DriveToolContext()
    agent = DriveSearchAgent(settings=settings)

    try:
        assistant_text, final = await agent.run(
            user_text=req.message.strip(),
            history=history,
            tool_ctx=tool_ctx,
        )
    except OpenAIAPIError as exc:
        status = getattr(exc, "status_code", None)
        if status in {401, 403}:
            logger.warning("OpenAI authentication failed: %s", exc)
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing OPENAI_API_KEY.",
            ) from exc
        raise
    except DriveServiceError as exc:
        logger.warning("Drive error during chat: %s", exc)
        return ChatResponse(
            response=(
                "I could not complete the Google Drive search. "
                f"Details: {exc} Please verify sharing with the service account."
            ),
            results=[],
            session_id=session_id,
            drive_q_used=tool_ctx.last_composed_q or None,
            tool_logs=list(tool_ctx.tool_logs),
            query_explanation=tool_ctx.query_explanation or None,
            semantic_ranked=False,
            error=str(exc),
            suggestions=suggest_followups(req.message),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled error in /chat")
        raise HTTPException(status_code=500, detail="Internal server error.") from exc

    memory_store.append(session_id, HumanMessage(content=req.message.strip()))
    memory_store.append(session_id, AIMessage(content=assistant_text))

    raw_results = final.get("structured_results") or []
    results: list[DriveFileItem] = []
    for r in raw_results:
        try:
            results.append(DriveFileItem.model_validate(r))
        except Exception:  # noqa: BLE001
            logger.debug("Skipping malformed Drive row: %s", r)

    suggestions = suggest_followups(req.message)
    if final.get("last_drive_q"):
        suggestions = suggest_followups(str(final.get("last_drive_q")))

    return ChatResponse(
        response=assistant_text,
        results=results,
        session_id=session_id,
        drive_q_used=final.get("last_drive_q") or tool_ctx.last_composed_q or None,
        tool_logs=list(final.get("tool_execution_logs") or tool_ctx.tool_logs),
        query_explanation=final.get("query_explanation") or tool_ctx.query_explanation or None,
        semantic_ranked=tool_ctx.semantic_ranked,
        error=tool_ctx.last_error,
        suggestions=suggestions,
    )


async def _ndjson_stream(req: ChatRequest) -> AsyncIterator[bytes]:
    """
    NDJSON stream for progressive UI updates.

    Emits:
    - {"type":"meta", ...}
    - {"type":"token","text": "..."} (word-chunked assistant text for a typing effect)
    - {"type":"final", ...} (structured payload mirroring ChatResponse fields)
    """
    settings = get_settings()
    session_id, _ = memory_store.get_or_create_session(req.session_id)
    history = memory_store.snapshot(session_id)
    tool_ctx = DriveToolContext()
    agent = DriveSearchAgent(settings=settings)

    yield (
        json.dumps({"type": "meta", "session_id": session_id}, ensure_ascii=False).encode("utf-8") + b"\n"
    )

    try:
        assistant_text, final = await agent.run(
            user_text=req.message.strip(),
            history=history,
            tool_ctx=tool_ctx,
        )
    except OpenAIAPIError as exc:
        status = getattr(exc, "status_code", None)
        detail = "Invalid OPENAI_API_KEY" if status in {401, 403} else str(exc)
        yield json.dumps({"type": "error", "detail": detail}, ensure_ascii=False).encode("utf-8") + b"\n"
        return
    except DriveServiceError as exc:
        yield json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False).encode("utf-8") + b"\n"
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Streaming chat failed")
        yield json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False).encode("utf-8") + b"\n"
        return

    for word in assistant_text.split():
        yield (
            json.dumps({"type": "token", "text": word + " "}, ensure_ascii=False).encode("utf-8") + b"\n"
        )

    memory_store.append(session_id, HumanMessage(content=req.message.strip()))
    memory_store.append(session_id, AIMessage(content=assistant_text))

    raw_results = final.get("structured_results") or []
    results: list[dict] = []
    for r in raw_results:
        try:
            results.append(DriveFileItem.model_validate(r).model_dump())
        except Exception:  # noqa: BLE001
            continue

    sug = suggest_followups(str(final.get("last_drive_q") or req.message))
    yield (
        json.dumps(
            {
                "type": "final",
                "response": assistant_text,
                "results": results,
                "session_id": session_id,
                "drive_q_used": final.get("last_drive_q") or tool_ctx.last_composed_q,
                "tool_logs": list(final.get("tool_execution_logs") or tool_ctx.tool_logs),
                "query_explanation": final.get("query_explanation") or tool_ctx.query_explanation,
                "semantic_ranked": tool_ctx.semantic_ranked,
                "error": tool_ctx.last_error,
                "suggestions": sug,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """NDJSON streaming endpoint (meta → token chunks → final payload)."""
    return StreamingResponse(_ndjson_stream(req), media_type="application/x-ndjson")
