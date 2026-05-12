"""Optional semantic re-ranking of Drive results using embeddings."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import numpy as np
from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


async def rerank_files_by_query(
    user_text: str,
    files: list[dict[str, Any]],
    *,
    settings: Optional[Settings] = None,
) -> list[dict[str, Any]]:
    """
    Re-order files by embedding similarity between the user query and each name.

    Falls back to original order on any failure (network, quota, etc.).
    """
    cfg = settings or get_settings()
    if not cfg.enable_semantic_rerank or not files:
        return files

    try:
        embedder = OpenAIEmbeddings(
            api_key=cfg.openai_api_key,
            model="text-embedding-3-small",
        )

        def _embed_sync() -> tuple[list[float], list[list[float]]]:
            q_vec = embedder.embed_query(user_text)
            docs = [f"{f.get('name', '')} {f.get('mimeType', '')}" for f in files]
            doc_vecs = embedder.embed_documents(docs)
            return q_vec, doc_vecs

        q_vec, doc_vecs = await asyncio.to_thread(_embed_sync)
        q = np.array(q_vec, dtype=np.float32)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row, f in zip(doc_vecs, files, strict=False):
            s = _cosine_sim(q, np.array(row, dtype=np.float32))
            scored.append((s, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored]
    except Exception:  # noqa: BLE001
        logger.warning("Semantic re-rank skipped due to error", exc_info=True)
        return files
