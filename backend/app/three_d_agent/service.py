"""Session orchestration for the composable 3D printing agent."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .calibration import ColorAssignment, InventoryColor, calibrate_3mf, geometry_only_3mf, inspect_3mf
from .contracts import (
    BriefEnricher,
    ColorMatchAssignment,
    FilamentColorMatcher,
    GeneratedTaskTitle,
    ImageGenerator,
    PrintAssessment,
    PrintProvider,
    SessionSnapshot,
    SessionStatus,
    StageEvent,
    SubworkflowStatus,
    ThreeDGenerator,
)
from .filament_inventory import FilamentInventoryRepository
from .graph import build_preparation_graph


class _SessionRepository(Protocol):
    def create(self, snapshot: SessionSnapshot) -> SessionSnapshot: ...
    def get(self, session_id: str) -> SessionSnapshot: ...
    def save(self, snapshot: SessionSnapshot) -> SessionSnapshot: ...
    def delete(self, session_id: str) -> None: ...
    def list(self) -> list[SessionSnapshot]: ...
    def get_pending_artifact_url(self, session_id: str, operation: str) -> str | None: ...
    def save_pending_artifact_url(self, session_id: str, operation: str, source_url: str) -> None: ...
    def clear_pending_artifact_url(self, session_id: str, operation: str) -> None: ...

class _ArtifactStore(Protocol):
    def save_reference(
        self, session_id: str, filename: str, content: bytes, media_type: str | None = None
    ) -> Path: ...

    def save_generated_image(
        self, session_id: str, image_index: int, content: bytes, media_type: str
    ) -> Path: ...

    async def download_model(self, session_id: str, glb_url: str) -> Path: ...
    async def download_repaired_model(self, session_id: str, glb_url: str) -> Path: ...

    async def download_print_file(self, session_id: str, file_url: str) -> Path: ...
    def delete_session(self, session_id: str) -> None: ...
    def calibrated_print_file_path(self, session_id: str) -> Path: ...



class PrintAssessmentProvider(Protocol):
    async def assess_printability(self, report) -> PrintAssessment: ...


class TaskTitleProvider(Protocol):
    async def generate_task_title(self, brief) -> GeneratedTaskTitle: ...


class ThreeDPrintAgent:
    """Coordinates the direct card-based 3D creation workflow."""

    def __init__(
        self,
        repository: _SessionRepository,
        artifact_store: _ArtifactStore,
        brief_enricher: BriefEnricher,
        image_generator: ImageGenerator,
        three_d_generator: ThreeDGenerator,
        print_provider: PrintProvider | None = None,
        color_matcher: FilamentColorMatcher | None = None,
        print_assessor: PrintAssessmentProvider | None = None,
        task_title_provider: TaskTitleProvider | None = None,
        filament_inventory: FilamentInventoryRepository | None = None,
        inventory_colors: Callable[[], Awaitable[list[object]]] | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._image_generator = image_generator
        self._three_d_generator = three_d_generator
        self._preparation_graph = build_preparation_graph(brief_enricher)
        self._print_provider = print_provider
        self._color_matcher = color_matcher
        self._filament_inventory = filament_inventory
        self._print_assessor = print_assessor
        self._task_title_provider = task_title_provider
        self._inventory_colors = inventory_colors
        self._session_locks: dict[str, asyncio.Lock] = {}

    def recover_interrupted_sessions(self) -> int:
        """Fail orphaned in-memory jobs so persisted sessions never poll forever."""
        recovered = 0
        active_main = {
            SessionStatus.QUEUED_IMAGE,
            SessionStatus.GENERATING_IMAGES,
            SessionStatus.QUEUED_3D,
            SessionStatus.GENERATING_3D,
        }
        for snapshot in self._repository.list():
            changed = False
            if snapshot.status in active_main:
                self._fail(
                    snapshot,
                    "recovery",
                    RuntimeError("服务重启，未完成的主生成任务已终止。"),
                )
                changed = True
            else:
                for stage in ("print_analysis", "model_repair", "print_file", "color_calibration"):
                    state = getattr(snapshot, stage)
                    if state.status in {SubworkflowStatus.QUEUED, SubworkflowStatus.RUNNING}:
                        self._fail_sub(snapshot, stage, "服务重启，未完成的打印子任务已终止，请重试。")
                        changed = True
                if snapshot.geometry_status is SubworkflowStatus.RUNNING:
                    snapshot.geometry_status = SubworkflowStatus.FAILED
                    self._record_sub(snapshot, "geometry", "failed", "服务重启，未完成的几何模式转换已终止，请重试。")
                    changed = True
            if changed:
                self._repository.save(snapshot)
                recovered += 1
        return recovered


    def create_session(self) -> SessionSnapshot:
        snapshot = SessionSnapshot(session_id=str(uuid4()), status=SessionStatus.NEEDS_INPUT)
        self._record(snapshot, "session", "会话已创建。")
        return self._detach(self._repository.create(snapshot))

    def get_session(self, session_id: str) -> SessionSnapshot:
        return self._detach(self._repository.get(session_id))

    def list_sessions(self) -> list[SessionSnapshot]:
        return [self._detach(snapshot) for snapshot in self._repository.list()]
    def delete_session(self, session_id: str) -> None:
        """Permanently remove one session and its locally owned artifacts."""
        lock = self._session_locks.get(session_id)
        if lock and lock.locked():
            raise ValueError("Cannot delete a session while an operation is running.")
        self._repository.delete(session_id)
        self._artifact_store.delete_session(session_id)
        self._session_locks.pop(session_id, None)


    @staticmethod
    def _reset_print_subworkflow(snapshot: SessionSnapshot) -> None:
        snapshot.print_analysis = type(snapshot.print_analysis)()
        snapshot.model_repair = type(snapshot.model_repair)()
        snapshot.print_file = type(snapshot.print_file)()
        snapshot.color_calibration = type(snapshot.color_calibration)()
        snapshot.print_file_path = None
        snapshot.calibrated_print_file_path = None
        snapshot.geometry_print_file_path = None
        snapshot.geometry_status = SubworkflowStatus.NOT_STARTED

    def _reset_after_model_change(self, session_id: str, snapshot: SessionSnapshot) -> None:
        self._reset_print_subworkflow(snapshot)
        snapshot.repaired_model_path = None
        self._repository.clear_pending_artifact_url(session_id, "repair")
        self._repository.clear_pending_artifact_url(session_id, "print_file")

    async def restart_from_stage(self, session_id: str, stage: str) -> SessionSnapshot:
        """Reset a workflow boundary and coherently discard downstream artifacts."""
        if stage not in {"brief", "images", "model", "print"}:
            raise ValueError("Restart stage must be brief, images, model, or print.")
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status in {
                SessionStatus.QUEUED_IMAGE,
                SessionStatus.GENERATING_IMAGES,
                SessionStatus.QUEUED_3D,
                SessionStatus.GENERATING_3D,
            } or any(
                state.status in {SubworkflowStatus.QUEUED, SubworkflowStatus.RUNNING}
                for state in (snapshot.print_analysis, snapshot.print_file, snapshot.color_calibration)
            ):
                raise ValueError("Wait for the active workflow stage to finish or fail before restarting.")
            if stage == "brief":
                snapshot.brief = type(snapshot.brief)()
                snapshot.questions = []
                snapshot.image_prompt = None
                snapshot.generated_image_paths = []
                snapshot.selected_image_index = None
                snapshot.model_path = None
                self._reset_after_model_change(session_id, snapshot)
                snapshot.status = SessionStatus.NEEDS_INPUT
            elif stage == "images":
                snapshot.generated_image_paths = []
                snapshot.selected_image_index = None
                snapshot.model_path = None
                self._reset_after_model_change(session_id, snapshot)
                snapshot.status = SessionStatus.READY_FOR_IMAGES if snapshot.brief.is_complete else SessionStatus.NEEDS_INPUT
            elif stage == "model":
                if len(snapshot.generated_image_paths) != 4:
                    raise ValueError("Four images are required before restarting the 3D model stage.")
                snapshot.model_path = None
                self._reset_after_model_change(session_id, snapshot)
                snapshot.status = SessionStatus.AWAITING_IMAGE_SELECTION
            else:
                if snapshot.status is not SessionStatus.COMPLETED:
                    raise ValueError("A completed model is required before restarting print processing.")
                self._reset_print_subworkflow(snapshot)
            snapshot.error = None
            self._record(snapshot, "restart", f"已从 {stage} 阶段重新开始。")
            return self._detach(self._repository.save(snapshot))
    async def prepare(
        self,
        session_id: str,
        message: str,
        reference_image_name: str | None = None,
        reference_image_content: bytes | None = None,
        reference_image_media_type: str | None = None,
    ) -> SessionSnapshot:
        """Enrich a brief for direct stage generation."""
        if not message.strip() and reference_image_content is None:
            raise ValueError("A preparation message or reference image is required.")
        if reference_image_name and reference_image_content is None:
            raise ValueError("Reference image content is required when a name is provided.")
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            active_subworkflow = any(
                state.status in {SubworkflowStatus.QUEUED, SubworkflowStatus.RUNNING}
                for state in (snapshot.print_analysis, snapshot.print_file, snapshot.color_calibration)
            )
            if snapshot.status in {
                SessionStatus.QUEUED_IMAGE,
                SessionStatus.GENERATING_IMAGES,
                SessionStatus.QUEUED_3D,
                SessionStatus.GENERATING_3D,
            } or active_subworkflow:
                raise ValueError("Wait for the active workflow stage to finish before redoing the creative brief.")
            if snapshot.status not in {SessionStatus.NEEDS_INPUT, SessionStatus.READY_FOR_IMAGES}:
                snapshot.brief = type(snapshot.brief)()
                snapshot.questions = []
                snapshot.image_prompt = None
                snapshot.reference_image_path = None
                snapshot.generated_image_paths = []
                snapshot.selected_image_index = None
                snapshot.model_path = None
                self._reset_after_model_change(session_id, snapshot)
                snapshot.status = SessionStatus.NEEDS_INPUT

            if reference_image_content is not None:
                reference_path = self._artifact_store.save_reference(
                    session_id,
                    reference_image_name or "reference-image",
                    reference_image_content,
                    reference_image_media_type,
                )
                snapshot.reference_image_path = str(reference_path)

            if snapshot.reference_image_path:
                snapshot.brief = snapshot.brief.model_copy(
                    update={
                        "subject": snapshot.brief.subject or "参考图中的主体",
                        "style": snapshot.brief.style or "参考图风格",
                    }
                )

            try:
                result = await self._preparation_graph.ainvoke(
                    {
                        "message": message,
                        "current_brief": snapshot.brief,
                        "has_reference_image": snapshot.reference_image_path is not None,
                    }
                )
            except Exception as exc:
                self._fail(snapshot, "preparation", exc)
                return self._detach(self._repository.save(snapshot))

            snapshot.brief = result["brief"]
            snapshot.questions = result["questions"]
            snapshot.image_prompt = result["image_prompt"]
            snapshot.error = None
            if snapshot.brief.is_complete:
                snapshot.status = SessionStatus.READY_FOR_IMAGES
                self._record(snapshot, "preparation", "创作信息已完整，可以生成四张效果图。")
            else:
                snapshot.status = SessionStatus.NEEDS_INPUT
                self._record(snapshot, "preparation", "仍需补充创作信息。")
            return self._detach(self._repository.save(snapshot))

    async def queue_image_generation(self, session_id: str) -> SessionSnapshot:
        """Queue image generation, resetting every downstream stage on redo."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status in {
                SessionStatus.QUEUED_IMAGE,
                SessionStatus.GENERATING_IMAGES,
                SessionStatus.QUEUED_3D,
                SessionStatus.GENERATING_3D,
            } or any(
                state.status in {SubworkflowStatus.QUEUED, SubworkflowStatus.RUNNING}
                for state in (snapshot.print_analysis, snapshot.print_file, snapshot.color_calibration)
            ):
                raise ValueError("Wait for the active workflow stage to finish before regenerating style images.")
            if not snapshot.brief.is_complete or not snapshot.image_prompt:
                raise ValueError("A complete prepared brief is required before image generation.")
            if snapshot.status is not SessionStatus.READY_FOR_IMAGES:
                snapshot.generated_image_paths = []
                snapshot.selected_image_index = None
                snapshot.model_path = None
                self._reset_after_model_change(session_id, snapshot)
            snapshot.status = SessionStatus.QUEUED_IMAGE
            snapshot.error = None
            self._record(snapshot, "images", "效果图生成任务已进入队列。")
            return self._detach(self._repository.save(snapshot))

    async def run_image_generation(self, session_id: str) -> SessionSnapshot:
        """Generate and persist exactly four images, once per successful queued job."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if (
                len(snapshot.generated_image_paths) == 4
                and snapshot.status
                in {
                    SessionStatus.AWAITING_IMAGE_SELECTION,
                    SessionStatus.QUEUED_3D,
                    SessionStatus.GENERATING_3D,
                    SessionStatus.COMPLETED,
                }
            ):
                return self._detach(snapshot)
            if snapshot.status is not SessionStatus.QUEUED_IMAGE:
                raise ValueError("Image generation can only run after it is queued.")
            try:
                snapshot.status = SessionStatus.GENERATING_IMAGES
                self._record(snapshot, "image", "正在生成四张适配彩色 3D 打印的效果图。")
                snapshot = self._repository.save(snapshot)
                async def image_ready(index: int, image) -> None:
                    current = self._repository.get(session_id)
                    if len(current.generated_image_paths) != index:
                        raise ValueError("Image provider returned concepts out of order.")
                    path = self._artifact_store.save_generated_image(
                        session_id, index, image.content, image.media_type
                    )
                    current.generated_image_paths.append(str(path))
                    self._record(current, "image", f"第 {index + 1} 张效果图已保存。")
                    self._repository.save(current)

                images = await self._image_generator.generate(
                    snapshot.image_prompt or "",
                    Path(snapshot.reference_image_path) if snapshot.reference_image_path else None,
                    image_ready=image_ready,
                )
                if len(images) != 4:
                    raise ValueError("Image provider must return exactly four images.")
                snapshot = self._repository.get(session_id)
                if not snapshot.generated_image_paths:
                    paths = [
                        self._artifact_store.save_generated_image(
                            session_id, index, image.content, image.media_type
                        )
                        for index, image in enumerate(images)
                    ]
                    snapshot.generated_image_paths = [str(path) for path in paths]
                if len(snapshot.generated_image_paths) != 4:
                    raise ValueError("Exactly four persisted images are required before selection.")
                snapshot.selected_image_index = None
                snapshot.status = SessionStatus.AWAITING_IMAGE_SELECTION
                snapshot.error = None
                self._record(snapshot, "image", "四张效果图已保存，请选择一张继续生成 3D 模型。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                self._fail(snapshot, "image", RuntimeError("服务停止，效果图生成任务已中断。"))
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                self._fail(snapshot, "image", exc)
            return self._detach(self._repository.save(snapshot))

    async def queue_3d_generation(self, session_id: str, image_index: int) -> SessionSnapshot:
        """Select one persisted style image and queue 3D generation or redo."""
        if image_index not in range(4):
            raise ValueError("Image index must be between 0 and 3.")
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status in {
                SessionStatus.QUEUED_IMAGE,
                SessionStatus.GENERATING_IMAGES,
                SessionStatus.QUEUED_3D,
                SessionStatus.GENERATING_3D,
            } or any(
                state.status in {SubworkflowStatus.QUEUED, SubworkflowStatus.RUNNING}
                for state in (snapshot.print_analysis, snapshot.print_file, snapshot.color_calibration)
            ):
                raise ValueError("Wait for the active workflow stage to finish before regenerating the 3D concept.")
            if len(snapshot.generated_image_paths) != 4:
                raise ValueError("Exactly four generated images are required before 3D generation.")
            if snapshot.model_path or snapshot.status is not SessionStatus.AWAITING_IMAGE_SELECTION:
                snapshot.model_path = None
                self._reset_after_model_change(session_id, snapshot)
            snapshot.selected_image_index = image_index
            snapshot.status = SessionStatus.QUEUED_3D
            snapshot.error = None
            self._record(snapshot, "model", f"第 {image_index + 1} 张效果图的 3D 生成任务已进入队列。")
            return self._detach(self._repository.save(snapshot))

    async def run_3d_generation(self, session_id: str) -> SessionSnapshot:
        """Generate the model from only the selected image, once after success."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status is SessionStatus.COMPLETED:
                return self._detach(snapshot)
            if snapshot.status is not SessionStatus.QUEUED_3D:
                raise ValueError("3D generation can only run after it is queued.")
            if snapshot.selected_image_index is None or len(snapshot.generated_image_paths) != 4:
                raise ValueError("The selected image is unavailable.")
            image_path = Path(snapshot.generated_image_paths[snapshot.selected_image_index])
            try:
                snapshot.status = SessionStatus.GENERATING_3D
                self._record(snapshot, "model", "正在根据选中的效果图生成 GLB 模型。")
                snapshot = self._repository.save(snapshot)
                model = await self._three_d_generator.generate(
                    image_path, self._progress_callback(session_id)
                )
                snapshot = self._repository.get(session_id)
                snapshot.provider_job_id = model.job_id
                snapshot.model_preview_url = model.preview_url
                snapshot = self._repository.save(snapshot)
                snapshot.model_path = str(
                    await self._artifact_store.download_model(session_id, model.glb_url)
                )
                snapshot.status = SessionStatus.COMPLETED
                snapshot.error = None
                self._record(snapshot, "completed", "选中效果图对应的 GLB 模型已保存。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                self._fail(snapshot, "model", RuntimeError("服务停止，3D 生成任务已中断。"))
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                self._fail(snapshot, "model", exc)
            return self._detach(self._repository.save(snapshot))

    async def queue_print_analysis(self, session_id: str) -> SessionSnapshot:
        """Queue or redo Meshy GLB analysis after final calibration."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.color_calibration.status is not SubworkflowStatus.SUCCEEDED or not snapshot.calibrated_print_file_path:
                raise ValueError("Final calibration must complete before print analysis.")
            if snapshot.print_analysis.status in {SubworkflowStatus.QUEUED, SubworkflowStatus.RUNNING}:
                raise ValueError("Print analysis is already queued or running.")
            snapshot.print_analysis = type(snapshot.print_analysis)()
            snapshot.print_analysis.status = SubworkflowStatus.QUEUED
            self._record_sub(snapshot, "print_analysis", "queued", "已提交校准后打印分析。")
            return self._detach(self._repository.save(snapshot))

    async def run_print_analysis(self, session_id: str) -> SessionSnapshot:
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.print_analysis.status is SubworkflowStatus.SUCCEEDED:
                return self._detach(snapshot)
            if (
                snapshot.print_analysis.status is not SubworkflowStatus.QUEUED
                or not snapshot.calibrated_print_file_path
                or not snapshot.model_path
            ):
                raise ValueError("Print analysis can only run after final calibration is queued.")
            snapshot.print_analysis.status = SubworkflowStatus.RUNNING
            self._record_sub(snapshot, "print_analysis", "running", "正在执行 Meshy 模型分析和 DeepSeek 评估。")
            self._repository.save(snapshot)
            try:
                report = await self._print_provider_for_use().analyze(
                    session_id,
                    Path(snapshot.model_path),
                    public_route="model",
                    capability_token=snapshot.provider_capability_token,
                )
                assessment = await self._print_assessor_for_use().assess_printability(report)
                snapshot = self._repository.get(session_id)
                snapshot.print_analysis.status = SubworkflowStatus.SUCCEEDED
                snapshot.print_analysis.report = report
                snapshot.print_analysis.score = assessment.score
                snapshot.print_analysis.insights = assessment.insights
                snapshot.print_analysis.error = None
                self._record_sub(snapshot, "print_analysis", "succeeded", "校准后打印分析和质量评估已完成。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "print_analysis", "服务停止，打印分析已中断。")
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "print_analysis", f"{type(exc).__name__}: {exc}")
            return self._detach(self._repository.save(snapshot))

    async def queue_color_calibration(self, session_id: str, *, mode: str, max_colors: int) -> SessionSnapshot:
        """Queue conversion and final calibration, resetting prior downstream results on redo."""
        if mode not in {"white", "multicolor"} or not 1 <= max_colors <= 8:
            raise ValueError("Calibration requires white or multicolor mode and 1–8 colors.")
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status is not SessionStatus.COMPLETED or not snapshot.model_path:
                raise ValueError("A completed GLB model is required before calibration.")
            if any(
                state.status in {SubworkflowStatus.QUEUED, SubworkflowStatus.RUNNING}
                for state in (snapshot.print_analysis, snapshot.print_file, snapshot.color_calibration)
            ):
                raise ValueError("Wait for the active print stage to finish before recalibrating.")
            # Recalibration is an explicit user redo with potentially different
            # mode/color inputs; never reuse a prior Meshy result URL.
            self._repository.clear_pending_artifact_url(session_id, "print_file")
            snapshot.print_analysis = type(snapshot.print_analysis)()
            snapshot.print_file = type(snapshot.print_file)()
            snapshot.color_calibration = type(snapshot.color_calibration)()
            snapshot.print_file_path = None
            snapshot.calibrated_print_file_path = None
            snapshot.print_file.status = SubworkflowStatus.QUEUED
            snapshot.print_file.max_colors = 1 if mode == "white" else max_colors
            snapshot.color_calibration.status = SubworkflowStatus.QUEUED
            snapshot.color_calibration.mode = mode
            snapshot.error = None
            self._record_sub(snapshot, "color_calibration", "queued", "已提交最终 3MF 校准任务。")
            return self._detach(self._repository.save(snapshot))

    async def run_color_calibration(self, session_id: str) -> SessionSnapshot:
        """Create Meshy's 3MF then write only its final calibrated local derivative."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.color_calibration.status is SubworkflowStatus.SUCCEEDED:
                return self._detach(snapshot)
            if snapshot.color_calibration.status is not SubworkflowStatus.QUEUED or not snapshot.model_path or snapshot.print_file.max_colors is None:
                raise ValueError("Color calibration can only run after it is queued.")
            mode = snapshot.color_calibration.mode
            if mode is None:
                raise ValueError("Calibration mode is unavailable.")
            snapshot.color_calibration.status = SubworkflowStatus.RUNNING
            snapshot.print_file.status = SubworkflowStatus.RUNNING
            self._record_sub(snapshot, "color_calibration", "running", "正在生成并校准最终 3MF。")
            self._repository.save(snapshot)
            temporary_path: Path | None = None
            try:
                file_url = self._repository.get_pending_artifact_url(session_id, "print_file")
                if file_url is None:
                    file_url = await self._print_provider_for_use().multi_color(
                        session_id,
                        Path(snapshot.model_path),
                        snapshot.print_file.max_colors,
                        capability_token=snapshot.provider_capability_token,
                    )
                    self._repository.save_pending_artifact_url(session_id, "print_file", file_url)
                temporary_path = await self._artifact_store.download_print_file(session_id, file_url)
                snapshot = self._repository.get(session_id)
                output_path = self._calibrated_print_file_path(session_id, temporary_path)
                if mode == "white":
                    await asyncio.to_thread(geometry_only_3mf, temporary_path, output_path=output_path)
                    assignments: list[ColorMatchAssignment] = []
                    source_colors: list[str] = []
                else:
                    inspection = await asyncio.to_thread(inspect_3mf, temporary_path)
                    records = await self._inventory_records_for_use()
                    colors = [InventoryColor(id=str(record.id), name=record.name, material=record.material, brand=record.brand, hex_srgb=record.hex_srgb or "") for record in records]
                    if not colors or not inspection.colors:
                        raise ValueError("3MF colors and active inventory are required for calibration.")
                    raw = await self._color_matcher_for_use().match_colors(
                        [{"source_color": item.source_color, "occurrence_count": item.occurrence_count} for item in inspection.colors],
                        [{"inventory_id": str(record.id), "name": record.name, "hex_srgb": record.hex_srgb, "material": record.material, "brand": record.brand, "aliases": list(record.aliases)} for record in records],
                    )
                    inventory_by_id = {item.id: item for item in colors}
                    assignments = [ColorMatchAssignment.model_validate(item).model_copy(update={"inventory_name": inventory_by_id.get(str(item.inventory_id)).name if inventory_by_id.get(str(item.inventory_id)) else None, "matched_hex_srgb": inventory_by_id.get(str(item.inventory_id)).hex_srgb.upper() if inventory_by_id.get(str(item.inventory_id)) else None}) for item in raw]
                    await asyncio.to_thread(calibrate_3mf, temporary_path, colors, [ColorAssignment(item.source_color, item.inventory_id, item.rationale) for item in assignments], output_path=output_path)
                    source_colors = [item.source_color for item in inspection.colors]
                snapshot = self._repository.get(session_id)
                snapshot.print_file.status = SubworkflowStatus.SUCCEEDED
                snapshot.print_file_path = None
                snapshot.print_file.error = None
                snapshot.color_calibration.status = SubworkflowStatus.SUCCEEDED
                snapshot.color_calibration.source_colors = source_colors
                snapshot.color_calibration.assignments = assignments
                snapshot.color_calibration.error = None
                snapshot.calibrated_print_file_path = str(output_path)
                self._repository.clear_pending_artifact_url(session_id, "print_file")
                self._record_sub(snapshot, "color_calibration", "succeeded", "最终校准 3MF 已保存。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "color_calibration", "服务停止，色彩校准任务已中断。")
                self._fail_sub(snapshot, "print_file", "服务停止，3MF 生成已中断。")
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "color_calibration", f"{type(exc).__name__}: {exc}")
                self._fail_sub(snapshot, "print_file", f"{type(exc).__name__}: {exc}")
            finally:
                if temporary_path is not None:
                    await asyncio.to_thread(temporary_path.unlink, missing_ok=True)
            return self._detach(self._repository.save(snapshot))


    async def generate_task_title(self, session_id: str) -> str:
        """Generate a concise title from the persisted creative brief."""
        snapshot = self._repository.get(session_id)
        title = await self._task_title_provider_for_use().generate_task_title(snapshot.brief)
        return title.title.strip()

    def _calibrated_print_file_path(self, session_id: str, source_path: Path) -> Path:
        configured_path = getattr(self._artifact_store, "calibrated_print_file_path", None)
        return configured_path(session_id) if configured_path is not None else source_path.with_name("print-calibrated.3mf")

    def _progress_callback(self, session_id: str) -> Callable[[str, str], Awaitable[None]]:
        async def record_progress(stage: str, message: str) -> None:
            snapshot = self._repository.get(session_id)
            if snapshot.status is SessionStatus.GENERATING_3D:
                self._record(snapshot, stage, message)
                self._repository.save(snapshot)

        return record_progress

    async def _inventory_records_for_use(self) -> list[object]:
        if self._inventory_colors is not None:
            return await self._inventory_colors()
        return await asyncio.to_thread(self._active_inventory_for_use().colors_for_numeric_matching)

    def _color_matcher_for_use(self) -> FilamentColorMatcher:
        if self._color_matcher is None:
            raise RuntimeError("DeepSeek color matcher is not configured.")
        return self._color_matcher

    def _print_assessor_for_use(self) -> PrintAssessmentProvider:
        if self._print_assessor is None:
            raise RuntimeError("DeepSeek print assessor is not configured.")
        return self._print_assessor

    def _task_title_provider_for_use(self) -> TaskTitleProvider:
        if self._task_title_provider is None:
            raise RuntimeError("DeepSeek task title generator is not configured.")
        return self._task_title_provider

    def _active_inventory_for_use(self) -> FilamentInventoryRepository:
        if self._filament_inventory is None:
            raise RuntimeError("Filament inventory is not configured.")
        return self._filament_inventory

    def _print_provider_for_use(self) -> PrintProvider:
        if self._print_provider is None:
            raise RuntimeError("Meshy print provider is not configured.")
        return self._print_provider

    @staticmethod
    def _record_sub(snapshot: SessionSnapshot, stage: str, status: str, message: str) -> None:
        snapshot.updated_at = datetime.now(timezone.utc)
        snapshot.events.append(StageEvent(stage=stage, status=status, message=message))

    @staticmethod
    def _fail_sub(snapshot: SessionSnapshot, stage: str, error: str) -> None:
        state = getattr(snapshot, stage)
        state.status = SubworkflowStatus.FAILED
        state.error = error
        ThreeDPrintAgent._record_sub(snapshot, stage, "failed", error)
    @staticmethod
    def _detach(snapshot: SessionSnapshot) -> SessionSnapshot:
        return snapshot.model_copy(deep=True)

    @staticmethod
    def _record(snapshot: SessionSnapshot, stage: str, message: str) -> None:
        snapshot.updated_at = datetime.now(timezone.utc)
        snapshot.events.append(
            StageEvent(stage=stage, status=snapshot.status.value, message=message)
        )

    @staticmethod
    def _fail(snapshot: SessionSnapshot, stage: str, error: Exception) -> None:
        snapshot.status = SessionStatus.FAILED
        snapshot.error = f"{type(error).__name__}: {error}"
        ThreeDPrintAgent._record(snapshot, stage, snapshot.error)
