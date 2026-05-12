"""LangGraph conversational agent with tool calling for Google Drive search."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.agent.tools import DriveToolContext, build_search_google_drive_tool
from app.core.config import Settings, get_settings
from app.services.drive_service import DriveService

logger = logging.getLogger(__name__)


def _extract_tool_calls(message: BaseMessage) -> list[dict[str, Any]]:
    """Normalize tool_calls from AIMessage across LangChain versions."""
    tc = getattr(message, "tool_calls", None) or []
    out: list[dict[str, Any]] = []
    for call in tc:
        if isinstance(call, dict):
            out.append(call)
        else:
            out.append(
                {
                    "name": getattr(call, "name", ""),
                    "args": getattr(call, "args", {}),
                    "id": getattr(call, "id", ""),
                }
            )
    return out


class DriveSearchAgent:
    """Compiles and runs the LangGraph agent."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        drive: Optional[DriveService] = None,
    ):
        self.settings = settings or get_settings()
        self.drive = drive or DriveService(self.settings)

    def _build_graph(self, tool_ctx: DriveToolContext):
        tool = build_search_google_drive_tool(self.drive, ctx=tool_ctx)
        tools = [tool]
        llm = ChatOpenAI(
            model=self.settings.openai_model,
            temperature=0.2,
            api_key=self.settings.openai_api_key,
        ).bind_tools(tools)

        async def agent_node(state: AgentState) -> dict[str, Any]:
            response = await llm.ainvoke(state["messages"])
            return {"messages": [response]}

        async def tools_node(state: AgentState) -> dict[str, Any]:
            last = state["messages"][-1]
            calls = _extract_tool_calls(last)
            outs: list[ToolMessage] = []
            for call in calls:
                name = call.get("name")
                call_id = call.get("id") or "call"
                args = call.get("args") or {}
                if name != "search_google_drive":
                    outs.append(
                        ToolMessage(
                            content=json.dumps({"error": f"unknown tool {name}"}),
                            tool_call_id=str(call_id),
                        )
                    )
                    continue
                q_query = args.get("q_query", "") or ""
                expl = args.get("query_explanation", "") or ""
                content = await tool.ainvoke({"q_query": q_query, "query_explanation": expl})
                outs.append(ToolMessage(content=str(content), tool_call_id=str(call_id)))

            return {
                "messages": outs,
                "structured_results": tool_ctx.structured_results,
                "last_drive_q": tool_ctx.last_composed_q or tool_ctx.last_fragment,
                "tool_execution_logs": list(tool_ctx.tool_logs),
                "query_explanation": tool_ctx.query_explanation,
            }

        def route_after_agent(state: AgentState) -> Literal["tools", "__end__"]:
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and _extract_tool_calls(last):
                return "tools"
            return END  # type: ignore[return-value]

        graph = StateGraph(AgentState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tools_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
            "agent",
            route_after_agent,
            {"tools": "tools", END: END},
        )
        graph.add_edge("tools", "agent")
        return graph.compile()

    async def run(
        self,
        *,
        user_text: str,
        history: Sequence[BaseMessage],
        tool_ctx: DriveToolContext,
    ) -> tuple[str, AgentState]:
        """Execute one conversational turn. Returns (assistant_text, final_state)."""
        tool_ctx.user_utterance = user_text
        graph = self._build_graph(tool_ctx)

        seed: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
        seed.extend(list(history))
        seed.append(HumanMessage(content=user_text))

        initial: AgentState = {
            "messages": seed,
            "structured_results": [],
            "last_drive_q": "",
            "tool_execution_logs": [],
            "query_explanation": "",
            "user_query_text": user_text,
        }

        final = await graph.ainvoke(initial)
        messages = final["messages"]
        last_ai: Optional[AIMessage] = None
        for m in reversed(messages):
            if isinstance(m, AIMessage):
                last_ai = m
                if not _extract_tool_calls(m):
                    break
        assistant_text = (last_ai.content if last_ai else "") or ""
        if isinstance(assistant_text, list):
            assistant_text = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in assistant_text
            )
        return str(assistant_text), final
