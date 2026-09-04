from __future__ import annotations

import asyncio

import pytest
from backend.app.three_d_agent.contracts import BriefExtraction, CreativeBrief
from backend.app.three_d_agent.config import Settings
from backend.app.three_d_agent.graph import build_preparation_graph, prepare_graph_input
from backend.app.three_d_agent.prompts import (
    build_prompt_package,
    complete_brief,
    response_language,
)
from backend.app.three_d_agent.providers.deepseek import DeepSeekBriefEnricher


def test_response_language_uses_cjk_input_and_english_input() -> None:
    assert response_language("做一个猫咪摆件") == "zh"
    assert response_language("Create a cat figurine") == "en"


def test_complete_brief_auto_fills_missing_key_fields() -> None:
    brief = complete_brief(CreativeBrief(subject="猫"), "zh")

    assert brief.subject == "猫"
    assert brief.style
    assert brief.product_type
    assert brief.details


def test_chinese_prompt_package_expands_any_input_without_questions() -> None:
    package = build_prompt_package(CreativeBrief(subject="猫"), "zh")

    assert package.language == "zh"
    assert "猫" in package.positive_prompt
    assert "不要文字" in package.negative_prompt
    assert package.print_constraints
    assert "Image2" in package.image2_prompt


def test_english_prompt_package_expands_any_input_without_questions() -> None:
    package = build_prompt_package(CreativeBrief(subject="cat"), "en")

    assert package.language == "en"
    assert "cat" in package.positive_prompt
    assert "No text" in package.negative_prompt
    assert "Positive requirements" in package.image2_prompt


def test_language_switch_rebuilds_every_field_without_mixing_languages() -> None:
    provider = DeepSeekBriefEnricher(Settings())
    current = CreativeBrief(
        subject="cat",
        style="chibi",
        product_type="figurine",
        details="blue",
    )
    extraction = BriefExtraction(
        subject="猫",
        style="Q版",
        product_type="手办",
        details="蓝色",
        subject_zh="猫",
        style_zh="Q版",
        product_type_zh="手办",
        details_zh="蓝色",
    )

    result = provider._brief_in_language(extraction, current, "zh")

    assert result.subject == "猫"
    assert result.style == "Q版"
    assert result.product_type == "手办"
    assert result.details == "蓝色"
    assert result.subject_zh == "猫"


@pytest.mark.asyncio
async def test_minimal_chinese_input_expands_directly_to_final_prompts() -> None:
    class Enricher:
        async def enrich(self, *_args) -> CreativeBrief:
            return CreativeBrief(subject="猫")

    result = await build_preparation_graph(Enricher()).ainvoke(
        prepare_graph_input("猫", CreativeBrief(), False)
    )

    assert result["questions"] == []
    assert result["prompt_package"].language == "zh"
    assert "猫" in result["prompt_package"].positive_prompt
    assert result["image_prompt"] == result["prompt_package"].image2_prompt


@pytest.mark.asyncio
async def test_minimal_english_input_expands_directly_to_final_prompts() -> None:
    class Enricher:
        async def enrich(self, *_args) -> CreativeBrief:
            return CreativeBrief(subject="cat")

    result = await build_preparation_graph(Enricher()).ainvoke(
        prepare_graph_input("cat", CreativeBrief(), False)
    )

    assert result["questions"] == []
    assert result["prompt_package"].language == "en"
    assert "cat" in result["prompt_package"].positive_prompt
