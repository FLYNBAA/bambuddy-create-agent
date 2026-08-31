"""Session-scoped LangGraph planner for the BCA creator chat surface."""

from __future__ import annotations

import json
from typing import Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from .config import Settings
from .contracts import ConversationMessage, SessionSnapshot
from .network import httpx_route_kwargs, proxy_route_candidates
from .providers.exceptions import ProviderConfigurationError, ProviderError


class CreatorCommand(BaseModel):
    action: Literal[
        "prepare",
        "confirm_images",
        "select_image",
        "confirm_3d",
        "analyze",
        "generate_print_file",
        "geometry",
        "calibrate",
        "restart_question",
    ] = "prepare"
    image_index: int | None = Field(default=None, ge=0, le=3)
    explicit_confirmation: bool = False
    acknowledge_issues: bool = False
    reply: str = Field(min_length=1, max_length=1000)


class ConversationState(TypedDict):
    session: SessionSnapshot
    message: str
    command: CreatorCommand


class CreatorConversationPlanner:
    """Use the configured free DeepSeek chat model to choose a safe workflow tool."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph = self._build_graph()

    async def plan(self, session: SessionSnapshot, message: str) -> CreatorCommand:
        result = await self._graph.ainvoke({"session": session, "message": message})
        return result["command"]

    def _build_graph(self):
        async def plan_command(state: ConversationState) -> dict[str, CreatorCommand]:
            return {"command": await self._invoke_model(state["session"], state["message"])}

        graph = StateGraph(ConversationState)
        graph.add_node("plan_command", plan_command)
        graph.add_edge(START, "plan_command")
        graph.add_edge("plan_command", END)
        return graph.compile()

    @staticmethod
    def _command_from_response(content: object, session: SessionSnapshot) -> CreatorCommand:
        """Normalize permissive JSON-mode output into one safe local action."""
        raw = content if isinstance(content, str) else str(content)
        try:
            start = raw.index("{")
            payload, _ = json.JSONDecoder().raw_decode(raw[start:])
        except (ValueError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        aliases = {
            "create": "prepare",
            "create_brief": "prepare",
            "generate_images": "confirm_images",
            "generate_image": "confirm_images",
            "generate_3d": "confirm_3d",
            "generate_model": "confirm_3d",
            "print": "generate_print_file",
            "generate_3mf": "generate_print_file",
        }
        action = aliases.get(str(payload.get("action", "")).strip().lower(), payload.get("action"))
        valid_actions = set(CreatorCommand.model_fields["action"].annotation.__args__)
        if action not in valid_actions:
            action = "prepare" if session.status.value in {"needs_input", "awaiting_image_confirmation"} else "restart_question"
        payload["action"] = action
        payload.setdefault(
            "reply",
            "已收到你的创意。我会先整理创作信息，再按确认门继续下一阶段。"
            if action == "prepare"
            else "请告诉我需要从创意、效果图、3D 模型还是打印处理哪个阶段重新开始。",
        )
        try:
            return CreatorCommand.model_validate(payload)
        except Exception:
            return CreatorCommand(
                action="prepare" if session.status.value in {"needs_input", "awaiting_image_confirmation"} else "restart_question",
                reply="已收到。请继续说明你的创意或选择需要重做的阶段。",
            )

    async def _invoke_model(self, session: SessionSnapshot, message: str) -> CreatorCommand:
        api_key = self._settings.deepseek_api_key.get_secret_value().strip()
        if not api_key:
            raise ProviderConfigurationError("DeepSeek API key is required for creator chat control.")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ProviderConfigurationError("langchain-openai is required for creator chat control.") from exc
        system = """You control a 3D-print creator workflow. Return exactly one JSON object and no markdown.
Choose exactly one action. prepare handles normal creative requests and revisions.
Paid actions confirm_images, confirm_3d, and generate_print_file require the user's
unambiguous explicit confirmation; set explicit_confirmation false otherwise.
select_image needs image_index 0..3. For generate_print_file, set acknowledge_issues
true only when the newest user message explicitly acknowledges the reported
print-analysis issues or risks. Never infer that acknowledgment from a request to continue.
restart_question never changes artifacts: it asks the user which stage to redo.
Never claim an artifact exists unless its session status says it does. Reply concisely in Chinese."""
        history = "\n".join(f"{turn.role}: {turn.content}" for turn in session.conversation[-16:])
        last_error: Exception | None = None
        for trust_env in proxy_route_candidates(self._settings.deepseek_proxy_mode):
            try:
                async with httpx.AsyncClient(
                    timeout=self._settings.deepseek_timeout_seconds,
                    **httpx_route_kwargs(trust_env),
                ) as client:
                    model = ChatOpenAI(
                        model=self._settings.deepseek_model,
                        api_key=api_key,
                        base_url=self._settings.deepseek_base_url.rstrip("/"),
                        timeout=self._settings.deepseek_timeout_seconds,
                        temperature=0,
                        http_async_client=client,
                        http_socket_options=(),
                    ).bind(response_format={"type": "json_object"})
                    response = await model.ainvoke(
                        [("system", system), ("human", f"Workflow status: {session.status.value}\nHistory:\n{history}\nNewest user message: {message}")]
                    )
                return self._command_from_response(response.content, session)
            except Exception as exc:
                last_error = exc
        raise ProviderError("Creator chat control could not reach DeepSeek.") from last_error


def append_message(snapshot: SessionSnapshot, role: Literal["user", "assistant"], content: str) -> None:
    snapshot.conversation.append(ConversationMessage(role=role, content=content.strip()))
    del snapshot.conversation[:-32]
