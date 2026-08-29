from __future__ import annotations

from unittest.mock import patch

from backend.app.three_d_agent.config import Settings
from backend.app.three_d_agent.providers.meshy import MeshyPrintProvider


def test_meshy_public_url_uses_controlled_creator_glb_route(tmp_path) -> None:
    provider = MeshyPrintProvider(
        Settings(
            data_dir=tmp_path,
            app_public_base_url="https://bca.example.test",
            meshy_model_input_mode="public_url",
        )
    )

    with patch("backend.app.three_d_agent.providers.meshy.assert_public_http_url"):
        public_url = provider._public_model_url("session-id", "model")

    assert public_url == "https://bca.example.test/api/v1/creator/sessions/session-id/model.glb"
