from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services.creator_integration import CreatorController
from backend.app.three_d_agent.contracts import SessionSnapshot, SessionStatus


@pytest.mark.asyncio
async def test_creator_stage_event_is_scoped_by_session_id(monkeypatch):
    sent = []

    async def capture(user_id, message):
        sent.append((user_id, message))

    controller = CreatorController.__new__(CreatorController)
    controller.agent = SimpleNamespace(
        get_session=lambda _session_id: SessionSnapshot(session_id="creator-session", status=SessionStatus.NEEDS_INPUT)
    )
    monkeypatch.setattr("backend.app.services.creator_integration.ws_manager.broadcast_to_user", capture)

    await controller._broadcast("creator-session", "images", "running")

    assert sent == [
        (
            None,
            {
                "type": "bca_creator_session",
                "session_id": "creator-session",
                "stage": "images",
                "event": "running",
                "status": "needs_input",
                "image_count": 0,
                "geometry_status": "not_started",
                "print_file_status": "not_started",
                "color_calibration_status": "not_started",
            },
        )
    ]
