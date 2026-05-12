"""LangGraph agent state definition."""

from __future__ import annotations

from typing import Annotated, Any, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Graph state: chat messages plus structured side channels for the API layer.

    `add_messages` reducer appends new messages from each node.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    structured_results: list[dict[str, Any]]
    last_drive_q: str
    tool_execution_logs: list[str]
    query_explanation: str
    user_query_text: str
