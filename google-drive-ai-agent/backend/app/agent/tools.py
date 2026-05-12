"""LangChain tools for Google Drive search."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Optional

from langchain_core.tools import tool
from pydantic import Field

from app.core.config import get_settings
from app.services.drive_service import DriveService, DriveServiceError, format_tool_result_for_llm
from app.services.semantic_rerank import rerank_files_by_query

logger = logging.getLogger(__name__)


@dataclass
class DriveToolContext:
    """Per-request mutable context populated by tool execution (for API mapping)."""

    user_utterance: str = ""
    last_fragment: str = ""
    last_composed_q: str = ""
    structured_results: list[dict[str, Any]] = field(default_factory=list)
    query_explanation: str = ""
    tool_logs: list[str] = field(default_factory=list)
    semantic_ranked: bool = False
    last_error: Optional[str] = None


def build_search_google_drive_tool(
    drive: DriveService,
    *,
    ctx: DriveToolContext,
) -> object:
    """Build the bound `search_google_drive` tool."""

    @tool
    async def search_google_drive(
        q_query: Annotated[
            str,
            Field(
                description=(
                    "Drive `q` FRAGMENT only (no parents/trashed). "
                    "Combine mimeType, name contains, fullText contains, modifiedTime, etc."
                ),
            ),
        ],
        query_explanation: Annotated[
            str,
            Field(
                description="Short plain-English explanation of the search for the end user.",
            ),
        ],
    ) -> str:
        """Search the configured Google Drive folder using a Drive API `q` fragment."""
        ctx.last_fragment = q_query.strip()
        ctx.query_explanation = query_explanation.strip()
        ctx.last_error = None
        try:
            full_q, files = await drive.search(q_query)
            ctx.last_composed_q = full_q
            reranked = await rerank_files_by_query(ctx.user_utterance, files)
            ctx.structured_results = reranked
            cfg = get_settings()
            ctx.semantic_ranked = bool(cfg.enable_semantic_rerank and files)
            ctx.tool_logs.append(
                f"search_google_drive fragment={q_query!r} composed_q={full_q!r} n={len(reranked)}"
            )
            logger.info("Drive search ok composed_q=%s count=%s", full_q, len(reranked))
            return format_tool_result_for_llm(reranked)
        except DriveServiceError as exc:
            logger.warning("Drive search failed: %s", exc)
            ctx.last_composed_q = ctx.last_fragment
            ctx.structured_results = []
            ctx.semantic_ranked = False
            ctx.last_error = str(exc)
            ctx.tool_logs.append(f"search_google_drive ERROR: {exc}")
            return json.dumps(
                {"error": str(exc), "count": 0, "files": []},
                ensure_ascii=False,
            )

    return search_google_drive
