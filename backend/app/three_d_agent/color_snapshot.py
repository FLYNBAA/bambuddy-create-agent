"""Best-effort coloured Bambu/Meshy 3MF snapshot generation.

Bambu Studio stores per-triangle colour selection in ``paint_color`` rather
than standard 3MF material references.  The selection is a compact, LSB-first
bit stream.  This module decodes enough of that format to render a useful
static preview and puts it where the client already expects it:
``Metadata/plate_1.png``.

This is deliberately independent of the ordinary plate-thumbnail renderer.
That renderer uses one Bambu-green material for every face; using it for an
unsliced colour model would lose the palette that matters here.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

SnapshotStatus = Literal["created", "replaced", "present", "skipped"]

_SNAPSHOT_NAME = "Metadata/plate_1.png"
_SNAPSHOT_SIZE = 512
_MAX_RENDER_FACES = 500_000
_MAX_PAINT_NODES = 250_000
_DEFAULT_FACE_COLOR = "#9CA3AF"
_BACKGROUND_COLOR = "#1A1A1A"


@dataclass(frozen=True, slots=True)
class ColorSnapshotResult:
    """Result of a best-effort snapshot attempt.

    ``status == 'skipped'`` is intentional failure isolation: callers must
    still return the original print artifact when its preview cannot render.
    """

    output_bytes: bytes
    status: SnapshotStatus
    error: str | None = None

    @property
    def changed(self) -> bool:
        return self.status in {"created", "replaced"}


def has_color_snapshot(source: bytes | bytearray | memoryview | str | os.PathLike[str]) -> bool:
    """Whether the package already has the precise preview the web client uses."""
    try:
        with zipfile.ZipFile(io.BytesIO(_source_bytes(source))) as archive:
            return _SNAPSHOT_NAME in archive.namelist()
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def inject_color_snapshot(
    source: bytes | bytearray | memoryview | str | os.PathLike[str],
    *,
    replace_existing: bool = False,
    output_path: str | os.PathLike[str] | None = None,
) -> ColorSnapshotResult:
    """Render and inject a coloured 512px ``Metadata/plate_1.png``.

    ``source`` may be package bytes or a path.  All ZIP entries other than a
    replaced snapshot are copied unchanged.  Rendering and ZIP errors are
    represented by a ``skipped`` result rather than raised, so a preview can
    never make creation of an otherwise valid artifact fail.  Call this
    synchronous function in a worker thread from async endpoints.
    """
    try:
        source_bytes = _source_bytes(source)
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
            had_snapshot = _SNAPSHOT_NAME in archive.namelist()
            if had_snapshot and not replace_existing:
                return ColorSnapshotResult(source_bytes, "present")
            model_names = _model_member_names(archive)
            if not model_names:
                return ColorSnapshotResult(source_bytes, "skipped", "3MF has no model XML")
            model_xmls = tuple(archive.read(name) for name in model_names)
            palette = _read_palette(archive)
    except Exception as exc:  # Preview generation must never reject an artifact.
        logger.info("color snapshot: could not read 3MF package: %s", exc)
        return ColorSnapshotResult(_safe_source_bytes(source), "skipped", "unreadable 3MF package")

    try:
        png = _render_colored_models(model_xmls, palette)
        if png is None:
            return ColorSnapshotResult(source_bytes, "skipped", "3MF has no renderable coloured mesh")
        output = _replace_snapshot(source_bytes, png)
        if output_path is not None:
            _atomic_write(Path(output_path), output)
        return ColorSnapshotResult(output, "replaced" if had_snapshot else "created")
    except Exception as exc:  # Preview generation is strictly best-effort.
        logger.warning("color snapshot: render or injection failed: %s", exc, exc_info=True)
        return ColorSnapshotResult(source_bytes, "skipped", "snapshot rendering failed")


def decode_paint_color_states(encoded: str, *, max_nodes: int = _MAX_PAINT_NODES) -> tuple[int, ...] | None:
    """Return decoded leaf palette states from a Bambu ``paint_color`` value.

    Bambu's ``FacetsAnnotation::get_triangle_as_string`` prepends each
    hexadecimal digit (``out.insert(out.begin(), digit)``), so the string is
    in reverse stream order and must be read from its last character. Each
    nibble is one node: the low two bits are ``split_sides``; the high two
    bits are the leaf state, or the split node's ``special_side`` (which only
    affects subdivision geometry, not colour). A leaf state of ``0b11`` is
    the extended-state marker: following nibbles give
    ``state = payload + 15 * continuations + 3``. A split node is followed by
    ``split_sides + 1`` children. The walk is nibble-aligned and iterative;
    a value only decodes when it consumes every nibble exactly.
    """
    if not isinstance(encoded, str) or not encoded or max_nodes < 1:
        return None
    compact = encoded.strip()
    if not compact:
        return None
    try:
        # Last character of the string is the first nibble of the stream.
        stream = [int(character, 16) for character in reversed(compact)]
    except ValueError:
        return None

    total = len(stream)
    position = 0
    pending = 1
    leaves: list[int] = []
    while pending:
        pending -= 1
        if position >= total or len(leaves) + pending > max_nodes:
            return None
        code = stream[position]
        position += 1
        split_sides = code & 0b11
        if split_sides:
            pending += split_sides + 1
            continue
        state = code >> 2
        if state == 0b11:
            continuations = 0
            while True:
                if position >= total:
                    return None
                payload = stream[position]
                position += 1
                if payload == 0b1111:
                    continuations += 1
                    continue
                state = payload + 15 * continuations + 3
                break
        leaves.append(state)
    if position != total:
        return None
    return tuple(leaves) if leaves else None


def _source_bytes(source: bytes | bytearray | memoryview | str | os.PathLike[str]) -> bytes:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    return Path(source).read_bytes()


def _safe_source_bytes(source: bytes | bytearray | memoryview | str | os.PathLike[str]) -> bytes:
    try:
        return _source_bytes(source)
    except OSError:
        return b""


def _model_member_names(archive: zipfile.ZipFile) -> tuple[str, ...]:
    return tuple(name for name in archive.namelist() if name.startswith("3D/") and name.endswith(".model"))



def _read_palette(archive: zipfile.ZipFile) -> tuple[str, ...]:
    """Read Bambu's project palette; malformed configuration is simply absent."""
    try:
        raw = archive.read("Metadata/project_settings.config")
        config = json.loads(raw.decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return ()
    palette = config.get("filament_colour") if isinstance(config, dict) else None
    if not isinstance(palette, list):
        return ()
    return tuple(color for color in palette if isinstance(color, str) and _normalise_color(color) is not None)


def _normalise_color(value: str) -> str | None:
    digits = value.strip().lstrip("#")
    if len(digits) in (3, 4):
        digits = "".join(char * 2 for char in digits)
    if len(digits) not in (6, 8) or any(char not in "0123456789abcdefABCDEF" for char in digits):
        return None
    return "#" + digits[:6].upper()




def _render_colored_models(model_xmls: tuple[bytes, ...], palette: tuple[str, ...]) -> bytes | None:
    """Render model members with Bambu per-face colours.

    Machine-generated 3MF model XML is extremely regular, and the Bambu
    object members can exceed 50 MiB compressed (hundreds of megabytes as
    text). Building an ElementTree for that costs gigabytes and tens of
    seconds — the exact lag this snapshot replaces — so vertices and
    triangles are matched with the same byte-level regex discipline
    calibration.py uses for colour rewriting.

    The visible surface is produced by a NumPy triangle z-buffer instead of
    matplotlib's 3D polygon engine: a ``Poly3DCollection`` with hundreds of
    thousands of faces takes minutes and renders sparsely. Filling projected
    triangles keeps the model solid while preserving its per-face colours.
    """
    for model_xml in model_xmls:
        if b"<!DOCTYPE" in model_xml.upper() or b"<!ENTITY" in model_xml.upper():
            return None

    triangle_count = sum(len(_TRIANGLE_TAG_RE.findall(model_xml)) for model_xml in model_xmls)
    if not triangle_count:
        return None
    sample_stride = max(1, (triangle_count + _MAX_RENDER_FACES - 1) // _MAX_RENDER_FACES)

    # Heavy rendering dependencies are intentionally imported only when a
    # snapshot is actually needed. The local developer environment does not
    # need the production renderer installed to import endpoint modules.
    import numpy as np
    from backend.app.services.stl_thumbnail import _configure_matplotlib_cache

    _configure_matplotlib_cache()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    standard = {
        (group, index): color
        for model_xml in model_xmls
        for group, index, color in _standard_color_entries(model_xml)
    }
    polygons: list[tuple[tuple[float, float, float], ...]] = []
    colors: list[str] = []
    triangle_index = 0
    for model_xml in model_xmls:
        vertices = _decode_vertices(model_xml)
        if not vertices:
            continue
        for match in _TRIANGLE_TAG_RE.finditer(model_xml):
            include = triangle_index % sample_stride == 0
            triangle_index += 1
            if not include:
                continue
            indices = _decode_triangle_indices(match.group(0))
            if indices is None:
                continue
            try:
                points = tuple(vertices[index] for index in indices)
            except IndexError:
                continue
            if any(point is None for point in points):
                continue
            polygons.append(points)  # type: ignore[arg-type]
            colors.append(_triangle_color(match.group(0), palette, standard))
    if not polygons:
        return None
    rgb = np.asarray([_hex_to_rgb(color) for color in colors], dtype=float)
    if not np.isfinite(rgb).all():
        return None

    triangles = np.asarray(polygons, dtype=float)
    # 3MF geometry is Z-up; the camera setup below looks down -Y, so rotate
    # once here to make Z the screen-up axis.
    triangles = triangles[:, :, [0, 2, 1]]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    visible = lengths > 0
    if not visible.any():
        return None
    triangles = triangles[visible]
    normals = normals[visible] / lengths[visible, None]
    rgb = rgb[visible]
    # Match the plate-thumbnail view (25° elevation, 45° azimuth) so both
    # preview paths feel like one product.
    azimuth = np.deg2rad(45.0)
    elevation = np.deg2rad(25.0)
    yaw = np.array(
        [
            [np.cos(azimuth), np.sin(azimuth), 0.0],
            [-np.sin(azimuth), np.cos(azimuth), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    pitch = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(elevation), np.sin(elevation)],
            [0.0, -np.sin(elevation), np.cos(elevation)],
        ]
    )
    rotated = triangles @ yaw @ pitch
    view_normals = normals @ yaw @ pitch
    if not np.isfinite(rotated).all():
        return None

    screen = rotated[:, :, (0, 2)]
    screen_min = screen.reshape(-1, 2).min(axis=0)
    screen_span = np.ptp(screen.reshape(-1, 2), axis=0)
    span = float(screen_span.max())
    if span <= 0:
        return None
    margin = 0.08
    usable = _SNAPSHOT_SIZE * (1.0 - 2.0 * margin)
    pixels = (screen - screen_min) / span * usable + _SNAPSHOT_SIZE * margin

    image = np.empty((_SNAPSHOT_SIZE, _SNAPSHOT_SIZE, 3), dtype=float)
    image[:] = np.asarray(matplotlib.colors.to_rgb(_BACKGROUND_COLOR))
    depth_buffer = np.full((_SNAPSHOT_SIZE, _SNAPSHOT_SIZE), -np.inf)
    light = np.array([-0.35, -0.6, 0.8])
    light /= np.linalg.norm(light)
    shade = 0.45 + 0.55 * np.clip(-(view_normals @ light), 0.0, 1.0)
    face_colors = np.clip(rgb * shade[:, None], 0.0, 1.0)

    for face, face_depth, face_color in zip(pixels, rotated[:, :, 1], face_colors, strict=True):
        x_min = max(0, int(np.floor(face[:, 0].min())))
        x_max = min(_SNAPSHOT_SIZE - 1, int(np.ceil(face[:, 0].max())))
        y_min = max(0, int(np.floor(face[:, 1].min())))
        y_max = min(_SNAPSHOT_SIZE - 1, int(np.ceil(face[:, 1].max())))
        if x_min > x_max or y_min > y_max:
            continue
        x0, y0 = face[0]
        x1, y1 = face[1]
        x2, y2 = face[2]
        denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denominator) < 1e-12:
            continue
        x = np.arange(x_min, x_max + 1, dtype=float) + 0.5
        y = np.arange(y_min, y_max + 1, dtype=float)[:, None] + 0.5
        weight_0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / denominator
        weight_1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / denominator
        weight_2 = 1.0 - weight_0 - weight_1
        covered = (weight_0 >= 0.0) & (weight_1 >= 0.0) & (weight_2 >= 0.0)
        depth = weight_0 * face_depth[0] + weight_1 * face_depth[1] + weight_2 * face_depth[2]
        depth_region = depth_buffer[y_min : y_max + 1, x_min : x_max + 1]
        nearer = covered & (depth > depth_region)
        if not nearer.any():
            continue
        depth_region[nearer] = depth[nearer]
        image[y_min : y_max + 1, x_min : x_max + 1][nearer] = face_color

    figure = plt.figure(figsize=(_SNAPSHOT_SIZE / 100, _SNAPSHOT_SIZE / 100), dpi=100)
    try:
        figure.patch.set_facecolor(_BACKGROUND_COLOR)
        axis = figure.add_subplot(111)
        axis.imshow(image, interpolation="nearest")
        axis.set_axis_off()
        figure.subplots_adjust(left=0, right=1, top=1, bottom=0)
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", facecolor=_BACKGROUND_COLOR, edgecolor="none", dpi=100)
        return buffer.getvalue()
    finally:
        plt.close(figure)


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    digits = value.strip().lstrip("#")
    return tuple(int(digits[index : index + 2], 16) / 255.0 for index in (0, 2, 4))  # type: ignore[return-value]


_VERTEX_TAG_RE = re.compile(rb"<vertex\b[^<>]*?/?>", re.DOTALL)
_TRIANGLE_TAG_RE = re.compile(rb"<triangle\b[^<>]*?/?>", re.DOTALL)
_BASE_COLOR_TAG_RE = re.compile(rb"<(?:base|color)\b[^<>]*?/?>", re.DOTALL)
_ID_ATTRIBUTE_RE = re.compile(rb"\bid\s*=\s*['\"]([^'\"]*)['\"]")
_PID_ATTRIBUTE_RE = re.compile(rb"\bpid\s*=\s*['\"]([^'\"]*)['\"]")
_P1_ATTRIBUTE_RE = re.compile(rb"\bp1\s*=\s*['\"]([^'\"]*)['\"]")
_PAINT_ATTRIBUTE_RE = re.compile(rb"\bpaint_color\s*=\s*['\"]([^'\"]*)['\"]")
_COORDINATE_ATTRIBUTE_RE = re.compile(rb"\b([xyz])\s*=\s*['\"]([^'\"]*)['\"]")


def _attribute_bytes(tag: bytes, pattern: re.Pattern[bytes]) -> str | None:
    match = pattern.search(tag)
    if match is None:
        return None
    return match.group(1).decode("utf-8", errors="replace")


def _decode_vertices(model_xml: bytes) -> list[tuple[float, float, float] | None]:
    vertices: list[tuple[float, float, float] | None] = []
    for match in _VERTEX_TAG_RE.finditer(model_xml):
        tag = match.group(0)
        coordinates: dict[str, float] = {}
        for axis, raw in _COORDINATE_ATTRIBUTE_RE.findall(tag):
            try:
                coordinates[axis.decode()] = float(raw)
            except ValueError:
                pass
        if len(coordinates) == 3:
            vertices.append((coordinates["x"], coordinates["y"], coordinates["z"]))
        else:
            vertices.append(None)
    return vertices


def _decode_triangle_indices(tag: bytes) -> tuple[int, int, int] | None:
    values: list[int] = []
    for axis in (b"v1", b"v2", b"v3"):
        raw = _attribute_bytes(tag, re.compile(rb"\b" + axis + rb"\s*=\s*['\"]([^'\"]*)['\"]"))
        if raw is None:
            return None
        try:
            values.append(int(raw))
        except ValueError:
            return None
    return (values[0], values[1], values[2])


def _standard_color_entries(model_xml: bytes) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    for match in _BASE_COLOR_TAG_RE.finditer(model_xml):
        tag = match.group(0)
        group = _attribute_bytes(tag, _ID_ATTRIBUTE_RE)
        color = _normalise_color(
            _attribute_bytes(tag, re.compile(rb"\b(?:displaycolor|color)\s*=\s*['\"]([^'\"]*)['\"]")) or ""
        )
        if group is not None and color is not None:
            entries.append((group, "0", color))
    return entries

def _triangle_color(tag: bytes, palette: tuple[str, ...], standard: dict[tuple[str, str], str]) -> str:
    paint = _attribute_bytes(tag, _PAINT_ATTRIBUTE_RE)
    if paint and palette:
        states = decode_paint_color_states(paint)
        if states:
            state = Counter(states).most_common(1)[0][0]
            # State 0 is unpainted and prints in the object's default
            # extruder, which Meshy/Bambu multicolor exports set to 1.
            if state == 0:
                return _normalise_color(palette[0]) or _DEFAULT_FACE_COLOR
            if 1 <= state <= len(palette):
                return _normalise_color(palette[state - 1]) or _DEFAULT_FACE_COLOR
    pid = _attribute_bytes(tag, _PID_ATTRIBUTE_RE)
    p1 = _attribute_bytes(tag, _P1_ATTRIBUTE_RE)
    if pid is not None and p1 is not None:
        return standard.get((pid, p1), _DEFAULT_FACE_COLOR)
    return _DEFAULT_FACE_COLOR


def _replace_snapshot(package: bytes, png: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package)) as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as destination:
        for info in source.infolist():
            if info.filename != _SNAPSHOT_NAME:
                destination.writestr(info, source.read(info))
        destination.writestr(_SNAPSHOT_NAME, png)
    return output.getvalue()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


__all__ = ["ColorSnapshotResult", "decode_paint_color_states", "has_color_snapshot", "inject_color_snapshot"]
