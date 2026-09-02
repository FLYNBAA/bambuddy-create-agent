from __future__ import annotations

import io
import zipfile

import pytest

from backend.app.three_d_agent.calibration import CalibrationLimits
from backend.app.three_d_agent.config import Settings
from backend.app.three_d_agent.storage import ArtifactStore


def _standard_3mf(*, duplicate_model: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("_rels/", b"")
        archive.writestr("3D/", b"")
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("3D/3dmodel.model", "<model />")
        if duplicate_model:
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("3D/3dmodel.model", "<model />")
    return output.getvalue()


def test_downloaded_3mf_uses_the_same_safe_validator_as_uploads(tmp_path) -> None:
    path = tmp_path / "model.3mf"
    path.write_bytes(_standard_3mf())

    ArtifactStore(Settings(data_dir=tmp_path))._validate_3mf(path)


def test_downloaded_3mf_rejects_duplicate_members_before_calibration(tmp_path) -> None:
    path = tmp_path / "duplicate.3mf"
    path.write_bytes(_standard_3mf(duplicate_model=True))

    with pytest.raises(ValueError, match="safe valid 3MF"):
        ArtifactStore(Settings(data_dir=tmp_path))._validate_3mf(path)


def test_calibration_limits_allow_large_compressible_mesh_members() -> None:
    limits = CalibrationLimits()

    assert limits.max_input_bytes == 512 * 1024 * 1024
    assert limits.max_member_bytes == 512 * 1024 * 1024
    assert limits.max_total_uncompressed == 512 * 1024 * 1024
    assert limits.max_members == 2048
    assert limits.max_compression_ratio == 500.0
