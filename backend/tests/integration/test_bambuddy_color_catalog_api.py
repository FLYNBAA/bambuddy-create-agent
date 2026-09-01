"""Integration coverage for selective built-in Bambu Lab color imports."""

import pytest
from httpx import AsyncClient


def _identity(entry: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(entry["manufacturer"]).strip().casefold(),
        str(entry["color_name"]).strip().casefold(),
        str(entry["hex_color"]).strip().lstrip("#").casefold(),
        str(entry["material"]).strip().casefold(),
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bambuddy_import_deduplicates_requested_selection(async_client: AsyncClient):
    """Repeated stable keys add one default row and remain idempotent."""
    available = await async_client.get("/api/v1/inventory/colors/bambuddy")
    assert available.status_code == 200, available.text
    selected = available.json()[0]

    first_import = await async_client.post(
        "/api/v1/inventory/colors/bambuddy/import",
        json={"selection_keys": [selected["selection_key"], selected["selection_key"]]},
    )
    assert first_import.status_code == 200, first_import.text
    assert first_import.json() == {"imported": 1, "skipped": 0}

    second_import = await async_client.post(
        "/api/v1/inventory/colors/bambuddy/import",
        json={"selection_keys": [selected["selection_key"]]},
    )
    assert second_import.status_code == 200, second_import.text
    assert second_import.json() == {"imported": 0, "skipped": 1}

    catalog = await async_client.get("/api/v1/inventory/colors")
    assert catalog.status_code == 200, catalog.text
    matches = [entry for entry in catalog.json() if _identity(entry) == _identity(selected)]
    assert len(matches) == 1
    assert matches[0]["is_default"] is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bambuddy_import_rejects_unknown_selection_without_partial_insert(async_client: AsyncClient):
    """Selection validation happens before the transaction can create any rows."""
    available = await async_client.get("/api/v1/inventory/colors/bambuddy")
    assert available.status_code == 200, available.text
    selected = available.json()[0]

    response = await async_client.post(
        "/api/v1/inventory/colors/bambuddy/import",
        json={"selection_keys": [selected["selection_key"], "bambuddy:not-a-built-in-color"]},
    )
    assert response.status_code == 422

    catalog = await async_client.get("/api/v1/inventory/colors")
    assert catalog.status_code == 200, catalog.text
    assert not any(_identity(entry) == _identity(selected) for entry in catalog.json())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bambuddy_import_bounds_selection_count(async_client: AsyncClient):
    """The import request rejects oversized selection lists before processing them."""
    available = await async_client.get("/api/v1/inventory/colors/bambuddy")
    assert available.status_code == 200, available.text
    selection_key = available.json()[0]["selection_key"]

    response = await async_client.post(
        "/api/v1/inventory/colors/bambuddy/import",
        json={"selection_keys": [selection_key] * 501},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bambuddy_import_preserves_matching_custom_entry(async_client: AsyncClient):
    """A matching custom row makes the built-in unavailable and is never overwritten."""
    available = await async_client.get("/api/v1/inventory/colors/bambuddy")
    assert available.status_code == 200, available.text
    selected = available.json()[0]
    custom = await async_client.post(
        "/api/v1/inventory/colors",
        json={
            "manufacturer": selected["manufacturer"],
            "color_name": selected["color_name"],
            "hex_color": selected["hex_color"],
            "material": selected["material"],
            "extra_colors": "ffffff,eeeeee",
            "effect_type": "glow",
        },
    )
    assert custom.status_code == 200, custom.text

    import_response = await async_client.post(
        "/api/v1/inventory/colors/bambuddy/import",
        json={"selection_keys": [selected["selection_key"]]},
    )
    assert import_response.status_code == 200, import_response.text
    assert import_response.json() == {"imported": 0, "skipped": 1}

    catalog = await async_client.get("/api/v1/inventory/colors")
    assert catalog.status_code == 200, catalog.text
    matches = [entry for entry in catalog.json() if _identity(entry) == _identity(selected)]
    assert len(matches) == 1
    assert matches[0]["id"] == custom.json()["id"]
    assert matches[0]["is_default"] is False
    assert matches[0]["extra_colors"] == "ffffff,eeeeee"
    assert matches[0]["effect_type"] == "glow"

    refreshed_available = await async_client.get("/api/v1/inventory/colors/bambuddy")
    assert refreshed_available.status_code == 200, refreshed_available.text
    refreshed = next(entry for entry in refreshed_available.json() if entry["selection_key"] == selected["selection_key"])
    assert refreshed["exists"] is True
