"""Chat bubble rendering and typing indicator helpers."""

from __future__ import annotations

import html
from typing import Literal

import streamlit as st


Role = Literal["user", "assistant"]


def render_message_bubble(role: Role, content: str) -> None:
    """Render a single chat bubble with role-specific styling."""
    css_class = "msg-user" if role == "user" else "msg-assistant"
    label = "You" if role == "user" else "Agent"
    safe = html.escape(content or "")
    st.markdown(
        f"""
        <div class="chat-row {css_class}">
          <div class="chat-bubble">
            <div class="chat-label">{label}</div>
            <div class="chat-text">{safe}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def typing_indicator() -> None:
    """Lightweight animated typing dots (CSS-driven)."""
    st.markdown(
        """
        <div class="typing-indicator" aria-live="polite">
          <span></span><span></span><span></span>
        </div>
        """,
        unsafe_allow_html=True,
    )
