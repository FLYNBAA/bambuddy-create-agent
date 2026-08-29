"""HTTP API for the embedded BCA creator workspace."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes._url_safety import assert_safe_lan_service_url
from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.bca_task import BCATask
from backend.app.models.user import User
from backend.app.services.creator_integration import (
    CreatorSessionResponse,
    ImageSelectionRequest,
    confined_artifact,
    controller_for,
    file_response,
    image_artifact,
    persist_creator_config_overrides,
)
from backend.app.three_d_agent.conversation import CreatorCommand
from backend.app.three_d_agent.providers.exceptions import ProviderConfigurationError, ProviderError

router = APIRouter(prefix="/creator", tags=["creator"])


class PrintGenerationRequest(BaseModel):
    max_colors: int = Field(default=8, ge=1, le=8)
    acknowledge_issues: bool = False


class CreatorTaskRequest(BaseModel):
    mode: str = Field(pattern="^(multicolor|geometry)$")


class CreatorTaskResponse(BaseModel):
    task_id: int
    status: str


class CreatorChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CreatorChatResponse(BaseModel):
    session: CreatorSessionResponse
    action: str
    reply: str

class CreatorRestartRequest(BaseModel):
    stage: str = Field(pattern="^(brief|images|model|print)$")

class CreatorConfigResponse(BaseModel):
    deepseek_base_url: str
    deepseek_model: str
    image_base_url: str
    image_model: str
    image_quality: str
    meshy_model_input_mode: str
    app_public_base_url: str
    configured: dict[str, bool]


class CreatorConfigUpdate(BaseModel):
    deepseek_base_url: str | None = None
    deepseek_model: str | None = None
    image_base_url: str | None = None
    image_model: str | None = None
    image_quality: str | None = None
    meshy_model_input_mode: str | None = None
    app_public_base_url: str | None = None


def _config_response(controller) -> CreatorConfigResponse:
    config = controller.settings
    return CreatorConfigResponse(
        deepseek_base_url=config.deepseek_base_url,
        deepseek_model=config.deepseek_model,
        image_base_url=config.image_base_url,
        image_model=config.image_model,
        image_quality=config.image_quality,
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

def _print_issues_require_acknowledgment(snapshot) -> bool:
    report = snapshot.print_analysis.report
    return report is not None and report.status != "healthy"


def _message_acknowledges_print_issues(message: str) -> bool:
    normalized = "".join(message.split())
    return any(
        phrase in normalized
        for phrase in (
            "已了解打印分析报告中的问题",
            "已了解报告中的问题",
            "已知悉打印问题",
            "已知悉风险",
            "接受打印风险",
        )
    )


def _validate_creator_provider_urls(payload: CreatorConfigUpdate) -> None:
    if payload.deepseek_base_url is not None:
        assert_safe_lan_service_url(payload.deepseek_base_url, label="DeepSeek base URL")
    if payload.image_base_url is not None:
        assert_safe_lan_service_url(payload.image_base_url, label="image-provider base URL")


def _snapshot(request: Request, session_id: str) -> CreatorSessionResponse:
    try:
        return _controller(request).snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc


@router.get("/config", response_model=CreatorConfigResponse)
def get_creator_config(
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SETTINGS_READ),
) -> CreatorConfigResponse:
    return _config_response(_controller(request))


@router.put("/config", response_model=CreatorConfigResponse)
async def update_creator_config(
    payload: CreatorConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SETTINGS_UPDATE),
) -> CreatorConfigResponse:
    try:
        _validate_creator_provider_urls(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    controller = _controller(request)
    current = _config_response(controller)
    values = {
        "deepseek_base_url": current.deepseek_base_url,
        "deepseek_model": current.deepseek_model,
        "image_base_url": current.image_base_url,
        "image_model": current.image_model,
        "image_quality": current.image_quality,
        "meshy_model_input_mode": current.meshy_model_input_mode,
        "app_public_base_url": current.app_public_base_url,
    }
    values.update(payload.model_dump(exclude_none=True))
    try:
        controller.reconfigure(**values)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await persist_creator_config_overrides(db, values)
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
    message: str = Form(""),
    reference_image: UploadFile | None = File(default=None),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> CreatorSessionResponse:
    controller = _controller(request)
    content = await reference_image.read() if reference_image else None
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


async def _queue_stage(session_id: str, request: Request, stage: str, queue, run) -> CreatorSessionResponse:
    controller = _controller(request)
    try:
        await queue(session_id)
        controller.schedule(session_id, stage, run(session_id))
        return controller.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/chat", response_model=CreatorChatResponse)
async def creator_chat(
    session_id: str,
    payload: CreatorChatRequest,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> CreatorChatResponse:
    controller = _controller(request)
    try:
        controller.agent.record_conversation_message(session_id, "user", payload.message)
        snapshot = controller.agent.get_session(session_id)
        command: CreatorCommand = await controller.planner.plan(snapshot, payload.message)
        paid_actions = {"confirm_images", "confirm_3d", "generate_print_file"}
        if command.action in paid_actions and (not command.explicit_confirmation or "确认" not in payload.message):
            command = command.model_copy(
                update={
                    "action": "restart_question",
                    "reply": "这是付费阶段。请明确回复“确认”并说明要继续的阶段，或直接点击工作卡片上的确认按钮。",
                }
            )
        if command.action == "generate_print_file" and _print_issues_require_acknowledgment(snapshot):
            if not (command.acknowledge_issues and _message_acknowledges_print_issues(payload.message)):
                command = command.model_copy(
                    update={
                        "action": "restart_question",
                        "reply": "打印分析发现问题。请先明确回复“我已了解打印分析报告中的问题，确认继续生成多色 3MF”，或在工作卡片勾选确认。",
                    }
                )
        if command.action == "prepare":
            await controller.agent.prepare(session_id, payload.message)
        elif command.action == "confirm_images":
            await controller.agent.queue_image_generation(session_id)
            controller.schedule(session_id, "images", controller.agent.run_image_generation(session_id))
        elif command.action == "select_image":
            if command.image_index is None:
                raise ValueError("请选择一张候选图后再继续。")
            await controller.agent.select_image(session_id, command.image_index)
        elif command.action == "confirm_3d":
            await controller.agent.queue_3d_generation(session_id)
            controller.schedule(session_id, "model", controller.agent.run_3d_generation(session_id))
        elif command.action == "analyze":
            await controller.agent.queue_print_analysis(session_id)
            controller.schedule(session_id, "analysis", controller.agent.run_print_analysis(session_id))
        elif command.action == "generate_print_file":
            await controller.agent.queue_print_file(
                session_id,
                max_colors=8,
                acknowledge_issues=_print_issues_require_acknowledgment(snapshot),
            )
            controller.schedule(session_id, "print-file", controller.agent.run_print_file(session_id))
        elif command.action == "geometry":
            controller.schedule(session_id, "geometry", controller.agent.generate_geometry_print_file(session_id))
        elif command.action == "calibrate":
            await controller.agent.queue_color_calibration(session_id)
            controller.schedule(session_id, "calibration", controller.agent.run_color_calibration(session_id))
        controller.agent.record_conversation_message(session_id, "assistant", command.reply)
        return CreatorChatResponse(session=controller.snapshot(session_id), action=command.action, reply=command.reply)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Creator chat provider is not configured") from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail="Creator chat provider request failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/restart", response_model=CreatorSessionResponse)
async def restart_creator_session(
    session_id: str,
    payload: CreatorRestartRequest,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> CreatorSessionResponse:
    controller = _controller(request)
    try:
        await controller.agent.restart_from_stage(session_id, payload.stage)
        return controller.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.post("/sessions/{session_id}/confirm-image", response_model=CreatorSessionResponse, status_code=202)
async def confirm_creator_image(
    session_id: str, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)
) -> CreatorSessionResponse:
    controller = _controller(request)
    return await _queue_stage(session_id, request, "images", controller.agent.queue_image_generation, controller.agent.run_image_generation)


@router.post("/sessions/{session_id}/select-image", response_model=CreatorSessionResponse)
async def select_creator_image(
    session_id: str,
    selection: ImageSelectionRequest,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> CreatorSessionResponse:
    controller = _controller(request)
    try:
        await controller.agent.select_image(session_id, selection.image_index)
        return controller.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/confirm-3d", response_model=CreatorSessionResponse, status_code=202)
async def confirm_creator_3d(
    session_id: str, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)
) -> CreatorSessionResponse:
    controller = _controller(request)
    return await _queue_stage(session_id, request, "model", controller.agent.queue_3d_generation, controller.agent.run_3d_generation)


@router.post("/sessions/{session_id}/print/analyze", response_model=CreatorSessionResponse, status_code=202)
async def analyze_creator_model(
    session_id: str, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)
) -> CreatorSessionResponse:
    controller = _controller(request)
    return await _queue_stage(session_id, request, "analysis", controller.agent.queue_print_analysis, controller.agent.run_print_analysis)


@router.post("/sessions/{session_id}/print/generate", response_model=CreatorSessionResponse, status_code=202)
async def generate_creator_print_file(
    session_id: str,
    generation: PrintGenerationRequest,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> CreatorSessionResponse:
    controller = _controller(request)
    try:
        await controller.agent.queue_print_file(
            session_id,
            max_colors=generation.max_colors,
            acknowledge_issues=generation.acknowledge_issues,
        )
        controller.schedule(session_id, "print-file", controller.agent.run_print_file(session_id))
        return controller.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/print/geometry", response_model=CreatorSessionResponse, status_code=202)
async def geometry_creator_print_file(
    session_id: str, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)
) -> CreatorSessionResponse:
    controller = _controller(request)
    try:
        controller.agent.get_session(session_id)
        controller.schedule(session_id, "geometry", controller.agent.generate_geometry_print_file(session_id))
        return controller.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Creator session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/print/calibrate", response_model=CreatorSessionResponse, status_code=202)
async def calibrate_creator_print_file(
    session_id: str, request: Request, _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE)
) -> CreatorSessionResponse:
    controller = _controller(request)
    return await _queue_stage(session_id, request, "calibration", controller.agent.queue_color_calibration, controller.agent.run_color_calibration)


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
    source_value = snapshot.calibrated_print_file_path if payload.mode == "multicolor" else snapshot.geometry_print_file_path
    if not source_value:
        raise HTTPException(status_code=409, detail="The selected calibration output is not complete")
    source = Path(source_value).resolve()
    agent_root = (Path(settings.base_dir) / "bca-agent").resolve()
    try:
        source.relative_to(agent_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Creator artifact not found") from exc
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Creator artifact not found")
    task_root = Path(settings.base_dir) / "bca-tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    destination = task_root / f"{uuid.uuid4().hex}.3mf"
    await asyncio.to_thread(shutil.copyfile, source, destination)
    task = BCATask(
        session_id=session_id,
        filename=f"{source.stem}.3mf",
        source_path=str(destination),
        status="awaiting_slice",
        created_by_id=current_user.id if current_user else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return CreatorTaskResponse(task_id=task.id, status=task.status)

@router.get("/sessions/{session_id}/{artifact}.glb", include_in_schema=False)
def download_creator_public_glb(
    session_id: str,
    artifact: str,
    request: Request,
) -> FileResponse:
    """Provider-facing capability route for Meshy's public-url model input.

    This route intentionally accepts no user credential: the high-entropy session
    ID is the provider capability, and the only accepted artifacts are GLBs
    confined to the creator's artifact root. It is never surfaced in snapshots.
    """
    if artifact not in {"model", "repaired-model"}:
        raise HTTPException(status_code=404, detail="Creator artifact not found")
    controller = _controller(request)
    try:
        path = confined_artifact(controller.agent.get_session(session_id), artifact)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Creator artifact not found") from exc
    return file_response(path, "model/gltf-binary", f"{session_id}-{artifact}.glb")


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
    if artifact not in {"model", "print-file", "calibrated-print-file", "geometry-print-file"}:
        raise HTTPException(status_code=404, detail="Creator artifact not found")
    controller = _controller(request)
    try:
        path = confined_artifact(controller.agent.get_session(session_id), artifact)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Creator artifact not found") from exc
    media_type = "model/gltf-binary" if artifact == "model" else "model/3mf"
    extension = ".glb" if artifact == "model" else ".3mf"
    return file_response(path, media_type, f"{session_id}-{artifact}{extension}")
