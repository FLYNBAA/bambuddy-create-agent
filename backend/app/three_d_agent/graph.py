"""LangGraph workflow for the no-cost preparation phase."""

from __future__ import annotations

from typing import Literal
from typing_extensions import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from .contracts import BriefEnricher, ClarificationQuestion, CreativeBrief
from .prompts import build_print_aware_image_prompt, clarification_questions


class PreparationState(TypedDict):
    """State passed through the brief preparation graph."""

    message: str
    current_brief: CreativeBrief
    has_reference_image: bool
    brief: NotRequired[CreativeBrief]
    questions: NotRequired[list[ClarificationQuestion]]
    image_prompt: NotRequired[str | None]


def _merged_brief(current: CreativeBrief, extracted: CreativeBrief) -> CreativeBrief:
    """Retain existing choices when an enricher omits or clears a field."""
    return CreativeBrief(
        subject=extracted.subject or current.subject,
        style=extracted.style or current.style,
        product_type=extracted.product_type or current.product_type,
        details=extracted.details or current.details,
    )


def build_preparation_graph(enricher: BriefEnricher):
    """Compile the typed enrichment-to-clarification-or-prompt workflow."""

    async def enrich_brief(state: PreparationState) -> dict[str, CreativeBrief]:
        extracted = await enricher.enrich(
            state["message"],
            state["current_brief"],
            state["has_reference_image"],
        )
        return {"brief": _merged_brief(state["current_brief"], extracted)}

    def route_after_enrichment(
        state: PreparationState,
    ) -> Literal["clarify", "construct_prompt"]:
        return "construct_prompt" if state["brief"].is_complete else "clarify"

    def clarify(state: PreparationState) -> dict[str, object]:
        return {
            "questions": clarification_questions(state["brief"]),
            "image_prompt": None,
        }

    def construct_prompt(state: PreparationState) -> dict[str, object]:
        return {
            "questions": [],
            "image_prompt": build_print_aware_image_prompt(state["brief"]),
        }

    workflow = StateGraph(PreparationState)
    workflow.add_node("enrich_brief", enrich_brief)
    workflow.add_node("clarify", clarify)
    workflow.add_node("construct_prompt", construct_prompt)
    workflow.add_edge(START, "enrich_brief")
    workflow.add_conditional_edges(
        "enrich_brief",
        route_after_enrichment,
        {"clarify": "clarify", "construct_prompt": "construct_prompt"},
    )
    workflow.add_edge("clarify", END)
    workflow.add_edge("construct_prompt", END)
    return workflow.compile()
