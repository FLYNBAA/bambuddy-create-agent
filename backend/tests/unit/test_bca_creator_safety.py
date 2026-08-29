from __future__ import annotations

import pytest

from backend.app.api.routes.creator import _message_acknowledges_print_issues, _print_issues_require_acknowledgment
from backend.app.three_d_agent.contracts import (
    CreativeBrief,
    PrintabilityMetrics,
    PrintabilityReport,
    PrintAnalysisState,
    SessionSnapshot,
    SessionStatus,
)


def _snapshot(report_status: str) -> SessionSnapshot:
    return SessionSnapshot(
        session_id="session",
        status=SessionStatus.COMPLETED,
        brief=CreativeBrief(subject="cat", style="cute", product_type="figure"),
        print_analysis=PrintAnalysisState(
            report=PrintabilityReport(
                status=report_status,
                metrics=PrintabilityMetrics(
                    is_watertight=True,
                    volume=1,
                    non_manifold_edges=0,
                    degenerate_faces=0,
                    holes=0,
                ),
            )
        ),
    )


def test_print_issue_acknowledgment_is_required_only_for_non_healthy_reports() -> None:
    assert not _print_issues_require_acknowledgment(_snapshot("healthy"))
    assert _print_issues_require_acknowledgment(_snapshot("warning"))


def test_creator_provider_url_updates_reject_unsafe_schemes() -> None:
    from backend.app.api.routes.creator import CreatorConfigUpdate, _validate_creator_provider_urls

    with pytest.raises(ValueError, match="DeepSeek base URL"):
        _validate_creator_provider_urls(CreatorConfigUpdate(deepseek_base_url="file:///etc/passwd"))


def test_chat_requires_explicit_issue_acknowledgment_phrase() -> None:
    assert _message_acknowledges_print_issues("我已了解打印分析报告中的问题，确认继续")
    assert not _message_acknowledges_print_issues("确认继续生成多色 3MF")
