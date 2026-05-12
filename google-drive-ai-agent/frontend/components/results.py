"""Render Google Drive search results as polished cards."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st


def mime_badge(mime: str) -> str:
    """Small emoji + label for common MIME types."""
    m = (mime or "").lower()
    if "pdf" in m:
        return "📄 PDF"
    if "spreadsheet" in m or "sheet" in m:
        return "📊 Sheet"
    if "document" in m:
        return "📝 Doc"
    if "presentation" in m:
        return "📽️ Slides"
    if m.startswith("image/"):
        return "🖼️ Image"
    if "csv" in m:
        return "📑 CSV"
    return "📁 File"


def render_result_cards(results: list[dict[str, Any]]) -> None:
    """Display a responsive grid of file cards with open links."""
    if not results:
        st.info("No files matched this query.")
        return

    cols = st.columns(2)
    for idx, item in enumerate(results):
        c = cols[idx % 2]
        with c:
            name = html.escape(item.get("name", "Untitled"))
            mime = item.get("mimeType", "")
            modified = html.escape(item.get("modifiedTime", ""))
            link = item.get("webViewLink") or "#"

            st.markdown(
                f"""
                <div class="gdrive-card">
                  <div class="gdrive-card-title">{name}</div>
                  <div class="gdrive-card-meta">{mime_badge(mime)} · <span class="muted">{modified}</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if link and link != "#":
                st.link_button("Open in Drive", link, use_container_width=True)
            else:
                st.caption("No preview link available.")
