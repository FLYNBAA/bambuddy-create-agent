from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException

from backend.app.api.routes.bca_tasks import _validate_model_3mf, _validate_sliced_3mf


def _package(*members: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("3D/3dmodel.model", "<model />")
        for member in members:
            archive.writestr(member, "G1 X1" if member.endswith(".gcode") else "<config />")
    return output.getvalue()


def test_model_validation_does_not_mistake_model_3mf_for_sliced_job() -> None:
    model = _package()
    _validate_model_3mf(model)
    with pytest.raises(HTTPException, match="plate_N.gcode"):
        _validate_sliced_3mf(model)


def test_sliced_validation_requires_gcode_and_slice_info() -> None:
    sliced = _package("Metadata/plate_1.gcode", "Metadata/slice_info.config")
    _validate_sliced_3mf(sliced)

def test_model_validation_rejects_unsafe_duplicate_members() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("3D/3dmodel.model", "<model />")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("3D/3dmodel.model", "<model />")

    with pytest.raises(HTTPException, match="safe valid 3MF"):
        _validate_model_3mf(output.getvalue())


def test_model_validation_accepts_standard_empty_directory_entries() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("_rels/", b"")
        archive.writestr("3D/", b"")
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("3D/3dmodel.model", "<model />")

    _validate_model_3mf(output.getvalue())


def test_model_validation_rejects_nonempty_directory_entry() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("3D/", b"not-a-directory")
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("3D/3dmodel.model", "<model />")

    with pytest.raises(HTTPException, match="unsafe 3MF directory member"):
        _validate_model_3mf(output.getvalue())
