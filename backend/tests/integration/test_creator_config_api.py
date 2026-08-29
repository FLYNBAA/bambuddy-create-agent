from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_creator_config_rejects_unsafe_provider_url_with_client_error(async_client) -> None:
    response = await async_client.put(
        "/api/v1/creator/config",
        json={"deepseek_base_url": "file:///etc/passwd"},
    )

    assert response.status_code == 422
    assert "DeepSeek base URL" in response.json()["detail"]
