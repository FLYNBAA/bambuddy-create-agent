"""Safe 3MF inspection and mapping-driven filament color rewriting.

DeepSeek (or another caller) decides which inventory color each source color
means. This module deliberately does not perform color matching. It only
validates that explicit assignments cover the package's colors, then rewrites
supported color-bearing metadata while preserving geometry and face painting.
"""
from __future__ import annotations

import io
import json
import os
import posixpath
import re
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


class CalibrationError(ValueError):
    """Raised when input records, assignments, or a 3MF package are unsafe."""


@dataclass(frozen=True, slots=True)
class InventoryColor:
    id: str
    name: str
    material: str
    brand: str
    hex_srgb: str

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.material or not self.brand:
            raise CalibrationError("inventory id, name, material and brand are required")
        if len(self.hex_srgb) != 7:
            raise CalibrationError("inventory hex_srgb must be #RRGGBB")
        _parse_hex(self.hex_srgb)


@dataclass(frozen=True, slots=True)
class ColorAssignment:
    """An explicit source-to-inventory decision supplied by the AI matcher."""

    source_color: str
    inventory_id: str
    rationale: str | None = None


@dataclass(frozen=True, slots=True)
class SourceColor:
    source_color: str
    occurrence_count: int


@dataclass(frozen=True, slots=True)
class CalibrationLimits:
    # Meshy/Bambu model XML is highly compressible: a 34 MiB package can hold
    # one legitimate object model far above 100 MiB after decompression.
    max_input_bytes: int = 512 * 1024 * 1024
    max_members: int = 2048
    max_member_bytes: int = 512 * 1024 * 1024
    max_total_uncompressed: int = 512 * 1024 * 1024
    max_compression_ratio: float = 500.0


@dataclass(frozen=True, slots=True)
class ColorMapping:
    source_color: str
    inventory_id: str
    inventory_name: str
    matched_hex_srgb: str
    rationale: str | None
    changed_count: int


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    mappings: tuple[ColorMapping, ...]
    changed_count: int
    member_count: int


@dataclass(frozen=True, slots=True)
class CalibrationInspection:
    colors: tuple[SourceColor, ...]
    member_count: int


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    output_bytes: bytes
    report: CalibrationReport


def _parse_hex(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or len(value) not in (4, 5, 7, 9) or value[0] != "#":
        raise CalibrationError(f"invalid sRGB colour: {value!r}")
    digits = value[1:]
    if any(c not in "0123456789abcdefABCDEF" for c in digits):
        raise CalibrationError(f"invalid sRGB colour: {value!r}")
    if len(digits) in (3, 4):
        digits = "".join(c * 2 for c in digits)
    return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _canonical_rgb(value: str) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in _parse_hex(value))


def _target_hex(source: str, inventory: InventoryColor) -> str:
    target = inventory.hex_srgb.upper()
    return target + "FF" if len(source) in (5, 9) else target


def _safe_name(name: str) -> bool:
    return (
        bool(name)
        and name not in (".", "..")
        and not any(ord(char) < 32 for char in name)
        and not name.startswith(("/", "\\"))
        and "\\" not in name
        and posixpath.normpath(name) == name
        and ".." not in name.split("/")
    )


def _read_package(
    source: bytes | bytearray | memoryview | str | os.PathLike[str],
    limits: CalibrationLimits,
) -> list[tuple[zipfile.ZipInfo, bytes]]:
    if isinstance(source, (bytes, bytearray, memoryview)):
        raw = bytes(source)
    else:
        path = Path(source)
        try:
            if path.stat().st_size > limits.max_input_bytes:
                raise CalibrationError("3MF input exceeds size limit")
            raw = path.read_bytes()
        except OSError as exc:
            raise CalibrationError("unable to read 3MF input") from exc
    if len(raw) > limits.max_input_bytes:
        raise CalibrationError("3MF input exceeds size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > limits.max_members:
                raise CalibrationError("invalid 3MF member count")
            names: set[str] = set()
            total = 0
            members: list[tuple[zipfile.ZipInfo, bytes]] = []
            for info in infos:
                is_symlink = ((info.external_attr >> 16) & 0o170000) == 0o120000
                # ZIP directory entries are optional metadata. Meshy and common
                # 3MF exporters emit them; reject unsafe/non-empty directories,
                # but never treat a harmless `3D/` or `_rels/` entry as model
                # content or a validation failure.
                if info.is_dir():
                    directory_name = info.filename.rstrip("/")
                    if (
                        not _safe_name(directory_name)
                        or info.file_size
                        or info.compress_size
                        or info.flag_bits & 0x1
                        or is_symlink
                    ):
                        raise CalibrationError("unsafe 3MF directory member")
                    continue
                if (
                    info.filename in names
                    or not _safe_name(info.filename)
                    or info.flag_bits & 0x1
                    or is_symlink
                ):
                    raise CalibrationError("unsafe or duplicate 3MF member")
                if info.file_size > limits.max_member_bytes:
                    raise CalibrationError("3MF member exceeds size limit")
                if info.compress_size and info.file_size / info.compress_size > limits.max_compression_ratio:
                    raise CalibrationError("3MF compression ratio exceeds limit")
                total += info.file_size
                if total > limits.max_total_uncompressed:
                    raise CalibrationError("3MF uncompressed size exceeds limit")
                names.add(info.filename)
                data = archive.read(info)
                if len(data) != info.file_size:
                    raise CalibrationError("3MF member size mismatch")
                members.append((info, data))
            if "[Content_Types].xml" not in names or not any(
                name.startswith("3D/") and name.endswith(".model") for name in names
            ):
                raise CalibrationError("3MF missing required package members")
            return members
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
        raise CalibrationError("malformed 3MF ZIP") from exc

def validate_3mf_package(
    input_data: bytes | bytearray | memoryview | str | os.PathLike[str],
    limits: CalibrationLimits | None = None,
) -> None:
    """Validate a safe 3MF package without requiring color-bearing metadata."""
    _read_package(input_data, limits or CalibrationLimits())


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _record_color(counts: dict[str, int], order: list[str], source: str) -> None:
    canonical = _canonical_rgb(source)
    counts[canonical] = counts.get(canonical, 0) + 1
    if canonical not in order:
        order.append(canonical)


def _parse_model_colors(data: bytes, name: str, counts: dict[str, int], order: list[str]) -> None:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise CalibrationError(f"unsafe XML declarations: {name}")
    try:
        parser = ElementTree.XMLParser(target=ElementTree.TreeBuilder(insert_comments=True))
        root = ElementTree.fromstring(data, parser=parser)
    except ElementTree.ParseError as exc:
        raise CalibrationError(f"malformed model XML: {name}") from exc
    for node in root.iter():
        kind = _local(node.tag)
        attr = (
            "displaycolor"
            if kind == "base" and "displaycolor" in node.attrib
            else "color"
            if kind == "color" and "color" in node.attrib
            else None
        )
        if attr is not None:
            _parse_hex(node.attrib[attr])
            _record_color(counts, order, node.attrib[attr])


def _parse_project_palette(data: bytes, counts: dict[str, int], order: list[str]) -> dict[str, object]:
    try:
        config = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibrationError("malformed Metadata/project_settings.config JSON") from exc
    if not isinstance(config, dict):
        raise CalibrationError("project settings must be a JSON object")
    palette = config.get("filament_colour")
    if palette is not None:
        if not isinstance(palette, list) or not palette or len(palette) > 16 or not all(isinstance(c, str) for c in palette):
            raise CalibrationError("filament_colour must be a non-empty array of at most 16 strings")
        for source in palette:
            _parse_hex(source)
            _record_color(counts, order, source)
    return config

_MODEL_TAG_RE = re.compile(
    rb"<(?:(?:[A-Za-z_][\w.-]*):)?(?P<kind>base|color)\b[^<>]*?/?>",
    re.DOTALL,
)
_XML_ATTRIBUTE_RE = re.compile(
    rb"(?P<name>displaycolor|color|name)(?P<equals>\s*=\s*)(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)"
)
_PROJECT_PALETTE_RE = re.compile(
    rb"(?P<prefix>\"filament_colour\"\s*:\s*)\[(?P<values>[^\[\]]*)\]",
    re.DOTALL,
)


def _rewrite_model_colors(
    data: bytes,
    name: str,
    targets: Mapping[str, InventoryColor],
) -> tuple[bytes, int]:
    """Patch only color/name attribute bytes; never reserialize model XML."""
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise CalibrationError(f"unsafe XML declarations: {name}")
    try:
        ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise CalibrationError(f"malformed model XML: {name}") from exc

    changed = 0

    def replace_tag(tag_match: re.Match[bytes]) -> bytes:
        nonlocal changed
        kind = tag_match.group("kind")
        tag = tag_match.group(0)
        attributes = {match.group("name"): match for match in _XML_ATTRIBUTE_RE.finditer(tag)}
        color_attribute = b"displaycolor" if kind == b"base" else b"color"
        color_match = attributes.get(color_attribute)
        if color_match is None:
            return tag
        source = color_match.group("value").decode("ascii", errors="strict")
        target = targets.get(_canonical_rgb(source))
        if target is None:
            raise CalibrationError(f"model color is missing an AI assignment: {source}")
        target_value = _target_hex(source, target).encode("ascii")
        replacements = {color_match.span("value"): target_value}
        if kind == b"base" and b"name" in attributes:
            replacements[attributes[b"name"].span("value")] = target.name.encode("utf-8")
        pieces: list[bytes] = []
        cursor = 0
        for start, end in sorted(replacements):
            pieces.extend((tag[cursor:start], replacements[(start, end)]))
            cursor = end
        pieces.append(tag[cursor:])
        changed += 1
        return b"".join(pieces)

    return _MODEL_TAG_RE.sub(replace_tag, data), changed


def _rewrite_project_palette(
    data: bytes,
    targets: Mapping[str, InventoryColor],
) -> bytes:
    config = _parse_project_palette(data, {}, [])
    palette = config.get("filament_colour")
    if not isinstance(palette, list):
        return data
    target_values = [
        _target_hex(source, targets[_canonical_rgb(source)])
        for source in palette
    ]
    replacement = b"[" + b",".join(json.dumps(value).encode("ascii") for value in target_values) + b"]"
    match = _PROJECT_PALETTE_RE.search(data)
    if match is None:
        raise CalibrationError("filament_colour JSON member could not be patched safely")
    return data[: match.start("values") - 1] + replacement + data[match.end("values") + 1 :]


def _inspect_members(members: Sequence[tuple[zipfile.ZipInfo, bytes]]) -> CalibrationInspection:
    counts: dict[str, int] = {}
    order: list[str] = []
    for info, data in members:
        if info.filename.startswith("3D/") and info.filename.endswith(".model"):
            _parse_model_colors(data, info.filename, counts, order)
        elif info.filename == "Metadata/project_settings.config":
            _parse_project_palette(data, counts, order)
    if not order:
        raise CalibrationError("3MF contains no supported color metadata")
    return CalibrationInspection(
        colors=tuple(SourceColor(source, counts[source]) for source in order),
        member_count=len(members),
    )


def inspect_3mf(
    input_data: bytes | bytearray | memoryview | str | os.PathLike[str],
    limits: CalibrationLimits | None = None,
) -> CalibrationInspection:
    """Inspect supported source colors without making any change."""
    return _inspect_members(_read_package(input_data, limits or CalibrationLimits()))


def _assignment_map(assignments: Sequence[ColorAssignment | Mapping[str, object]]) -> dict[str, ColorAssignment]:
    result: dict[str, ColorAssignment] = {}
    for raw in assignments:
        assignment = raw if isinstance(raw, ColorAssignment) else ColorAssignment(
            source_color=str(raw.get("source_color", "")),
            inventory_id=str(raw.get("inventory_id", "")),
            rationale=raw.get("rationale") if isinstance(raw.get("rationale"), str) else None,
        )
        source = _canonical_rgb(assignment.source_color)
        if source in result:
            raise CalibrationError(f"duplicate AI assignment for source color {source}")
        if not assignment.inventory_id:
            raise CalibrationError(f"missing inventory ID for source color {source}")
        result[source] = ColorAssignment(source, assignment.inventory_id, assignment.rationale)
    return result


def calibrate_3mf(
    input_data: bytes | bytearray | memoryview | str | os.PathLike[str],
    colors: Sequence[InventoryColor],
    assignments: Sequence[ColorAssignment | Mapping[str, object]],
    limits: CalibrationLimits | None = None,
    output_path: str | os.PathLike[str] | None = None,
) -> CalibrationResult:
    """Rewrite a 3MF using explicit AI assignments; never infer a match locally."""
    limits = limits or CalibrationLimits()
    inventory = list(colors)
    if not inventory:
        raise CalibrationError("at least one inventory colour is required")
    if len({color.id for color in inventory}) != len(inventory):
        raise CalibrationError("inventory IDs must be unique")
    inventory_by_id = {color.id: color for color in inventory}
    assignment_by_source = _assignment_map(assignments)
    members = _read_package(input_data, limits)
    inspection = _inspect_members(members)
    source_set = {color.source_color for color in inspection.colors}
    if set(assignment_by_source) != source_set:
        missing = sorted(source_set - set(assignment_by_source))
        extra = sorted(set(assignment_by_source) - source_set)
        raise CalibrationError(f"AI assignments must cover exactly package colors; missing={missing}, extra={extra}")
    targets: dict[str, InventoryColor] = {}
    for source, assignment in assignment_by_source.items():
        target = inventory_by_id.get(assignment.inventory_id)
        if target is None:
            raise CalibrationError(f"AI selected unknown inventory ID {assignment.inventory_id!r}")
        targets[source] = target

    rewritten: dict[str, bytes] = {}
    for info, data in members:
        if info.filename.startswith("3D/") and info.filename.endswith(".model"):
            rewritten[info.filename], _ = _rewrite_model_colors(data, info.filename, targets)
        elif info.filename == "Metadata/project_settings.config":
            rewritten[info.filename] = _rewrite_project_palette(data, targets)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for info, data in members:
            archive.writestr(info, rewritten.get(info.filename, data))
    result_bytes = output.getvalue()
    _read_package(result_bytes, limits)
    mappings = tuple(
        ColorMapping(
            source_color=color.source_color,
            inventory_id=assignment_by_source[color.source_color].inventory_id,
            inventory_name=targets[color.source_color].name,
            matched_hex_srgb=targets[color.source_color].hex_srgb.upper(),
            rationale=assignment_by_source[color.source_color].rationale,
            changed_count=color.occurrence_count,
        )
        for color in inspection.colors
    )
    report = CalibrationReport(
        mappings=mappings,
        changed_count=sum(color.occurrence_count for color in inspection.colors),
        member_count=inspection.member_count,
    )
    if output_path is not None:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target_path.name}.", dir=target_path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(result_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target_path)
        except OSError as exc:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise CalibrationError("unable to atomically write calibrated 3MF") from exc
    return CalibrationResult(result_bytes, report)

def geometry_only_3mf(
    input_data: bytes | bytearray | memoryview | str | os.PathLike[str],
    limits: CalibrationLimits | None = None,
    output_path: str | os.PathLike[str] | None = None,
) -> CalibrationResult:
    """Normalize every supported palette entry to opaque white.

    3MF face references remain structurally valid, but no material colour
    distinction survives. This is the safe geometry-only variant for a
    single-white-material print workflow.
    """
    inspection = inspect_3mf(input_data, limits)
    neutral = InventoryColor("geometry-white", "Geometry White", "PLA", "BCA", "#FFFFFF")
    assignments = [ColorAssignment(item.source_color, neutral.id, "geometry-only") for item in inspection.colors]
    return calibrate_3mf(input_data, [neutral], assignments, limits, output_path)


__all__ = [
    "CalibrationError",
    "CalibrationInspection",
    "CalibrationLimits",
    "CalibrationReport",
    "CalibrationResult",
    "ColorAssignment",
    "ColorMapping",
    "InventoryColor",
    "SourceColor",
    "geometry_only_3mf",
    "calibrate_3mf",
    "inspect_3mf",
]
