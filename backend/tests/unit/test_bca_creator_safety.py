from __future__ import annotations

import pytest

from backend.app.api.routes.creator import CreatorConfigUpdate, PrintCalibrationRequest, _validate_creator_provider_urls
from backend.app.three_d_agent.contracts import PrintAnalysisState


def test_creator_provider_url_updates_reject_unsafe_schemes() -> None:
    with pytest.raises(ValueError, match="DeepSeek base URL"):
        _validate_creator_provider_urls(CreatorConfigUpdate(deepseek_base_url="file:///etc/passwd"))
    with pytest.raises(ValueError, match="Meshy base URL"):
        _validate_creator_provider_urls(CreatorConfigUpdate(meshy_base_url="file:///etc/passwd"))


def test_calibration_contract_enforces_eight_color_limit() -> None:
    assert PrintCalibrationRequest(mode="white", max_colors=1).max_colors == 1
    with pytest.raises(ValueError):
        PrintCalibrationRequest(mode="multicolor", max_colors=9)


def test_print_analysis_contract_exposes_score_and_insights_without_recommendations() -> None:
    state = PrintAnalysisState(score=84, insights=["The final mesh is watertight."])
    assert state.model_dump() == {
        "status": "not_started",
        "report": None,
        "score": 84,
        "insights": ["The final mesh is watertight."],
        "error": None,
    }
    assert "recommendations" not in state.model_dump()
