"""Bambuddy integration boundary for the embedded create-agent workflow.

The controller keeps the creative workflow independent from Bambuddy's printer
scheduler. It owns only agent sessions and background stage execution; queue
submission is deliberately a later adapter over Bambuddy's existing library
and queue APIs.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings as bambuddy_settings
from backend.app.core.websocket import ws_manager
from backend.app.models.settings import Settings as StoredSetting
from backend.app.services.creator_inventory import active_creator_inventory_colors
from backend.app.three_d_agent.config import Settings as AgentSettings
from backend.app.three_d_agent.conversation import CreatorConversationPlanner
from backend.app.three_d_agent.factory import create_agent
from backend.app.three_d_agent.service import ThreeDPrintAgent

_CONFIG_KEYS = frozenset(
    {
        "deepseek_api_key",
        "deepseek_base_url",
        "deepseek_model",
        "image_api_key",
        "image_base_url",
        "image_model",
        "image_quality",
        "tencent_secret_id",
        "tencent_secret_key",
        "tencent_region",
        "meshy_api_key",
        "meshy_model_input_mode",
        "app_public_base_url",
    }
)


async def load_creator_config_overrides(db: AsyncSession) -> dict[str, str]:
    rows = await db.execute(select(StoredSetting).where(StoredSetting.key.in_([f"bca_creator_{key}" for key in _CONFIG_KEYS])))
    return {
        row.key.removeprefix("bca_creator_"): row.value
        for row in rows.scalars().all()
        if row.key.removeprefix("bca_creator_") in _CONFIG_KEYS
    }


async def persist_creator_config_overrides(db: AsyncSession, values: dict[str, str]) -> None:
    for key, value in values.items():
        if key not in _CONFIG_KEYS:
            raise ValueError(f"Unsupported creator config key: {key}")
        stored_key = f"bca_creator_{key}"
        row = await db.scalar(select(StoredSetting).where(StoredSetting.key == stored_key))
        if row is None:
            db.add(StoredSetting(key=stored_key, value=value))
        else:
            row.value = value
    await db.commit()

class CreatorSessionResponse(BaseModel):
    """Safe creator snapshot projected for the Bambuddy API."""

    session_id: str
    status: str
    brief: dict[str, Any]
    questions: list[dict[str, Any]]
    image_prompt: str | None
    generated_images: list[str]
    selected_image_index: int | None
    model_download_url: str | None
    print_file_download_url: str | None
    calibrated_print_file_download_url: str | None
    geometry_print_file_download_url: str | None
    print_analysis: dict[str, Any]
    model_repair: dict[str, Any]
    print_file: dict[str, Any]
    conversation: list[dict[str, Any]]
    geometry_status: str
    color_calibration: dict[str, Any]
    events: list[dict[str, Any]]
    error: str | None


class ImageSelectionRequest(BaseModel):
    image_index: int


class CreatorController:
    """Own the embedded create-agent instance and its stage tasks."""

    def __init__(self) -> None:
        data_dir = Path(bambuddy_settings.base_dir) / "bca-agent"
        self.settings = AgentSettings(
            data_dir=data_dir,
            app_public_base_url=os_public_base_url(),
        )
        self.settings.ensure_directories()
        self.agent: ThreeDPrintAgent = create_agent(self.settings, inventory_colors=active_creator_inventory_colors)
        self.planner = CreatorConversationPlanner(self.settings)
        self.tasks: dict[tuple[str, str], asyncio.Task[object]] = {}

    def snapshot(self, session_id: str) -> CreatorSessionResponse:
        snapshot = self.agent.get_session(session_id)
        base = f"/api/v1/creator/sessions/{session_id}"
        return CreatorSessionResponse(
            session_id=snapshot.session_id,
            status=snapshot.status.value,
            brief=snapshot.brief.model_dump(mode="json"),
            questions=[item.model_dump(mode="json") for item in snapshot.questions],
            image_prompt=snapshot.image_prompt,
            generated_images=[f"{base}/images/{index}" for index in range(len(snapshot.generated_image_paths))],
            selected_image_index=snapshot.selected_image_index,
            model_download_url=f"{base}/model" if snapshot.model_path else None,
            print_file_download_url=f"{base}/print-file" if snapshot.print_file_path else None,
            calibrated_print_file_download_url=f"{base}/calibrated-print-file" if snapshot.calibrated_print_file_path else None,
            geometry_print_file_download_url=f"{base}/geometry-print-file" if snapshot.geometry_print_file_path else None,
            print_analysis=snapshot.print_analysis.model_dump(mode="json"),
            model_repair=snapshot.model_repair.model_dump(mode="json"),
            print_file=snapshot.print_file.model_dump(mode="json"),
            conversation=[item.model_dump(mode="json") for item in snapshot.conversation],
            geometry_status=snapshot.geometry_status.value,
            color_calibration=snapshot.color_calibration.model_dump(mode="json"),
            events=[item.model_dump(mode="json") for item in snapshot.events],
            error=snapshot.error,
        )

    def schedule(self, session_id: str, stage: str, operation) -> None:
        key = (session_id, stage)
        current = self.tasks.get(key)
        if current and not current.done():
            operation.close()
            return

        async def run() -> object:
            await self._broadcast(session_id, stage, "running")
            try:
                result = await operation
            except Exception:
                await self._broadcast(session_id, stage, "failed")
                raise
            await self._broadcast(session_id, stage, "updated")
            return result

        task = asyncio.create_task(run(), name=f"bca-{stage}-{session_id}")
        self.tasks[key] = task
        task.add_done_callback(lambda _: self.tasks.pop(key, None))

    async def _broadcast(self, session_id: str, stage: str, event: str) -> None:
        try:
            snapshot = self.agent.get_session(session_id)
            await ws_manager.broadcast_to_user(
                None,
                {
                    "type": "bca_creator_session",
                    "session_id": session_id,
                    "stage": stage,
                    "event": event,
                    "status": snapshot.status.value,
                    "image_count": len(snapshot.generated_image_paths),
                    "geometry_status": snapshot.geometry_status.value,
                    "print_file_status": snapshot.print_file.status.value,
                    "color_calibration_status": snapshot.color_calibration.status.value,
                },
            )
        except Exception:
            # Persisted snapshot polling remains authoritative if websocket delivery fails.
            return

    def reconfigure(self, **overrides: str) -> None:
        """Hot-reload non-secret provider settings when no workflow is active."""
        if any(not task.done() for task in self.tasks.values()):
            raise ValueError("Wait for active creator operations before changing provider configuration.")
        self.settings = AgentSettings(data_dir=self.settings.data_dir, **overrides)
        self.settings.ensure_directories()
        self.agent = create_agent(self.settings, inventory_colors=active_creator_inventory_colors)
        self.planner = CreatorConversationPlanner(self.settings)

    async def shutdown(self) -> None:
        tasks = [task for task in self.tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()

def os_public_base_url() -> str:
    """Use the configured public origin for optional provider callbacks."""
    configured = os.environ.get("BCA_PUBLIC_BASE_URL") or os.environ.get("APP_URL")
    if configured:
        return configured.rstrip("/")
    return "http://127.0.0.1:8000"


def controller_for(request: Request) -> CreatorController:
    controller = getattr(request.app.state, "bca_creator", None)
    if controller is None:
        controller = CreatorController()
        request.app.state.bca_creator = controller
    return controller


def confined_artifact(snapshot, kind: str) -> Path:
    paths = {
        "geometry-print-file": snapshot.geometry_print_file_path,
        "model": snapshot.model_path,
        "print-file": snapshot.print_file_path,
        "calibrated-print-file": snapshot.calibrated_print_file_path,
    }
    stored = paths.get(kind)
    if not stored:
        raise FileNotFoundError(kind)
    candidate = Path(stored).resolve()
    allowed_root = (Path(bambuddy_settings.base_dir) / "bca-agent").resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError as exc:
        raise FileNotFoundError(kind) from exc
    if not candidate.is_file():
        raise FileNotFoundError(kind)
    return candidate


def image_artifact(snapshot, image_index: int) -> Path:
    if image_index < 0 or image_index >= len(snapshot.generated_image_paths):
        raise FileNotFoundError("image")
    candidate = Path(snapshot.generated_image_paths[image_index]).resolve()
    allowed_root = (Path(bambuddy_settings.base_dir) / "bca-agent").resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError as exc:
        raise FileNotFoundError("image") from exc
    if not candidate.is_file():
        raise FileNotFoundError("image")
    return candidate


def file_response(path: Path, media_type: str, filename: str) -> FileResponse:
    return FileResponse(path, media_type=media_type, filename=filename)
