from __future__ import annotations

import io
import zipfile

import pytest
from PIL import Image


def _model_3mf() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(
            "3D/3dmodel.model",
            '<model><resources><basematerials><base name="Blue" displaycolor="#3366CC" /></basematerials></resources></model>',
        )
        archive.writestr("Metadata/project_settings.config", '{"filament_colour":["#3366CC"]}')
        archive.writestr("Metadata/plate_1.png", _reference_png())
    return output.getvalue()


def _reference_png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1, 1), "#3366CC").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_direct_task_upload_persists_custom_metadata_and_reference_image(async_client, monkeypatch, tmp_path) -> None:
    import backend.app.api.routes.bca_tasks as bca_tasks

    monkeypatch.setattr(bca_tasks.settings, "base_dir", tmp_path)
    response = await async_client.post(
        "/api/v1/bca-tasks",
        data={
            "title": "蓝白猫咪摆件",
            "customer_name": "张三",
            "phone": "13800138000",
            "address": "深圳市南山区",
            "notes": "请保留完整底座",
            "price": "128.00 CNY",
        },
        files={
            "file": ("model.3mf", _model_3mf(), "model/3mf"),
            "reference_image": ("reference.png", _reference_png(), "image/png"),
        },
    )

    assert response.status_code == 201, response.text
    task = response.json()
    assert task["title"] == "蓝白猫咪摆件"
    assert task["customer_name"] == "张三"
    assert task["phone"] == "13800138000"
    assert task["address"] == "深圳市南山区"
    assert task["notes"] == "请保留完整底座"
    assert task["style_image_preview_url"] == f"/api/v1/bca-tasks/{task['id']}/style-image"
    assert task["model_preview_url"] is None
    assert task["source_3mf_url"] == f"/api/v1/bca-tasks/{task['id']}/source"
    assert task["source_3mf_snapshot_url"] == f"/api/v1/bca-tasks/{task['id']}/snapshot"

    snapshot = await async_client.get(task["source_3mf_snapshot_url"])
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.headers["content-type"] == "image/png"
    assert snapshot.content == _reference_png()

@pytest.mark.asyncio
async def test_direct_task_upload_rejects_glb(async_client) -> None:
    response = await async_client.post(
        "/api/v1/bca-tasks",
        files={"file": ("model.glb", b"glTF", "model/gltf-binary")},
    )

    assert response.status_code == 422
    assert "GLB" in response.json()["detail"]
