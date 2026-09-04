"""Independent Creator capability endpoints for public API clients.

These endpoints deliberately execute one provider capability per request. They do
not create, advance, or require a browser-facing Creator session; callers compose
briefing, Image2, GLB generation, multicolour conversion, calibration, and analysis
in their own workflow.
"""
from __future__ import annotations

import asyncio
import shutil
import struct
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.permissions import Permission
from backend.app.models.user import User
from backend.app.services.creator_integration import controller_for
from backend.app.services.creator_inventory import active_creator_inventory_colors
from backend.app.three_d_agent.calibration import (
    CalibrationError,
    CalibrationLimits,
    ColorAssignment,
    InventoryColor,
    calibrate_3mf,
    inspect_3mf,
)
from backend.app.three_d_agent.color_snapshot import has_color_snapshot, inject_color_snapshot
from backend.app.three_d_agent.contracts import CreativeBrief
from backend.app.three_d_agent.graph import build_preparation_graph, prepare_graph_input
from backend.app.three_d_agent.prompts import response_language
from backend.app.three_d_agent.providers import (
    DeepSeekBriefEnricher,
    DeepSeekColorMatcher,
    DeepSeekPrintAssessor,
    MeshyPrintProvider,
    OpenAICompatibleImageGenerator,
    TencentHunyuan3DGenerator,
)
from backend.app.three_d_agent.providers.exceptions import ProviderConfigurationError, ProviderError
from backend.app.three_d_agent.storage import ArtifactStore

router = APIRouter(prefix="/creator/modules", tags=["creator-modules"])

_LIMITS = CalibrationLimits()
# Meshy's GLB model_url API itself caps input at 100 MiB. Keep that provider
# contract distinct from the wider 3MF calibration/package limit.
_GLB_LIMIT_BYTES = 100 * 1024 * 1024

# Calibration expands and rewrites whole 3MF packages. One process admits one
# such request at a time so a public burst cannot OOM it before validation.
_CALIBRATION_ADMISSION = asyncio.Lock()
_CALIBRATION_SLOT = asyncio.Semaphore(1)
_CALIBRATION_RETRY_AFTER_SECONDS = 120


async def _try_acquire_calibration_slot() -> bool:
    """Atomically reserve the sole large-package calibration slot."""
    async with _CALIBRATION_ADMISSION:
        if _CALIBRATION_SLOT.locked():
            return False
        await _CALIBRATION_SLOT.acquire()
        return True


class BriefModuleRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    current_brief: CreativeBrief = Field(default_factory=CreativeBrief)
    has_reference_image: bool = False




def _module_id() -> str:
    return str(uuid.uuid4())


def _module_directory(request: Request) -> Path:
    root = controller_for(request).settings.data_dir / "module-runs"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="module-", dir=root))


def _cleanup_module(store: ArtifactStore, operation_id: str, workdir: Path | None = None) -> None:
    store.delete_session(operation_id)
    if workdir is not None:
        shutil.rmtree(workdir, ignore_errors=True)


def _file_response(
    path: Path,
    *,
    media_type: str,
    filename: str,
    store: ArtifactStore,
    operation_id: str,
    background_tasks: BackgroundTasks,
    workdir: Path | None = None,
    headers: dict[str, str] | None = None,
) -> FileResponse:
    background_tasks.add_task(_cleanup_module, store, operation_id, workdir)
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        background=background_tasks,
        headers={"X-BCA-Module": "standalone", **(headers or {})},
    )


async def _read_upload(file: UploadFile, max_bytes: int, label: str) -> bytes:
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{label} exceeds the {max_bytes // (1024 * 1024)} MB upload limit")
    if not content:
        raise HTTPException(status_code=422, detail=f"{label} is empty")
    return content


def _validate_glb(content: bytes) -> None:
    if len(content) < 12 or content[:4] != b"glTF":
        raise HTTPException(status_code=422, detail="File is not a GLB model")
    version, declared_size = struct.unpack("<II", content[4:12])
    if version != 2 or declared_size != len(content):
        raise HTTPException(status_code=422, detail="GLB header does not match the uploaded file")


def _provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ProviderConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ProviderError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, (CalibrationError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Creator module failed")


@router.post("/brief/prepare")
async def prepare_brief_module(
    payload: BriefModuleRequest,
    request: Request,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> dict[str, object]:
    """Expand one brief and return prompts in the caller's source language."""
    settings = controller_for(request).settings
    language = response_language(payload.message, payload.current_brief)
    try:
        result = await build_preparation_graph(DeepSeekBriefEnricher(settings)).ainvoke(
            prepare_graph_input(payload.message, payload.current_brief, payload.has_reference_image)
        )
        brief = result["brief"]
        brief_payload = brief.model_dump(mode="json", exclude_none=True)
        if language == "zh":
            for field in ("subject", "style", "product_type", "details"):
                localized = brief_payload.pop(f"{field}_zh", None)
                if localized:
                    brief_payload[field] = localized
        else:
            for field in ("subject_zh", "style_zh", "product_type_zh", "details_zh"):
                brief_payload.pop(field, None)
        package = result.get("prompt_package")
        return {
            "language": language,
            "brief": brief_payload,
            "questions": [{"field": item.field, "prompt": item.prompt, "options": item.options} for item in result["questions"]],
            "image_prompt_ready": package is not None,
            "prompts": package.model_dump(mode="json") if package is not None else None,
            "presentation": result.get("presentation_zh" if language == "zh" else "presentation_en"),
        }
    except Exception as exc:
        raise _provider_error(exc) from exc


@router.post("/image2/generate")
async def generate_image_module(
    request: Request,
    background_tasks: BackgroundTasks,
    prompt: str = Form(..., min_length=1, max_length=8000),
    reference_image: UploadFile | None = File(default=None),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> FileResponse:
    """Return one normalized 1:1 Image2 style image as a file response."""
    controller = controller_for(request)
    operation_id = _module_id()
    store = ArtifactStore(controller.settings)
    try:
        reference_path = None
        if reference_image is not None:
            content = await _read_upload(reference_image, controller.settings.max_upload_bytes, "Reference image")
            reference_path = store.save_reference(
                operation_id,
                reference_image.filename or "reference-image",
                content,
                reference_image.content_type,
            )
        image = await OpenAICompatibleImageGenerator(controller.settings).generate_one(prompt, reference_path)
        path = store.save_generated_image(operation_id, 0, image.content, image.media_type)
        headers = {"X-BCA-Image-Shape": "1:1"}
        if image.revised_prompt:
            headers["X-BCA-Image-Revised"] = "true"
        return _file_response(
            path,
            media_type="image/png",
            filename="style-image.png",
            store=store,
            operation_id=operation_id,
            background_tasks=background_tasks,
            headers=headers,
        )
    except Exception as exc:
        _cleanup_module(store, operation_id)
        raise _provider_error(exc) from exc


@router.post("/model/generate")
async def generate_model_module(
    request: Request,
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> FileResponse:
    """Turn one input image into a GLB and return the final model file."""
    controller = controller_for(request)
    operation_id = _module_id()
    store = ArtifactStore(controller.settings)
    try:
        content = await _read_upload(image, controller.settings.max_upload_bytes, "Input image")
        image_path = store.save_reference(operation_id, image.filename or "input-image", content, image.content_type)
        generated = await TencentHunyuan3DGenerator(controller.settings).generate(image_path)
        model_path = await store.download_model(operation_id, generated.glb_url)
        return _file_response(
            model_path,
            media_type="model/gltf-binary",
            filename="model.glb",
            store=store,
            operation_id=operation_id,
            background_tasks=background_tasks,
        )
    except Exception as exc:
        _cleanup_module(store, operation_id)
        raise _provider_error(exc) from exc


@router.post("/print/multicolor")
async def generate_multicolor_module(
    request: Request,
    background_tasks: BackgroundTasks,
    model: UploadFile | None = File(default=None),
    max_colors: int = Form(..., ge=1, le=8),
    meshy_result_url: str | None = Form(default=None),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> FileResponse:
    """Convert one GLB into a multi-color 3MF without a Creator workflow session.

    Supplying a prior Meshy result URL retries only the download and avoids another
    paid Meshy submission.
    """
    controller = controller_for(request)
    operation_id = _module_id()
    store = ArtifactStore(controller.settings)
    workdir = _module_directory(request)
    try:
        meshy_settings = controller.settings.model_copy(update={"meshy_model_input_mode": "data_uri"})
        provider = MeshyPrintProvider(meshy_settings)
        if meshy_result_url:
            # A result URL is a complete retry input: skip the upload and every
            # paid Meshy request, then validate and download only that artifact.
            result_url = provider._model_url({"model_urls": {"3mf": meshy_result_url}}, "3mf")
        else:
            if model is None:
                raise HTTPException(status_code=422, detail="GLB is required when no Meshy result URL is supplied")
            content = await _read_upload(model, _GLB_LIMIT_BYTES, "GLB")
            _validate_glb(content)
            model_path = workdir / "input.glb"
            await asyncio.to_thread(model_path.write_bytes, content)
            # Direct upload modules do not depend on a public callback artifact;
            # Meshy receives the validated input as a data URI.
            result_url = await provider.multi_color(operation_id, model_path, max_colors)
        output_path = await store.download_print_file(operation_id, result_url)
        if await asyncio.to_thread(has_color_snapshot, output_path):
            snapshot_status = "present"
        else:
            snapshot = await asyncio.to_thread(inject_color_snapshot, output_path, output_path=output_path)
            snapshot_status = snapshot.status
        return _file_response(
            output_path,
            media_type="model/3mf",
            filename="multicolor.3mf",
            store=store,
            operation_id=operation_id,
            background_tasks=background_tasks,
            workdir=workdir,
            headers={
                "X-BCA-Meshy-Reused": str(bool(meshy_result_url)).lower(),
                "X-BCA-Color-Snapshot": snapshot_status,
            },
        )
    except Exception as exc:
        _cleanup_module(store, operation_id, workdir)
        raise _provider_error(exc) from exc


@router.post("/print/calibrate")
async def calibrate_print_module(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> FileResponse:
    """Match a model 3MF palette against active inventory and return a calibrated 3MF."""
    if not await _try_acquire_calibration_slot():
        raise HTTPException(
            status_code=429,
            detail="3MF calibration capacity is busy; retry after the active large-package calibration completes",
            headers={"Retry-After": str(_CALIBRATION_RETRY_AFTER_SECONDS)},
        )
    operation_id: str | None = None
    store: ArtifactStore | None = None
    workdir: Path | None = None
    try:
        controller = controller_for(request)
        operation_id = _module_id()
        store = ArtifactStore(controller.settings)
        workdir = _module_directory(request)
        content = await _read_upload(file, _LIMITS.max_input_bytes, "3MF")
        source_path = workdir / "source.3mf"
        output_path = workdir / "calibrated.3mf"
        await asyncio.to_thread(source_path.write_bytes, content)
        inspection = await asyncio.to_thread(inspect_3mf, source_path, _LIMITS)
        inventory_records = await active_creator_inventory_colors()
        inventory = [
            InventoryColor(
                id=item.id,
                name=item.name,
                material=item.material,
                brand=item.brand,
                hex_srgb=item.hex_srgb,
            )
            for item in inventory_records
        ]
        if not inventory:
            raise CalibrationError("Active filament inventory with colors is required for calibration.")
        assignments = await DeepSeekColorMatcher(controller.settings).match_colors(
            [{"source_color": item.source_color, "occurrence_count": item.occurrence_count} for item in inspection.colors],
            [
                {
                    "inventory_id": item.id,
                    "name": item.name,
                    "hex_srgb": item.hex_srgb,
                    "material": item.material,
                    "brand": item.brand,
                    "aliases": list(item.aliases),
                }
                for item in inventory_records
            ],
        )
        result = await asyncio.to_thread(
            calibrate_3mf,
            source_path,
            inventory,
            [ColorAssignment(item.source_color, item.inventory_id, item.rationale) for item in assignments],
            _LIMITS,
            output_path,
        )
        snapshot = await asyncio.to_thread(
            inject_color_snapshot,
            output_path,
            replace_existing=True,
            output_path=output_path,
        )
        return _file_response(
            output_path,
            media_type="model/3mf",
            filename="calibrated.3mf",
            store=store,
            operation_id=operation_id,
            background_tasks=background_tasks,
            workdir=workdir,
            headers={
                "X-BCA-Calibration-Colors": str(len(result.report.mappings)),
                "X-BCA-Calibration-Changes": str(result.report.changed_count),
                "X-BCA-Color-Snapshot": snapshot.status,
            },
        )
    except Exception as exc:
        if store is not None and operation_id is not None:
            _cleanup_module(store, operation_id, workdir)
        raise _provider_error(exc) from exc
    finally:
        _CALIBRATION_SLOT.release()


@router.post("/print/analyze")
async def analyze_print_module(
    request: Request,
    model: UploadFile = File(...),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
) -> dict[str, object]:
    """Analyze one GLB and return Meshy plus DeepSeek observations as JSON."""
    controller = controller_for(request)
    operation_id = _module_id()
    store = ArtifactStore(controller.settings)
    workdir = _module_directory(request)
    try:
        content = await _read_upload(model, _GLB_LIMIT_BYTES, "GLB")
        _validate_glb(content)
        model_path = workdir / "input.glb"
        await asyncio.to_thread(model_path.write_bytes, content)
        meshy_settings = controller.settings.model_copy(update={"meshy_model_input_mode": "data_uri"})
        report = await MeshyPrintProvider(meshy_settings).analyze(operation_id, model_path)
        assessment = await DeepSeekPrintAssessor(controller.settings).assess_printability(report)
        return {"report": report.model_dump(mode="json"), "assessment": assessment.model_dump(mode="json")}
    except Exception as exc:
        raise _provider_error(exc) from exc
    finally:
        _cleanup_module(store, operation_id, workdir)
