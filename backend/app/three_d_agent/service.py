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
    ImageGenerator,
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


class ThreeDPrintAgent:
    """Coordinates preparation, four-image approval, and selected-image 3D work."""

    def __init__(
        self,
        repository: _SessionRepository,
        artifact_store: _ArtifactStore,
        brief_enricher: BriefEnricher,
        image_generator: ImageGenerator,
        three_d_generator: ThreeDGenerator,
        print_provider: PrintProvider | None = None,
        color_matcher: FilamentColorMatcher | None = None,
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

    def record_conversation_message(self, session_id: str, role: str, content: str) -> SessionSnapshot:
        """Persist bounded global chat history alongside the workflow snapshot."""
        from .conversation import append_message

        snapshot = self._repository.get(session_id)
        append_message(snapshot, role, content)
        return self._detach(self._repository.save(snapshot))

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
        """Reset a safe workflow boundary without bypassing a paid confirmation."""
        if stage not in {"brief", "images", "model", "print"}:
            raise ValueError("Restart stage must be brief, images, model, or print.")
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status in {SessionStatus.GENERATING_IMAGES, SessionStatus.GENERATING_3D}:
                raise ValueError("Wait for the active generation to finish or fail before restarting.")
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
                snapshot.status = (
                    SessionStatus.AWAITING_IMAGE_CONFIRMATION if snapshot.brief.is_complete else SessionStatus.NEEDS_INPUT
                )
            elif stage == "model":
                if len(snapshot.generated_image_paths) != 4:
                    raise ValueError("Four images are required before restarting the 3D model stage.")
                snapshot.model_path = None
                self._reset_after_model_change(session_id, snapshot)
                snapshot.status = SessionStatus.AWAITING_3D_CONFIRMATION
            else:
                if snapshot.status is not SessionStatus.COMPLETED:
                    raise ValueError("A completed model is required before restarting print processing.")
                self._reset_print_subworkflow(snapshot)
            snapshot.error = None
            self._record(snapshot, "restart", f"已从 {stage} 阶段重新开始；后续付费阶段仍需要明确确认。")
            return self._detach(self._repository.save(snapshot))
    async def prepare(
        self,
        session_id: str,
        message: str,
        reference_image_name: str | None = None,
        reference_image_content: bytes | None = None,
        reference_image_media_type: str | None = None,
    ) -> SessionSnapshot:
        """Enrich a brief and wait for the first explicit paid-generation gate."""
        if not message.strip() and reference_image_content is None:
            raise ValueError("A preparation message or reference image is required.")
        if reference_image_name and reference_image_content is None:
            raise ValueError("Reference image content is required when a name is provided.")
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status not in {
                SessionStatus.NEEDS_INPUT,
                SessionStatus.AWAITING_IMAGE_CONFIRMATION,
            }:
                raise ValueError(f"Cannot prepare a session in status '{snapshot.status}'.")

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
                snapshot.status = SessionStatus.AWAITING_IMAGE_CONFIRMATION
                self._record(snapshot, "preparation", "创作信息已完整，等待确认四张效果图生成。")
            else:
                snapshot.status = SessionStatus.NEEDS_INPUT
                self._record(snapshot, "preparation", "仍需补充创作信息。")
            return self._detach(self._repository.save(snapshot))

    async def queue_image_generation(self, session_id: str) -> SessionSnapshot:
        """Open the first paid gate; only this method permits image provider work."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if (
                snapshot.status is not SessionStatus.AWAITING_IMAGE_CONFIRMATION
                or not snapshot.brief.is_complete
                or not snapshot.image_prompt
            ):
                raise ValueError("A complete prepared brief must be explicitly confirmed first.")
            snapshot.status = SessionStatus.QUEUED_IMAGE
            snapshot.error = None
            self._record(snapshot, "image_confirmation", "已确认付费生成四张效果图，任务进入队列。")
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
                    SessionStatus.AWAITING_3D_CONFIRMATION,
                    SessionStatus.QUEUED_3D,
                    SessionStatus.GENERATING_3D,
                    SessionStatus.COMPLETED,
                }
            ):
                return self._detach(snapshot)
            if snapshot.status is not SessionStatus.QUEUED_IMAGE:
                raise ValueError("Image generation can only run after explicit image confirmation.")
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

    async def select_image(self, session_id: str, image_index: int) -> SessionSnapshot:
        """Choose or re-choose a persisted candidate before the second gate queues."""
        if image_index not in range(4):
            raise ValueError("Image index must be between 0 and 3.")
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status not in {
                SessionStatus.AWAITING_IMAGE_SELECTION,
                SessionStatus.AWAITING_3D_CONFIRMATION,
            }:
                raise ValueError("An image can only be selected before 3D generation is queued.")
            if len(snapshot.generated_image_paths) != 4:
                raise ValueError("Exactly four persisted images are required before selection.")
            snapshot.selected_image_index = image_index
            snapshot.status = SessionStatus.AWAITING_3D_CONFIRMATION
            self._record(snapshot, "image_selection", f"已选择第 {image_index + 1} 张效果图，等待确认 3D 生成。")
            return self._detach(self._repository.save(snapshot))

    async def queue_3d_generation(self, session_id: str) -> SessionSnapshot:
        """Open the second paid gate for the selected and persisted image only."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if (
                snapshot.status is not SessionStatus.AWAITING_3D_CONFIRMATION
                or snapshot.selected_image_index is None
                or len(snapshot.generated_image_paths) != 4
            ):
                raise ValueError("A selected image must be explicitly confirmed before 3D generation.")
            snapshot.status = SessionStatus.QUEUED_3D
            snapshot.error = None
            self._record(snapshot, "model_confirmation", "已确认付费 3D 生成，任务进入队列。")
            return self._detach(self._repository.save(snapshot))

    async def run_3d_generation(self, session_id: str) -> SessionSnapshot:
        """Generate the model from only the selected image, once after success."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status is SessionStatus.COMPLETED:
                return self._detach(snapshot)
            if snapshot.status is not SessionStatus.QUEUED_3D:
                raise ValueError("3D generation can only run after explicit 3D confirmation.")
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
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status is not SessionStatus.COMPLETED or not snapshot.model_path:
                raise ValueError("A completed GLB model is required before print analysis.")
            if snapshot.print_analysis.status not in {
                SubworkflowStatus.NOT_STARTED,
                SubworkflowStatus.FAILED,
            }:
                raise ValueError("Print analysis is already queued or complete.")
            snapshot.print_analysis.status = SubworkflowStatus.QUEUED
            snapshot.print_analysis.error = None
            self._record_sub(snapshot, "print_analysis", "queued", "已提交免费可打印性分析。")
            return self._detach(self._repository.save(snapshot))

    async def run_print_analysis(self, session_id: str) -> SessionSnapshot:
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.print_analysis.status is SubworkflowStatus.SUCCEEDED:
                return self._detach(snapshot)
            if snapshot.print_analysis.status is not SubworkflowStatus.QUEUED or not snapshot.model_path:
                raise ValueError("Print analysis can only run after it is queued.")
            snapshot.print_analysis.status = SubworkflowStatus.RUNNING
            self._record_sub(snapshot, "print_analysis", "running", "正在分析 GLB 的可打印性。")
            self._repository.save(snapshot)
            try:
                report = await self._print_provider_for_use().analyze(session_id, Path(snapshot.model_path))
                snapshot = self._repository.get(session_id)
                snapshot.print_analysis.status = SubworkflowStatus.SUCCEEDED
                snapshot.print_analysis.report = report
                snapshot.print_analysis.error = None
                self._record_sub(snapshot, "print_analysis", "succeeded", "可打印性分析已完成。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "print_analysis", "服务停止，可打印性分析已中断。")
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "print_analysis", f"{type(exc).__name__}: {exc}")
            return self._detach(self._repository.save(snapshot))

    async def queue_model_repair(self, session_id: str) -> SessionSnapshot:
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            report = snapshot.print_analysis.report
            if (
                snapshot.status is not SessionStatus.COMPLETED
                or not snapshot.model_path
                or snapshot.print_analysis.status is not SubworkflowStatus.SUCCEEDED
                or report is None
                or report.status == "healthy"
            ):
                raise ValueError("Repair requires a completed analysis that found printability issues.")
            if snapshot.model_repair.status not in {
                SubworkflowStatus.NOT_STARTED,
                SubworkflowStatus.FAILED,
            }:
                raise ValueError("Model repair is already queued or complete.")
            snapshot.model_repair.status = SubworkflowStatus.QUEUED
            snapshot.model_repair.error = None
            self._record_sub(snapshot, "model_repair", "queued", "已确认付费拓扑修复任务。")
            return self._detach(self._repository.save(snapshot))

    async def run_model_repair(self, session_id: str) -> SessionSnapshot:
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.model_repair.status is SubworkflowStatus.SUCCEEDED:
                return self._detach(snapshot)
            if snapshot.model_repair.status is not SubworkflowStatus.QUEUED or not snapshot.model_path:
                raise ValueError("Model repair can only run after it is queued.")
            snapshot.model_repair.status = SubworkflowStatus.RUNNING
            self._record_sub(snapshot, "model_repair", "running", "正在修复 GLB 拓扑；修复件不保留纹理。")
            self._repository.save(snapshot)
            try:
                provider = self._print_provider_for_use()
                original_model = Path(snapshot.model_path)
                repaired_path = (
                    Path(snapshot.repaired_model_path)
                    if snapshot.repaired_model_path
                    else None
                )
                if repaired_path is None or not repaired_path.is_file():
                    repaired_url = self._repository.get_pending_artifact_url(session_id, "repair")
                    if repaired_url is None:
                        repaired_url = await provider.repair(session_id, original_model)
                        self._repository.save_pending_artifact_url(
                            session_id, "repair", repaired_url
                        )
                    repaired_path = await self._artifact_store.download_repaired_model(
                        session_id, repaired_url
                    )
                    snapshot = self._repository.get(session_id)
                    snapshot.repaired_model_path = str(repaired_path)
                    self._repository.clear_pending_artifact_url(session_id, "repair")
                    self._record_sub(
                        snapshot,
                        "model_repair",
                        "running",
                        "修复 GLB 已保存，正在执行免费复检。",
                    )
                    self._repository.save(snapshot)
                repaired_report = await provider.analyze(
                    session_id, repaired_path, public_route="repaired-model"
                )
                snapshot = self._repository.get(session_id)
                snapshot.model_repair.status = SubworkflowStatus.SUCCEEDED
                snapshot.model_repair.report = repaired_report
                snapshot.model_repair.textures_preserved = False
                snapshot.model_repair.error = None
                self._record_sub(snapshot, "model_repair", "succeeded", "拓扑修复和复检已完成；修复件不保留纹理。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "model_repair", "服务停止，拓扑修复任务已中断。")
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "model_repair", f"{type(exc).__name__}: {exc}")
            return self._detach(self._repository.save(snapshot))

    async def queue_print_file(
        self,
        session_id: str,
        max_colors: int = 4,
        acknowledge_issues: bool = False,
    ) -> SessionSnapshot:
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            report = snapshot.print_analysis.report
            if (
                snapshot.status is not SessionStatus.COMPLETED
                or not snapshot.model_path
                or snapshot.print_analysis.status is not SubworkflowStatus.SUCCEEDED
                or report is None
            ):
                raise ValueError("A completed printability analysis is required before 3MF generation.")
            if not 1 <= max_colors <= 16:
                raise ValueError("Invalid multi-color print settings.")
            if report.status != "healthy" and not acknowledge_issues:
                raise ValueError("Printability issues must be explicitly acknowledged before 3MF generation.")
            if snapshot.print_file.status not in {
                SubworkflowStatus.NOT_STARTED,
                SubworkflowStatus.FAILED,
            }:
                raise ValueError("3MF generation is already queued or complete.")
            snapshot.print_file.status = SubworkflowStatus.QUEUED
            snapshot.print_file.max_colors = max_colors
            snapshot.print_file.issues_acknowledged = acknowledge_issues
            snapshot.print_file.error = None
            self._record_sub(snapshot, "print_file", "queued", "已确认付费多色 3MF 生成任务。")
            return self._detach(self._repository.save(snapshot))

    async def run_print_file(self, session_id: str) -> SessionSnapshot:
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.print_file.status is SubworkflowStatus.SUCCEEDED:
                return self._detach(snapshot)
            if (
                snapshot.print_file.status is not SubworkflowStatus.QUEUED
                or not snapshot.model_path
                or snapshot.print_file.max_colors is None
            ):
                raise ValueError("3MF generation can only run after it is queued.")
            snapshot.print_file.status = SubworkflowStatus.RUNNING
            self._record_sub(snapshot, "print_file", "running", "正在以原始含纹理 GLB 生成多色 3MF。")
            self._repository.save(snapshot)
            try:
                file_url = self._repository.get_pending_artifact_url(session_id, "print_file")
                if file_url is None:
                    file_url = await self._print_provider_for_use().multi_color(
                        session_id, Path(snapshot.model_path), snapshot.print_file.max_colors
                    )
                    self._repository.save_pending_artifact_url(session_id, "print_file", file_url)
                file_path = await self._artifact_store.download_print_file(session_id, file_url)
                snapshot = self._repository.get(session_id)
                snapshot.print_file.status = SubworkflowStatus.SUCCEEDED
                snapshot.print_file_path = str(file_path)
                snapshot.print_file.error = None
                self._repository.clear_pending_artifact_url(session_id, "print_file")
                self._record_sub(snapshot, "print_file", "succeeded", "多色 3MF 已保存；始终使用原始含纹理 GLB。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "print_file", "服务停止，多色 3MF 生成已中断。")
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "print_file", f"{type(exc).__name__}: {exc}")
            return self._detach(self._repository.save(snapshot))

    async def generate_geometry_print_file(self, session_id: str) -> SessionSnapshot:
        """Create a safe single-white-material copy of the persisted model 3MF."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.status is not SessionStatus.COMPLETED or not snapshot.print_file_path:
                raise ValueError("A completed persisted 3MF is required before geometry conversion.")
            if snapshot.geometry_status is SubworkflowStatus.RUNNING:
                raise ValueError("Geometry conversion is already running.")
            source_path = Path(snapshot.print_file_path)
            configured_path = getattr(self._artifact_store, "geometry_print_file_path", None)
            output_path = configured_path(session_id) if configured_path is not None else source_path.with_name("print-geometry.3mf")
            snapshot.geometry_status = SubworkflowStatus.RUNNING
            self._record_sub(snapshot, "geometry", "running", "正在生成仅保留几何信息的白色 3MF。")
            self._repository.save(snapshot)
            try:
                await asyncio.to_thread(geometry_only_3mf, source_path, output_path=output_path)
                snapshot = self._repository.get(session_id)
                snapshot.geometry_print_file_path = str(output_path)
                snapshot.geometry_status = SubworkflowStatus.SUCCEEDED
                self._record_sub(snapshot, "geometry", "succeeded", "几何模式 3MF 已保存。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                snapshot.geometry_status = SubworkflowStatus.FAILED
                self._record_sub(snapshot, "geometry", "failed", "服务停止，几何模式转换已中断。")
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                snapshot.geometry_status = SubworkflowStatus.FAILED
                self._record_sub(snapshot, "geometry", "failed", f"{type(exc).__name__}: {exc}")
            return self._detach(self._repository.save(snapshot))

    async def queue_color_calibration(self, session_id: str) -> SessionSnapshot:
        """Queue local/AI calibration after the original 3MF has been persisted."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if (
                snapshot.status is not SessionStatus.COMPLETED
                or snapshot.print_file.status is not SubworkflowStatus.SUCCEEDED
                or not snapshot.print_file_path
            ):
                raise ValueError("A completed persisted 3MF is required before color calibration.")
            if snapshot.color_calibration.status not in {
                SubworkflowStatus.NOT_STARTED,
                SubworkflowStatus.FAILED,
            }:
                raise ValueError("Color calibration is already queued or complete.")
            snapshot.color_calibration.status = SubworkflowStatus.QUEUED
            snapshot.color_calibration.error = None
            self._record_sub(snapshot, "color_calibration", "queued", "已提交本地色彩校准任务。")
            return self._detach(self._repository.save(snapshot))

    async def run_color_calibration(self, session_id: str) -> SessionSnapshot:
        """Map every source 3MF color to active inventory and atomically write a copy."""
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            snapshot = self._repository.get(session_id)
            if snapshot.color_calibration.status is SubworkflowStatus.SUCCEEDED:
                return self._detach(snapshot)
            if (
                snapshot.color_calibration.status is not SubworkflowStatus.QUEUED
                or not snapshot.print_file_path
            ):
                raise ValueError("Color calibration can only run after it is queued.")
            snapshot.color_calibration.status = SubworkflowStatus.RUNNING
            self._record_sub(snapshot, "color_calibration", "running", "正在检查 3MF 颜色并匹配可用耗材。")
            self._repository.save(snapshot)
            try:
                source_path = Path(snapshot.print_file_path)
                inspection = await asyncio.to_thread(inspect_3mf, source_path)
                snapshot = self._repository.get(session_id)
                snapshot.color_calibration.source_colors = [item.source_color for item in inspection.colors]
                self._repository.save(snapshot)
                records = await self._inventory_records_for_use()
                colors = [
                    InventoryColor(
                        id=str(record.id),
                        name=record.name,
                        material=record.material,
                        brand=record.brand,
                        hex_srgb=record.hex_srgb or "",
                    )
                    for record in records
                ]
                if not colors or not inspection.colors:
                    raise ValueError("3MF colors and active inventory are required for calibration.")
                payload = [{"source_color": c.source_color, "occurrence_count": c.occurrence_count} for c in inspection.colors]
                inventory = [{"inventory_id": str(r.id), "name": r.name, "hex_srgb": r.hex_srgb, "material": r.material, "brand": r.brand, "aliases": list(r.aliases)} for r in records]
                raw = await self._color_matcher_for_use().match_colors(payload, inventory)
                assignments = [ColorMatchAssignment.model_validate(item) for item in raw]
                inventory_by_id = {item.id: item for item in colors}
                assignments = [
                    assignment.model_copy(
                        update={
                            "inventory_name": inventory_by_id.get(assignment.inventory_id).name
                            if inventory_by_id.get(assignment.inventory_id) else None,
                            "matched_hex_srgb": inventory_by_id.get(assignment.inventory_id).hex_srgb.upper()
                            if inventory_by_id.get(assignment.inventory_id) else None,
                        }
                    )
                    for assignment in assignments
                ]
                output_path = self._calibrated_print_file_path(session_id, source_path)
                await asyncio.to_thread(calibrate_3mf, source_path, colors, [ColorAssignment(a.source_color, a.inventory_id, a.rationale) for a in assignments], output_path=output_path)
                snapshot = self._repository.get(session_id)
                snapshot.color_calibration.status = SubworkflowStatus.SUCCEEDED
                snapshot.color_calibration.source_colors = [c.source_color for c in inspection.colors]
                snapshot.color_calibration.assignments = assignments
                snapshot.color_calibration.error = None
                snapshot.calibrated_print_file_path = str(output_path)
                self._record_sub(snapshot, "color_calibration", "succeeded", "色彩校准 3MF 已保存；原始文件未修改。")
            except asyncio.CancelledError:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "color_calibration", "服务停止，色彩校准任务已中断。")
                self._repository.save(snapshot)
                raise
            except Exception as exc:
                snapshot = self._repository.get(session_id)
                self._fail_sub(snapshot, "color_calibration", f"{type(exc).__name__}: {exc}")
            return self._detach(self._repository.save(snapshot))


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
