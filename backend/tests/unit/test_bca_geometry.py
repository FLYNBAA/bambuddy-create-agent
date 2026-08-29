from __future__ import annotations

import io
import json
import zipfile

from backend.app.three_d_agent.calibration import geometry_only_3mf, inspect_3mf


def _model_3mf() -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(
            "3D/3dmodel.model",
            '<model><resources><basematerials><base name="Red" displaycolor="#FF0000" /></basematerials></resources></model>',
        )
        archive.writestr("Metadata/project_settings.config", json.dumps({"filament_colour": ["#FF0000"]}))
    return payload.getvalue()


def test_geometry_only_3mf_normalizes_supported_palette_to_white() -> None:
    result = geometry_only_3mf(_model_3mf())
    inspection = inspect_3mf(result.output_bytes)

    assert [item.source_color for item in inspection.colors] == ["#FFFFFF"]
    assert all(mapping.matched_hex_srgb == "#FFFFFF" for mapping in result.report.mappings)
