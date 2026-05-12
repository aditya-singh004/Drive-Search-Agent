"""Pydantic models for API requests and responses."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class DriveFileItem(BaseModel):
    """Single file metadata returned from Google Drive."""

    id: str
    name: str
    mimeType: str
    modifiedTime: str
    webViewLink: Optional[str] = None


class ChatRequest(BaseModel):
    """Incoming chat message from the Streamlit client."""

    message: str = Field(..., min_length=1, description="User utterance.")
    session_id: Optional[str] = Field(
        default=None,
        description="Stable id for multi-turn memory; generated if omitted.",
    )


class ChatResponse(BaseModel):
    """Assistant reply with optional structured Drive hits."""

    response: str
    results: list[DriveFileItem] = Field(default_factory=list)
    session_id: str
    drive_q_used: Optional[str] = None
    tool_logs: list[str] = Field(default_factory=list)
    query_explanation: Optional[str] = None
    semantic_ranked: bool = False
    error: Optional[str] = None
    suggestions: list[str] = Field(
        default_factory=list,
        description="Lightweight next-step query ideas for the UI.",
    )


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"


class ErrorDetail(BaseModel):
    detail: str
    code: Optional[str] = None
    extra: Optional[dict[str, Any]] = None
