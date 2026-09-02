"""HTTP API for the embedded BCA creator workspace."""

from __future__ import annotations

import asyncio
import secrets
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes._url_safety import assert_safe_lan_service_url
from backend.app.api.routes.bca_tasks import _validate_model_3mf
from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.bca_task import BCATask
from backend.app.models.user import User
from backend.app.services.creator_integration import (
    CreatorSessionResponse,
    confined_artifact,
    controller_for,
    file_response,
    image_artifact,
    persist_creator_config_overrides,
)
from backend.app.three_d_agent.contracts import SubworkflowStatus
from backend.app.three_d_agent.providers.exceptions import ProviderConfigurationError, ProviderError

router = APIRouter(prefix="/creator", tags=["creator"])

_SECRET_CONFIG_KEYS = frozenset(
    {"deepseek_api_key", "image_api_key", "tencent_secret_id", "tencent_secret_key", "meshy_api_key"}
)


class ModelGenerationRequest(BaseModel):
    image_index: int = Field(ge=0, le=3)


class PrintCalibrationRequest(BaseModel):
    mode: str = Field(pattern="^(white|multicolor)$")
    max_colors: int = Field(default=8, ge=1, le=8)


class CreatorTaskRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    customer_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=40)
    address: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


    @field_validator("customer_name", "phone", "address")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("title", "notes")
    @classmethod
    def optional_text_is_normalized(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

class CreatorTaskResponse(BaseModel):
    task_id: int
    status: str



class CreatorRestartRequest(BaseModel):
    stage: str = Field(pattern="^(brief|images|model|print)$")

class CreatorConfigResponse(BaseModel):
    """Non-secret Creator provider configuration safe to expose to administrators."""

    deepseek_base_url: str
    deepseek_model: str
    image_base_url: str
    image_model: str
    image_quality: str
    tencent_region: str
    meshy_base_url: str
    meshy_model_input_mode: str
    app_public_base_url: str
    configured: dict[str, bool]


class CreatorConfigUpdate(BaseModel):
    # Secrets are write-only: they are accepted for a hot reload, persisted by
    # the server, and never serialized in a response.
    deepseek_api_key: str | None = None
    deepseek_base_url: str | None = None
    deepseek_model: str | None = None
    image_api_key: str | None = None
    image_base_url: str | None = None
    image_model: str | None = None
    image_quality: str | None = None
    tencent_secret_id: str | None = None
    tencent_secret_key: str | None = None
    tencent_region: str | None = None
    meshy_api_key: str | None = None
    meshy_base_url: str | None = None
    meshy_model_input_mode: str | None = None
    app_public_base_url: str | None = None


def _config_values(controller) -> dict[str, str]:
    """Build the server-only complete configuration used for a hot reload."""
    config = controller.settings
    return {
        "deepseek_api_key": config.deepseek_api_key.get_secret_value(),
        "deepseek_base_url": config.deepseek_base_url,
        "deepseek_model": config.deepseek_model,
        "image_api_key": config.image_api_key.get_secret_value(),
        "image_base_url": config.image_base_url,
        "image_model": config.image_model,
        "image_quality": config.image_quality,
        "tencent_secret_id": config.tencent_secret_id.get_secret_value(),
        "tencent_secret_key": config.tencent_secret_key.get_secret_value(),
        "tencent_region": config.tencent_region,
        "meshy_api_key": config.meshy_api_key.get_secret_value(),
        "meshy_base_url": config.meshy_base_url,
        "meshy_model_input_mode": config.meshy_model_input_mode,
        "app_public_base_url": config.app_public_base_url,
    }


def _config_response(controller) -> CreatorConfigResponse:
    config = controller.settings
    return CreatorConfigResponse(
        deepseek_base_url=config.deepseek_base_url,
        deepseek_model=config.deepseek_model,
        image_base_url=config.image_base_url,
        image_model=config.image_model,
        image_quality=config.image_quality,
        tencent_region=config.tencent_region,
        meshy_base_url=config.meshy_base_url,
        meshy_model_input_mode=config.meshy_model_input_mode,
        app_public_base_url=config.app_public_base_url,
        configured={
            "deepseek": bool(config.deepseek_api_key.get_secret_value().strip()),
            "image": bool(config.image_api_key.get_secret_value().strip()),
            "hunyuan": bool(config.tencent_secret_id.get_secret_value().strip() and config.tencent_secret_key.get_secret_value().strip()),
            "meshy": bool(config.meshy_api_key.get_secret_value().strip()),
        },
    )


def _controller(request: Request):
    return controller_for(request)



def _validate_creator_provider_urls(payload: CreatorConfigUpdate) -> None:
    if payload.deepseek_base_url is not None:
        assert_safe_lan_service_url(payload.deepseek_base_url, label="DeepSeek base URL")
    if payload.image_base_url is not None:
        assert_safe_lan_service_url(payload.image_base_url, label="image-provider base URL")
    if payload.meshy_base_url is not None:
        assert_safe_lan_service_url(payload.meshy_base_url, label="Meshy base URL")


def _snapshot(request: Request, session_id: str) -> CreatorSessionResponse:
    try:
        return _controller(request).snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc


@router.get("/config", response_model=CreatorConfigResponse)
def get_creator_config(
    request: Request,
    response: Response,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SETTINGS_UPDATE),
) -> CreatorConfigResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return _config_response(_controller(request))


@router.put("/config", response_model=CreatorConfigResponse)
async def update_creator_config(
    payload: CreatorConfigUpdate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SETTINGS_UPDATE),
) -> CreatorConfigResponse:
    try:
        _validate_creator_provider_urls(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc), headers={"Cache-Control": "private, no-store"}) from exc
    controller = _controller(request)
    values = _config_values(controller)
    values.update({
        key: value
        for key, value in payload.model_dump(exclude_none=True).items()
        if key not in _SECRET_CONFIG_KEYS or value.strip()
    })
    try:
        controller.reconfigure(**values)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers={"Cache-Control": "private, no-store"}) from exc
    await persist_creator_config_overrides(db, values)
    response.headers["Cache-Control"] = "private, no-store"
    return _config_response(controller)

@router.get("/sessions", response_model=list[CreatorSessionResponse])
def list_creator_sessions(
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_READ_ALL),
) -> list[CreatorSessionResponse]:
    controller = _controller(request)
    return [controller.snapshot(item.session_id) for item in controller.agent.list_sessions()]


@router.post("/sessions", response_model=CreatorSessionResponse, status_code=201)
def create_creator_session(
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> CreatorSessionResponse:
    controller = _controller(request)
    session = controller.agent.create_session()
    return controller.snapshot(session.session_id)


@router.get("/sessions/{session_id}", response_model=CreatorSessionResponse)
def get_creator_session(
    session_id: str,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_READ_ALL),
) -> CreatorSessionResponse:
    return _snapshot(request, session_id)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_creator_session(
    session_id: str,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_DELETE_ALL),
) -> None:
    controller = _controller(request)
    try:
        controller.agent.delete_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/prepare", response_model=CreatorSessionResponse)
async def prepare_creator_session(
    session_id: str,
    request: Request,
    message: str = Form("", max_length=4000),
    reference_image: UploadFile | None = File(default=None),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> CreatorSessionResponse:
    controller = _controller(request)
    content = await reference_image.read(controller.settings.max_upload_bytes + 1) if reference_image else None
    if content is not None and len(content) > controller.settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Reference image exceeds the upload limit")
    try:
        controller.agent.get_session(session_id)
        await controller.agent.prepare(
            session_id,
            message,
            reference_image_name=reference_image.filename if reference_image else None,
            reference_image_content=content,
            reference_image_media_type=reference_image.content_type if reference_image else None,
        )
        return controller.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _queue_stage(session_id: str, request: Request, stage: str, queue, run, *args, **kwargs) -> CreatorSessionResponse:
    controller = _controller(request)
    try:
        await queue(session_id, *args, **kwargs)
        controller.schedule(session_id, stage, run(session_id))
        return controller.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/restart", response_model=CreatorSessionResponse)
async def restart_creator_session(session_id: str, payload: CreatorRestartRequest, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)) -> CreatorSessionResponse:
    controller = _controller(request)
    try:
        await controller.agent.restart_from_stage(session_id, payload.stage)
        return controller.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/images/generate", response_model=CreatorSessionResponse, status_code=202)
async def generate_creator_images(session_id: str, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)) -> CreatorSessionResponse:
    controller = _controller(request)
    return await _queue_stage(session_id, request, "images", controller.agent.queue_image_generation, controller.agent.run_image_generation)


@router.post("/sessions/{session_id}/model/generate", response_model=CreatorSessionResponse, status_code=202)
async def generate_creator_model(session_id: str, payload: ModelGenerationRequest, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)) -> CreatorSessionResponse:
    controller = _controller(request)
    return await _queue_stage(session_id, request, "model", controller.agent.queue_3d_generation, controller.agent.run_3d_generation, payload.image_index)


@router.post("/sessions/{session_id}/print/calibrate", response_model=CreatorSessionResponse, status_code=202)
async def calibrate_creator_print_file(session_id: str, payload: PrintCalibrationRequest, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)) -> CreatorSessionResponse:
    controller = _controller(request)
    return await _queue_stage(session_id, request, "calibration", controller.agent.queue_color_calibration, controller.agent.run_color_calibration, mode=payload.mode, max_colors=payload.max_colors)


@router.post("/sessions/{session_id}/print/analyze", response_model=CreatorSessionResponse, status_code=202)
async def analyze_creator_model(session_id: str, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)) -> CreatorSessionResponse:
    controller = _controller(request)
    return await _queue_stage(session_id, request, "analysis", controller.agent.queue_print_analysis, controller.agent.run_print_analysis)


def _validate_task_source(path: Path) -> None:
    _validate_model_3mf(path.read_bytes())

@router.post("/sessions/{session_id}/task", response_model=CreatorTaskResponse, status_code=201)

async def push_calibrated_creator_task(
    session_id: str,
    payload: CreatorTaskRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> CreatorTaskResponse:
    controller = _controller(request)
    try:
        snapshot = controller.agent.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    if (
        not snapshot.calibrated_print_file_path
        or snapshot.selected_image_index is None
        or not snapshot.model_path
        or snapshot.print_analysis.status is not SubworkflowStatus.SUCCEEDED
    ):
        raise HTTPException(status_code=409, detail="Final calibration, print analysis, and immutable previews must be complete")
    agent_root = (Path(settings.base_dir) / "bca-agent").resolve()
    sources = [
        Path(snapshot.calibrated_print_file_path).resolve(),
        Path(snapshot.generated_image_paths[snapshot.selected_image_index]).resolve(),
        Path(snapshot.model_path).resolve(),
    ]
    for source in sources:
        try:
            source.relative_to(agent_root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Creator artifact not found") from exc
        if not source.is_file():
            raise HTTPException(status_code=404, detail="Creator artifact not found")
    await asyncio.to_thread(_validate_task_source, sources[0])
    title = (payload.title or "").strip()
    if not title:
        try:
            title = await controller.agent.generate_task_title(session_id)
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=503, detail="Task title provider is not configured") from exc
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail="Task title generation failed") from exc
    task_root = Path(settings.base_dir) / "bca-tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    destinations = [task_root / f"{token}.3mf", task_root / f"{token}.png", task_root / f"{token}.glb"]
    committed = False
    try:
        for source, destination in zip(sources, destinations, strict=True):
            await asyncio.to_thread(shutil.copyfile, source, destination)
        task = BCATask(
            session_id=session_id,
            filename="calibrated-model.3mf",
            source_path=str(destinations[0]),
            style_image_path=str(destinations[1]),
            model_preview_path=str(destinations[2]),
            username=current_user.username if current_user else "root",
            title=title,
            customer_name=payload.customer_name,
            phone=payload.phone,
            address=payload.address,
            notes=payload.notes,
            price=None,
            status="awaiting_slice",
            created_by_id=current_user.id if current_user else None,
        )
        db.add(task)
        await db.flush()
        task_id = task.id
        await db.commit()
        committed = True
    except Exception:
        if not committed:
            await db.rollback()
            for destination in destinations:
                await asyncio.to_thread(destination.unlink, missing_ok=True)
        raise
    return CreatorTaskResponse(task_id=task_id, status="awaiting_slice")

@router.get("/sessions/{session_id}/provider/{capability_token}/model.glb", include_in_schema=False)
def download_creator_provider_glb(
    session_id: str,
    capability_token: str,
    request: Request,
) -> FileResponse:
    """Provider-only GLB capability independent from the browser-visible session ID."""
    controller = _controller(request)
    try:
        snapshot = controller.agent.get_session(session_id)
        if not secrets.compare_digest(snapshot.provider_capability_token, capability_token):
            raise FileNotFoundError("capability")
        path = confined_artifact(snapshot, "model")
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Creator artifact not found") from exc
    return file_response(path, "model/gltf-binary", f"{session_id}-model.glb")


@router.get("/sessions/{session_id}/provider/{capability_token}/calibrated.3mf", include_in_schema=False)
def download_creator_provider_calibrated_print_file(
    session_id: str,
    capability_token: str,
    request: Request,
) -> FileResponse:
    """Provider-only final-3MF capability independent from browser artifact URLs."""
    controller = _controller(request)
    try:
        snapshot = controller.agent.get_session(session_id)
        if not secrets.compare_digest(snapshot.provider_capability_token, capability_token):
            raise FileNotFoundError("capability")
        path = confined_artifact(snapshot, "calibrated-print-file")
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Creator artifact not found") from exc
    return file_response(path, "model/3mf", f"{session_id}-calibrated.3mf")


@router.get("/sessions/{session_id}/images/{image_index}")
def download_creator_image(
    session_id: str,
    image_index: int,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_READ_ALL),
) -> FileResponse:
    controller = _controller(request)
    try:
        path = image_artifact(controller.agent.get_session(session_id), image_index)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Creator image not found") from exc
    return file_response(path, "image/png", f"{session_id}-image-{image_index}.png")


@router.get("/sessions/{session_id}/{artifact}")
def download_creator_artifact(
    session_id: str,
    artifact: str,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_READ_ALL),
) -> FileResponse:
    if artifact not in {"model", "calibrated-print-file"}:
        raise HTTPException(status_code=404, detail="Creator artifact not found")
    controller = _controller(request)
    try:
        path = confined_artifact(controller.agent.get_session(session_id), artifact)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Creator artifact not found") from exc
    media_type = "model/gltf-binary" if artifact == "model" else "model/3mf"
    extension = ".glb" if artifact == "model" else ".3mf"
    return file_response(path, media_type, f"{session_id}-{artifact}{extension}")
