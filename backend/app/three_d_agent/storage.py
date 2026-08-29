"""Durable session and artifact storage for the 3D-print agent."""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import os
import re
import sqlite3
import struct
import tempfile
import zipfile
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import Settings
from .contracts import SessionSnapshot, SessionStatus
from .network import assert_allowed_https_host

try:
    from pillow_heif import register_heif_opener
except ImportError:  # pragma: no cover - deployment dependency is declared.
    register_heif_opener = None
else:
    register_heif_opener()

_SESSION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_COPY_CHUNK_SIZE: Final[int] = 64 * 1024
_TENCENT_MODEL_HOST_SUFFIXES: Final[tuple[str, ...]] = ("tencentcos.cn", "myqcloud.com")
_MESHY_MODEL_HOST_SUFFIXES: Final[tuple[str, ...]] = ("meshy.ai",)
_LEGACY_STATUSES: Final[dict[str, str]] = {
    "awaiting_confirmation": SessionStatus.AWAITING_IMAGE_CONFIRMATION.value,
    "queued": SessionStatus.QUEUED_IMAGE.value,
    "generating_image": SessionStatus.GENERATING_IMAGES.value,
}


class _PublicRedirectHandler(HTTPRedirectHandler):
    """Validate every redirect before urllib opens the next destination."""

    def __init__(self, allowed_suffixes: tuple[str, ...]) -> None:
        super().__init__()
        self._allowed_suffixes = allowed_suffixes

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_allowed_https_host(newurl, self._allowed_suffixes)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SessionRepository:
    """SQLite-backed repository of complete session snapshots."""

    def __init__(self, settings: Settings) -> None:
        self._database_path = settings.data_dir.expanduser().resolve() / "sessions.sqlite3"
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        try:
            connection.execute("PRAGMA busy_timeout = 30000")
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_provider_artifacts (
                    session_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    PRIMARY KEY (session_id, operation),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            self._migrate_legacy_snapshots(connection)
            connection.commit()

    @staticmethod
    def _migrate_legacy_snapshots(connection: sqlite3.Connection) -> None:
        """Upgrade persisted pre-two-gate JSON before Pydantic reconstructs it."""
        rows = connection.execute("SELECT session_id, snapshot_json FROM sessions").fetchall()
        for session_id, serialized in rows:
            try:
                payload = json.loads(serialized)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue

            changed = False
            legacy_status = payload.get("status")
            if legacy_status in _LEGACY_STATUSES:
                payload["status"] = _LEGACY_STATUSES[legacy_status]
                changed = True

            if "generated_image_path" in payload:
                legacy_path = payload.pop("generated_image_path")
                changed = True
                if legacy_path and not payload.get("generated_image_paths"):
                    payload["generated_image_paths"] = [legacy_path]
                if (
                    legacy_path
                    and payload.get("status")
                    in {SessionStatus.GENERATING_3D.value, SessionStatus.COMPLETED.value}
                    and payload.get("selected_image_index") is None
                ):
                    payload["selected_image_index"] = 0

            if changed:
                connection.execute(
                    "UPDATE sessions SET snapshot_json = ? WHERE session_id = ?",
                    (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), session_id),
                )

    def create(self, snapshot: SessionSnapshot) -> SessionSnapshot:
        payload = snapshot.model_dump_json()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO sessions (session_id, snapshot_json, created_at) VALUES (?, ?, ?)",
                (snapshot.session_id, payload, snapshot.created_at.isoformat()),
            )
            connection.commit()
        return SessionSnapshot.model_validate_json(payload)

    def get(self, session_id: str) -> SessionSnapshot:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return SessionSnapshot.model_validate_json(row[0])

    def save(self, snapshot: SessionSnapshot) -> SessionSnapshot:
        payload = snapshot.model_dump_json()
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET snapshot_json = ? WHERE session_id = ?",
                (payload, snapshot.session_id),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise KeyError(snapshot.session_id)
            connection.commit()
        return SessionSnapshot.model_validate_json(payload)
    def delete(self, session_id: str) -> None:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            if cursor.rowcount != 1:
                connection.rollback()
                raise KeyError(session_id)
            connection.commit()

    def get_pending_artifact_url(self, session_id: str, operation: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT source_url FROM pending_provider_artifacts
                WHERE session_id = ? AND operation = ?
                """,
                (session_id, operation),
            ).fetchone()
        return row[0] if row is not None else None

    def save_pending_artifact_url(self, session_id: str, operation: str, source_url: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO pending_provider_artifacts (session_id, operation, source_url)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, operation) DO UPDATE SET source_url = excluded.source_url
                """,
                (session_id, operation, source_url),
            )
            connection.commit()

    def clear_pending_artifact_url(self, session_id: str, operation: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM pending_provider_artifacts WHERE session_id = ? AND operation = ?",
                (session_id, operation),
            )
            connection.commit()

    def list(self) -> list[SessionSnapshot]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT snapshot_json FROM sessions ORDER BY rowid ASC"
            ).fetchall()
        return [SessionSnapshot.model_validate_json(row[0]) for row in rows]


class ArtifactStore:
    """Stores normalized references, indexed generated images, and GLB downloads."""

    def __init__(self, settings: Settings) -> None:
        self._data_dir = settings.data_dir.expanduser().resolve()
        self._max_upload_bytes = settings.max_upload_bytes
        self._max_upload_pixels = settings.max_upload_pixels
        self._max_remote_download_bytes = settings.meshy_max_download_bytes
        self._max_uncompressed_3mf_bytes = settings.meshy_max_uncompressed_3mf_bytes
        self._uploads_dir = self._data_dir / "uploads"
        self._images_dir = self._data_dir / "images"
        self._models_dir = self._data_dir / "models"
        self._repaired_models_dir = self._data_dir / "repaired-models"
        self._print_files_dir = self._data_dir / "print-files"
        for directory in (
            self._uploads_dir,
            self._images_dir,
            self._models_dir,
            self._repaired_models_dir,
            self._print_files_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
    def delete_session(self, session_id: str) -> None:
        """Remove all artifact directories owned by one validated session."""
        if not _SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("Invalid session identifier")
        for root in (
            self._uploads_dir,
            self._images_dir,
            self._models_dir,
            self._repaired_models_dir,
            self._print_files_dir,
        ):
            directory = self._confined_path(root / session_id)
            if directory.exists():
                shutil.rmtree(directory)

    def save_reference(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        media_type: str | None = None,
    ) -> Path:
        """Decode untrusted upload content and publish a metadata-free PNG."""
        del filename, media_type
        normalized = self._normalize_to_png(content, "Reference image")
        return self._atomic_write(
            self._session_directory(self._uploads_dir, session_id) / "reference.png", normalized
        )

    def save_generated_image(
        self,
        session_id: str,
        image_index: int,
        content: bytes,
        media_type: str = "image/png",
    ) -> Path:
        """Decode and atomically persist one indexed provider image as PNG."""
        if image_index not in range(4):
            raise ValueError("Generated image index must be between 0 and 3")
        del media_type
        normalized = self._normalize_to_png(content, "Generated image")
        return self._atomic_write(
            self._session_directory(self._images_dir, session_id) / f"image-{image_index}.png",
            normalized,
        )

    def _normalize_to_png(self, content: bytes, label: str) -> bytes:
        data = self._as_byte_view(content)
        if data.nbytes == 0:
            raise ValueError(f"{label} is empty")
        if data.nbytes > self._max_upload_bytes:
            raise ValueError(f"{label} exceeds {self._max_upload_bytes} bytes")
        try:
            from PIL import Image, ImageOps, UnidentifiedImageError
        except ImportError as exc:
            raise ValueError("Pillow is required to process image uploads") from exc

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as opened:
                    opened.verify()
                with Image.open(io.BytesIO(data)) as opened:
                    if opened.width * opened.height > self._max_upload_pixels:
                        raise ValueError(f"{label} exceeds {self._max_upload_pixels} pixels")
                    opened.seek(0)  # GIF and TIFF use their first frame.
                    image = ImageOps.exif_transpose(opened)
                    image.load()
                    if image.width * image.height > self._max_upload_pixels:
                        raise ValueError(f"{label} exceeds {self._max_upload_pixels} pixels")
                    if image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info:
                        image = image.convert("RGBA")
                    else:
                        image = image.convert("RGB")
                    output = io.BytesIO()
                    image.save(output, format="PNG")
        except ValueError:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError(f"{label} is not a supported safe image") from exc
        except Exception as exc:
            raise ValueError(f"{label} could not be decoded") from exc

        normalized = output.getvalue()
        if not normalized or len(normalized) > self._max_upload_bytes:
            raise ValueError(f"Normalized {label.lower()} exceeds {self._max_upload_bytes} bytes")
        return normalized

    async def download_model(self, session_id: str, glb_url: str) -> Path:
        return await asyncio.to_thread(
            self._download_validated,
            session_id,
            glb_url,
            self._models_dir,
            "model.glb",
            _TENCENT_MODEL_HOST_SUFFIXES,
            self._validate_glb,
        )

    async def download_repaired_model(self, session_id: str, glb_url: str) -> Path:
        return await asyncio.to_thread(
            self._download_validated,
            session_id,
            glb_url,
            self._repaired_models_dir,
            "repaired-model.glb",
            _MESHY_MODEL_HOST_SUFFIXES,
            self._validate_glb,
        )

    async def download_print_file(self, session_id: str, file_url: str) -> Path:
        return await asyncio.to_thread(
            self._download_validated,
            session_id,
            file_url,
            self._print_files_dir,
            "print.3mf",
            _MESHY_MODEL_HOST_SUFFIXES,
            self._validate_3mf,
        )

    def calibrated_print_file_path(self, session_id: str) -> Path:
        """Return the confined destination for the post-print calibration copy."""
        return self._session_directory(self._print_files_dir, session_id) / "print-calibrated.3mf"
    def geometry_print_file_path(self, session_id: str) -> Path:
        """Return the confined destination for a geometry-only 3MF copy."""
        return self._session_directory(self._print_files_dir, session_id) / "print-geometry.3mf"


    def _download_validated(
        self,
        session_id: str,
        source_url: str,
        root: Path,
        filename: str,
        allowed_suffixes: tuple[str, ...],
        validator: Callable[[Path], None],
    ) -> Path:
        assert_allowed_https_host(source_url, allowed_suffixes)
        destination = self._session_directory(root, session_id) / filename
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                request = Request(source_url, headers={"User-Agent": "3d-print-agent/1.0"})
                opener = build_opener(_PublicRedirectHandler(allowed_suffixes))
                with opener.open(request, timeout=60.0) as response:
                    assert_allowed_https_host(response.geturl(), allowed_suffixes)
                    length = response.headers.get("Content-Length")
                    if length is not None and (not length.isdigit() or int(length) > self._max_remote_download_bytes):
                        raise ValueError("Downloaded artifact exceeds the allowed size")
                    size = 0
                    while chunk := response.read(_COPY_CHUNK_SIZE):
                        size += len(chunk)
                        if size > self._max_remote_download_bytes:
                            raise ValueError("Downloaded artifact exceeds the allowed size")
                        temporary_file.write(chunk)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            validator(temporary_path)
            os.replace(temporary_path, destination)
            return self._confined_path(destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _as_byte_view(content: bytes) -> memoryview:
        try:
            data = memoryview(content)
        except TypeError as error:
            raise ValueError("Artifact content must be bytes") from error
        if data.ndim != 1 or not data.contiguous:
            raise ValueError("Artifact content must be a contiguous byte sequence")
        return data.cast("B")

    @staticmethod
    def _validate_glb(path: Path) -> None:
        file_size = path.stat().st_size
        with path.open("rb") as model_file:
            header = model_file.read(12)
        if len(header) != 12 or header[:4] != b"glTF":
            raise ValueError("Downloaded model is not a GLB file")
        version, declared_size = struct.unpack("<II", header[4:12])
        if version != 2 or declared_size != file_size:
            raise ValueError("Downloaded GLB has an invalid header")

    def _validate_3mf(self, path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                total_size = sum(member.file_size for member in members)
                if total_size > self._max_uncompressed_3mf_bytes:
                    raise ValueError("Downloaded 3MF exceeds the allowed uncompressed size")
                names = {member.filename for member in members}
                has_model = any(
                    name.startswith("3D/") and name.endswith(".model") for name in names
                )
                if "[Content_Types].xml" not in names or not has_model:
                    raise ValueError("Downloaded print file is not a valid 3MF archive")
                if archive.testzip() is not None:
                    raise ValueError("Downloaded print file is corrupt")
        except zipfile.BadZipFile as exc:
            raise ValueError("Downloaded print file is not a valid 3MF archive") from exc

    def _session_directory(self, root: Path, session_id: str) -> Path:
        if not _SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("Invalid session identifier")
        directory = root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        return self._confined_path(directory)

    def _atomic_write(self, destination: Path, content: bytes | memoryview) -> Path:
        destination = self._confined_path(destination)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, destination)
            return self._confined_path(destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _confined_path(self, path: Path) -> Path:
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(self._data_dir)
        except ValueError as error:
            raise ValueError("Artifact path escapes the configured data directory") from error
        return resolved_path
