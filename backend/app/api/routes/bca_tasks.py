"""BCA task list: model files wait for root-provided sliced 3MF before queueing."""

from __future__ import annotations

import asyncio
import io
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.library import save_3mf_bytes_to_library
from backend.app.api.routes.print_queue import add_to_queue
from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.bca_task import BCATask
from backend.app.models.user import User
from backend.app.schemas.print_queue import PrintQueueItemCreate
from backend.app.three_d_agent.calibration import CalibrationError, CalibrationLimits, validate_3mf_package

_BCA_TASK_3MF_LIMITS = CalibrationLimits()
_MAX_BCA_TASK_UPLOAD_BYTES = _BCA_TASK_3MF_LIMITS.max_input_bytes

router = APIRouter(prefix="/bca-tasks", tags=["bca-tasks"])


class BCATaskResponse(BaseModel):
    id: int
    session_id: str | None
    filename: str
    status: str
    sliced_library_file_id: int | None
    print_queue_item_id: int | None
    created_by: str
    created_at: str
    updated_at: str


class BCATaskQueueRequest(BaseModel):
    printer_id: int = Field(gt=0)
    plate_id: int | None = Field(default=None, ge=1)


def _response(task: BCATask, user_name: str = "root") -> BCATaskResponse:
    return BCATaskResponse(
        id=task.id,
        session_id=task.session_id,
        filename=task.filename,
        status=task.status,
        sliced_library_file_id=task.sliced_library_file_id,
        print_queue_item_id=task.print_queue_item_id,
        created_by=user_name,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )


def _archive_members(content: bytes) -> set[str]:
    if len(content) > _MAX_BCA_TASK_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="3MF exceeds the 100 MB upload limit")
    try:
        validate_3mf_package(content, limits=_BCA_TASK_3MF_LIMITS)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return set(archive.namelist())
    except CalibrationError as exc:
        raise HTTPException(status_code=422, detail="File is not a safe valid 3MF archive") from exc
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
        raise HTTPException(status_code=422, detail="File is not a valid 3MF archive") from exc


def _validate_model_3mf(content: bytes) -> None:
    names = _archive_members(content)
    if "[Content_Types].xml" not in names or not any(name.startswith("3D/") and name.endswith(".model") for name in names):
        raise HTTPException(status_code=422, detail="File is not a valid model 3MF archive")


def _validate_sliced_3mf(content: bytes) -> None:
    names = _archive_members(content)
    if not any(name.startswith("Metadata/plate_") and name.endswith(".gcode") for name in names):
        raise HTTPException(status_code=422, detail="Sliced 3MF must contain Metadata/plate_N.gcode")
    if "Metadata/slice_info.config" not in names:
        raise HTTPException(status_code=422, detail="Sliced 3MF must contain Metadata/slice_info.config")


def _task_root() -> Path:
    root = Path(settings.base_dir) / "bca-tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.get("", response_model=list[BCATaskResponse])
async def list_bca_tasks(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_READ_ALL),
) -> list[BCATaskResponse]:
    result = await db.execute(select(BCATask).order_by(BCATask.created_at.desc(), BCATask.id.desc()))
    return [_response(task) for task in result.scalars().all()]


@router.post("", response_model=BCATaskResponse, status_code=201)
async def upload_bca_task(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.LIBRARY_UPLOAD),
) -> BCATaskResponse:
    filename = file.filename or "model.3mf"
    if not filename.lower().endswith(".3mf"):
        raise HTTPException(status_code=422, detail="BCA task files must use .3mf")
    content = await file.read(_MAX_BCA_TASK_UPLOAD_BYTES + 1)
    _validate_model_3mf(content)
    source = _task_root() / f"{uuid.uuid4().hex}.3mf"
    await asyncio.to_thread(source.write_bytes, content)
    task = BCATask(
        filename=filename,
        source_path=str(source),
        status="awaiting_slice",
        created_by_id=current_user.id if current_user else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _response(task, current_user.username if current_user else "root")


@router.get("/{task_id}/source")
async def download_bca_task_source(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_READ_ALL),
) -> FileResponse:
    task = await db.get(BCATask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="BCA task not found")
    source = Path(task.source_path).resolve()
    try:
        source.relative_to(_task_root().resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="BCA task file not found") from exc
    if not source.is_file():
        raise HTTPException(status_code=404, detail="BCA task file not found")
    return FileResponse(source, media_type="model/3mf", filename=task.filename)


@router.post("/{task_id}/sliced", response_model=BCATaskResponse)
async def attach_sliced_bca_task(
    task_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.LIBRARY_UPLOAD),
) -> BCATaskResponse:
    task = await db.get(BCATask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="BCA task not found")
    if task.status not in {"awaiting_slice", "slice_requested", "slice_failed"}:
        raise HTTPException(status_code=409, detail=f"Task cannot accept a sliced file in status '{task.status}'")
    filename = file.filename or f"{Path(task.filename).stem}.gcode.3mf"
    if not filename.lower().endswith(".gcode.3mf"):
        raise HTTPException(status_code=422, detail="Sliced task file must use .gcode.3mf")
    content = await file.read(_MAX_BCA_TASK_UPLOAD_BYTES + 1)
    _validate_sliced_3mf(content)
    library_file, _ = await save_3mf_bytes_to_library(
        db,
        file_bytes=content,
        filename=filename,
        source_type="bca_task_slice",
        owner_id=current_user.id if current_user else None,
    )
    task.sliced_library_file_id = library_file.id
    task.status = "ready_for_queue"
    await db.commit()
    await db.refresh(task)
    return _response(task, current_user.username if current_user else "root")


@router.post("/{task_id}/queue", response_model=BCATaskResponse)
async def queue_bca_task(
    task_id: int,
    payload: BCATaskQueueRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> BCATaskResponse:
    task = await db.get(BCATask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="BCA task not found")
    if task.status != "ready_for_queue" or task.sliced_library_file_id is None:
        raise HTTPException(status_code=409, detail="Root must attach a validated sliced 3MF before queueing")
    queue_item = await add_to_queue(
        PrintQueueItemCreate(
            library_file_id=task.sliced_library_file_id,
            printer_id=payload.printer_id,
            plate_id=payload.plate_id,
            manual_start=True,
        ),
        db,
        current_user,
    )
    task.print_queue_item_id = queue_item.id
    task.status = "queued"
    await db.commit()
    await db.refresh(task)
    return _response(task, current_user.username if current_user else "root")


@router.delete("/{task_id}", status_code=204)
async def delete_bca_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_DELETE_ALL),
) -> None:
    task = await db.get(BCATask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="BCA task not found")
    source = Path(task.source_path)
    await db.delete(task)
    await db.commit()
    await asyncio.to_thread(source.unlink, missing_ok=True)
