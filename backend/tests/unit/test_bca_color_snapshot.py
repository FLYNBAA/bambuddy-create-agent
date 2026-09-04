from __future__ import annotations

import io
import json
import zipfile

from PIL import Image

from backend.app.three_d_agent.color_snapshot import decode_paint_color_states, inject_color_snapshot


def _painted_3mf(*, stale_snapshot: bool = False) -> bytes:
    """A minimal Bambu-style package with one red and one green triangle."""
    root_model = b'''<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources><object id="2" type="model"><components><component objectid="1"/></components></object></resources>
  <build><item objectid="2"/></build>
</model>'''
    painted_object = b'''<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="1" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0"/>
          <vertex x="1" y="0" z="0"/>
          <vertex x="0" y="1" z="0"/>
          <vertex x="1" y="1" z="0"/>
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" paint_color="4"/>
          <triangle v1="1" v2="3" v3="2" paint_color="8"/>
        </triangles>
      </mesh>
    </object>
  </resources>
</model>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("3D/3dmodel.model", root_model)
        archive.writestr("3D/Objects/object_1.model", painted_object)
        archive.writestr("Metadata/project_settings.config", json.dumps({"filament_colour": ["#E61919", "#18B83C"]}))
        archive.writestr("keep/me.bin", b"must survive")
        if stale_snapshot:
            archive.writestr("Metadata/plate_1.png", b"stale preview")
    return output.getvalue()


def _image_has_dominant_rgb(image_bytes: bytes, channel: int) -> bool:
    with Image.open(io.BytesIO(image_bytes)) as image:
        assert image.size == (512, 512)
        pixels = image.convert("RGB").getdata()
        return any(pixel[channel] > 50 and pixel[channel] > pixel[(channel + 1) % 3] * 1.4 and pixel[channel] > pixel[(channel + 2) % 3] * 1.4 for pixel in pixels)


def test_bambu_paint_color_decoder_reads_reversed_nibble_stream() -> None:
    # Bambu prepends each hex digit, so the string is reversed stream order.
    # A simple leaf is one character: "4"/"8" are states 1/2, "0" unpainted.
    assert decode_paint_color_states("4") == (1,)
    assert decode_paint_color_states("8") == (2,)
    assert decode_paint_color_states("0") == (0,)
    # Extended leaf: marker nibble "C" (state bits 11) read first from the
    # string's end, payload follows in stream order. "0C" -> state 0+3 = 3;
    # "1C" -> state 1+3 = 4.
    assert decode_paint_color_states("0C") == (3,)
    assert decode_paint_color_states("1C") == (4,)
    # Incomplete streams (a split node without its children, or an extended
    # marker without a payload) must be rejected, as must non-hex input.
    assert decode_paint_color_states("1") is None
    assert decode_paint_color_states("C") is None
    assert decode_paint_color_states("XY") is None


def test_existing_snapshot_is_left_untouched_without_replacement_request() -> None:
    source = _painted_3mf(stale_snapshot=True)

    result = inject_color_snapshot(source)

    assert result.status == "present"
    assert result.output_bytes == source


def test_colored_snapshot_replaces_stale_preview_and_preserves_package_members() -> None:
    source = _painted_3mf(stale_snapshot=True)

    result = inject_color_snapshot(source, replace_existing=True)

    assert result.status == "replaced"
    with zipfile.ZipFile(io.BytesIO(result.output_bytes)) as archive:
        assert set(archive.namelist()) == {
            "[Content_Types].xml",
            "3D/3dmodel.model",
            "3D/Objects/object_1.model",
            "Metadata/project_settings.config",
            "Metadata/plate_1.png",
            "keep/me.bin",
        }
        assert archive.read("keep/me.bin") == b"must survive"
        snapshot = archive.read("Metadata/plate_1.png")
    assert snapshot != b"stale preview"
    assert _image_has_dominant_rgb(snapshot, 0)
    assert _image_has_dominant_rgb(snapshot, 1)


def test_unrenderable_model_fails_open_without_replacing_existing_package() -> None:
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("3D/3dmodel.model", b"<not-valid-xml")
        archive.writestr("keep/me.bin", b"must survive")

    result = inject_color_snapshot(source.getvalue())

    assert result.status == "skipped"
    assert result.output_bytes == source.getvalue()
