"""
Streamlit chat UI for the Google Drive AI Agent.

Run (from repo root):
  streamlit run frontend/app.py
"""

from __future__ import annotations

import asyncio
import html
import os
import sys
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv

# Ensure `frontend/` is importable when launching via `streamlit run frontend/app.py`
_FRONTEND_DIR = Path(__file__).resolve().parent
if str(_FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(_FRONTEND_DIR))

from components.chat import render_message_bubble, typing_indicator
from components.results import render_result_cards
from utils.api import astream_chat, post_chat


def load_css() -> None:
    css_path = _FRONTEND_DIR / "styles" / "custom.css"
    if css_path.is_file():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []  # list[dict]: role, content, results?, meta?
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None


def hero() -> None:
    st.markdown(
        """
        <div class="app-hero">
          <div>
            <h1>Google Drive Search Agent</h1>
            <p>Ask in natural language — the agent builds Drive <code>q</code> queries, searches your folder, and explains results.</p>
          </div>
          <div class="pill">🔎 LangGraph · FastAPI · GPT-4o-mini</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar() -> tuple[str, bool, bool, bool, bool]:
    load_dotenv()
    default_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    with st.sidebar:
        st.header("Configuration")
        base_url = st.text_input("Backend URL", value=default_url, help="FastAPI base URL (no trailing slash).")
        use_stream = st.toggle("Streaming responses", value=False, help="Uses /chat/stream for token-like chunks.")
        show_logs = st.toggle("Show tool logs", value=False)
        show_explain = st.toggle("Show query explanation", value=True)
        show_suggestions = st.toggle("Show next-step suggestions", value=True)

        st.divider()
        st.caption("Suggestions")
        for i, q in enumerate(
            [
                "Find PDF reports from last month",
                "Search inside files for 'budget'",
                "Show spreadsheets modified this week",
                "Find images named screenshot",
            ]
        ):
            if st.button(q, key=f"sug_{i}", use_container_width=True):
                st.session_state.pending_prompt = q

        st.divider()
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = None
            st.session_state.pending_prompt = None
            st.rerun()

        return base_url, use_stream, show_logs, show_explain, show_suggestions


async def run_streaming_turn(base_url: str, prompt: str) -> dict:
    """Consume NDJSON stream and return final payload."""
    final: dict | None = None
    placeholder = st.empty()
    accumulated = ""
    async for evt in astream_chat(base_url=base_url, message=prompt, session_id=st.session_state.session_id):
        if evt.get("type") == "meta":
            st.session_state.session_id = evt.get("session_id")
        elif evt.get("type") == "token":
            accumulated += evt.get("text", "")
            safe = html.escape(accumulated)
            placeholder.markdown(
                f'<div class="chat-row msg-assistant"><div class="chat-bubble">'
                f'<div class="chat-label">Agent</div><div class="chat-text">{safe}</div>'
                f"</div></div>",
                unsafe_allow_html=True,
            )
        elif evt.get("type") == "final":
            final = evt
        elif evt.get("type") == "error":
            raise RuntimeError(evt.get("detail", "Unknown streaming error"))
    placeholder.empty()
    if not final:
        raise RuntimeError("Stream ended without final payload")
    return final


def main() -> None:
    st.set_page_config(page_title="Drive Search Agent", page_icon="📂", layout="wide")
    load_css()
    init_session_state()
    base_url, use_stream, show_logs, show_explain, show_suggestions = sidebar()
    hero()

    chat_box = st.container()
    with chat_box:
        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)
        for mi, m in enumerate(st.session_state.messages):
            render_message_bubble(m["role"], m["content"])
            if m["role"] == "assistant" and m.get("results"):
                with st.expander(f"Results ({len(m['results'])})", expanded=True):
                    render_result_cards(m["results"])
            if show_suggestions and m["role"] == "assistant" and m.get("meta", {}).get("suggestions"):
                st.caption("Try next")
                cols = st.columns(2)
                for si, s in enumerate(m["meta"]["suggestions"][:6]):
                    if cols[si % 2].button(s, key=f"sg_{mi}_{si}", use_container_width=True):
                        st.session_state.pending_prompt = s
            if show_logs and m.get("meta", {}).get("tool_logs"):
                with st.expander("Tool logs", expanded=False):
                    for line in m["meta"]["tool_logs"]:
                        st.code(line)
            if show_explain and m.get("meta", {}).get("query_explanation"):
                st.caption(f"Query explanation: {m['meta']['query_explanation']}")
        st.markdown("</div>", unsafe_allow_html=True)

    prompt = st.chat_input("Ask anything about your Drive folder…", key="chat_input")
    if st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})

        try:
            status = st.status("Thinking…", expanded=False)
            with status:
                typing_indicator()
                if use_stream:
                    final = asyncio.run(run_streaming_turn(base_url, prompt))
                    st.session_state.session_id = final.get("session_id")
                    assistant = final.get("response", "")
                    results = final.get("results", []) or []
                    meta = {
                        "tool_logs": final.get("tool_logs") or [],
                        "query_explanation": final.get("query_explanation"),
                        "drive_q_used": final.get("drive_q_used"),
                        "semantic_ranked": final.get("semantic_ranked"),
                        "error": final.get("error"),
                        "suggestions": final.get("suggestions") or [],
                    }
                else:
                    data = post_chat(
                        base_url=base_url,
                        message=prompt,
                        session_id=st.session_state.session_id,
                    )
                    st.session_state.session_id = data.get("session_id")
                    assistant = data.get("response", "")
                    results = data.get("results", []) or []
                    meta = {
                        "tool_logs": data.get("tool_logs") or [],
                        "query_explanation": data.get("query_explanation"),
                        "drive_q_used": data.get("drive_q_used"),
                        "semantic_ranked": data.get("semantic_ranked"),
                        "error": data.get("error"),
                        "suggestions": data.get("suggestions") or [],
                    }
            status.update(label="Done", state="complete")

            st.session_state.messages.append(
                {"role": "assistant", "content": assistant, "results": results, "meta": meta}
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            st.error(f"Backend error ({exc.response.status_code}): {detail}")
            st.session_state.messages.append(
                {"role": "assistant", "content": f"⚠️ Backend error ({exc.response.status_code}).", "results": [], "meta": {}}
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Request failed: {exc}")
            st.session_state.messages.append(
                {"role": "assistant", "content": f"⚠️ {exc}", "results": [], "meta": {}}
            )
        st.rerun()


if __name__ == "__main__":
    main()
