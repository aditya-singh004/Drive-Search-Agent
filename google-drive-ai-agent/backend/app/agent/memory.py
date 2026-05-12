"""In-memory conversation store for multi-turn sessions."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Optional

from langchain_core.messages import BaseMessage

from app.utils.helpers import new_session_id

_MAX_MESSAGES = 80
_SESSION_TTL_SEC = 60 * 60 * 6  # 6 hours
_MAX_SESSIONS = 2000


class _Session:
    __slots__ = ("messages", "last_touch")

    def __init__(self) -> None:
        self.messages: Deque[BaseMessage] = deque(maxlen=_MAX_MESSAGES)
        self.last_touch: float = time.time()

    def touch(self) -> None:
        self.last_touch = time.time()


class ConversationMemory:
    """
    Thread-safe session → message history.

    For production, replace with Redis or another shared store.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, _Session] = {}

    def get_or_create_session(self, session_id: Optional[str]) -> tuple[str, _Session]:
        with self._lock:
            self._evict_stale_unlocked()
            sid = session_id or new_session_id()
            sess = self._sessions.get(sid)
            if sess is None:
                if len(self._sessions) >= _MAX_SESSIONS:
                    self._evict_oldest_unlocked()
                sess = _Session()
                self._sessions[sid] = sess
            sess.touch()
            return sid, sess

    def append(self, session_id: str, message: BaseMessage) -> None:
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                sess = _Session()
                self._sessions[session_id] = sess
            sess.messages.append(message)
            sess.touch()

    def extend(self, session_id: str, messages: list[BaseMessage]) -> None:
        for m in messages:
            self.append(session_id, m)

    def snapshot(self, session_id: str) -> list[BaseMessage]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return []
            sess.touch()
            return list(sess.messages)

    def _evict_stale_unlocked(self) -> None:
        now = time.time()
        dead = [sid for sid, s in self._sessions.items() if now - s.last_touch > _SESSION_TTL_SEC]
        for sid in dead:
            self._sessions.pop(sid, None)

    def _evict_oldest_unlocked(self) -> None:
        if not self._sessions:
            return
        sid = min(self._sessions.items(), key=lambda kv: kv[1].last_touch)[0]
        self._sessions.pop(sid, None)


memory_store = ConversationMemory()
