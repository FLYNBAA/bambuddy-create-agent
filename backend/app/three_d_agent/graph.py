"""LangGraph workflow for the no-cost preparation phase."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from typing_extensions import NotRequired, TypedDict

from .contracts import BriefEnricher, CreativeBrief, PromptPackage
from .prompts import build_display_presentations, build_prompt_package, response_language


class PreparationState(TypedDict):
    """State passed through the brief preparation graph."""

    message: str
    current_brief: CreativeBrief
    has_reference_image: bool
    language: str
    brief: NotRequired[CreativeBrief]
    questions: NotRequired[list[object]]
    image_prompt: NotRequired[str | None]
    prompt_package: NotRequired[PromptPackage | None]
    presentation_en: NotRequired[str | None]
    presentation_zh: NotRequired[str | None]


def build_preparation_graph(enricher: BriefEnricher):
    """Compile the typed enrichment-to-clarification-or-prompt workflow."""

    async def enrich_brief(state: PreparationState) -> dict[str, CreativeBrief]:
        return {
            "brief": await enricher.enrich(
                state["message"],
                state["current_brief"],
                state["has_reference_image"],
            )
        }

    async def expand_brief(state: PreparationState) -> dict[str, object]:
        """Every input expands directly to final prompts; no clarification path."""
        package = build_prompt_package(state["brief"], state["language"])
        presentation_en, presentation_zh = build_display_presentations(state["brief"], state["language"])
        return {
            "questions": [],
            "image_prompt": package.image2_prompt,
            "prompt_package": package,
            "presentation_en": presentation_en,
            "presentation_zh": presentation_zh,
        }

    workflow = StateGraph(PreparationState)
    workflow.add_node("enrich_brief", enrich_brief)
    workflow.add_node("expand_brief", expand_brief)
    workflow.add_edge(START, "enrich_brief")
    workflow.add_edge("enrich_brief", "expand_brief")
    workflow.add_edge("expand_brief", END)
    return workflow.compile()


def prepare_graph_input(message: str, current_brief: CreativeBrief, has_reference_image: bool) -> dict[str, object]:
    """Keep the caller's response language stable across graph execution."""
    return {
        "message": message,
        "current_brief": current_brief,
        "has_reference_image": has_reference_image,
        "language": response_language(message, current_brief),
    }
