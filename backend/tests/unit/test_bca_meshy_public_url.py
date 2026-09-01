from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.three_d_agent.config import Settings
from backend.app.three_d_agent.providers.exceptions import ProviderError
from backend.app.three_d_agent.providers.meshy import MeshyPrintProvider


def test_meshy_public_url_uses_independent_provider_capability(tmp_path) -> None:
    provider = MeshyPrintProvider(
        Settings(
            data_dir=tmp_path,
            app_public_base_url="https://bca.example.test",
            meshy_model_input_mode="public_url",
        )
    )

    with patch("backend.app.three_d_agent.providers.meshy.assert_public_http_url"):
        public_url = provider._public_model_url("session-id", "model", "independent-capability-token-123456")

    assert public_url == (
        "https://bca.example.test/api/v1/creator/sessions/session-id/"
        "provider/independent-capability-token-123456/model.glb"
    )


def test_meshy_base_url_normalizes_surrounding_whitespace(tmp_path) -> None:
    provider = MeshyPrintProvider(
        Settings(data_dir=tmp_path, meshy_base_url="  https://relay.example.test/root/  ")
    )

    assert provider._api_base_url() == "https://relay.example.test/root"


def test_meshy_accepts_artifacts_from_exact_configured_http_relay(tmp_path) -> None:
    provider = MeshyPrintProvider(
        Settings(data_dir=tmp_path, meshy_base_url="http://192.166.82.66:8001")
    )

    assert provider._model_url(
        {"model_urls": {"3mf": "http://192.166.82.66:8001/files/result.3mf"}},
        "3mf",
    ) == "http://192.166.82.66:8001/files/result.3mf"


def test_meshy_rejects_artifact_from_unconfigured_http_origin(tmp_path) -> None:
    provider = MeshyPrintProvider(
        Settings(data_dir=tmp_path, meshy_base_url="http://192.166.82.66:8001")
    )

    with pytest.raises(ProviderError, match="invalid model URL"):
        provider._model_url(
            {"model_urls": {"3mf": "http://192.166.82.67:8001/files/result.3mf"}},
            "3mf",
        )


@pytest.mark.asyncio
async def test_meshy_submission_posts_are_never_automatically_retried(tmp_path) -> None:
    provider = MeshyPrintProvider(Settings(data_dir=tmp_path))
    observed: list[bool] = []

    async def request(_method, _path, *, safe_to_retry=False, **_kwargs):
        observed.append(safe_to_retry)
        return {"result": "task-id"}

    provider._request = request

    assert await provider._submit("analyze", {"model_url": "data:model/gltf-binary;base64,AA=="}) == "task-id"
    assert observed == [False]
