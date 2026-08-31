from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.app.models.settings import Settings


@pytest.mark.asyncio
@pytest.mark.integration
async def test_creator_config_rejects_unsafe_provider_url_with_client_error(async_client) -> None:
    response = await async_client.put(
        "/api/v1/creator/config",
        json={"deepseek_base_url": "file:///etc/passwd"},
    )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "private, no-store"
    assert "DeepSeek base URL" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_creator_config_persists_plaintext_provider_credentials(async_client, db_session) -> None:
    credentials = {
        "deepseek_api_key": "test-deepseek-plain",
        "image_api_key": "test-image-plain",
        "tencent_secret_id": "test-tencent-id",
        "tencent_secret_key": "test-tencent-key",
        "meshy_api_key": "test-meshy-plain",
    }

    response = await async_client.put("/api/v1/creator/config", json=credentials)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert {key: response.json()[key] for key in credentials} == credentials
    rows = await db_session.execute(
        select(Settings).where(Settings.key.in_([f"bca_creator_{key}" for key in credentials]))
    )
    assert {row.key.removeprefix("bca_creator_"): row.value for row in rows.scalars().all()} == credentials

    loaded = await async_client.get("/api/v1/creator/config")
    assert loaded.status_code == 200
    assert loaded.headers["cache-control"] == "private, no-store"
    assert {key: loaded.json()[key] for key in credentials} == credentials
