from __future__ import annotations

import asyncio

import pytest

import backend.app.three_d_agent.service as service_module
from backend.app.services.creator_integration import confined_artifact
from backend.app.three_d_agent.contracts import (
    ColorCalibrationState,
    CreativeBrief,
    PrintabilityMetrics,
    PrintabilityReport,
    PrintAnalysisState,
    PrintFileState,
    SessionSnapshot,
    SessionStatus,
    SubworkflowStatus,
)
from backend.app.three_d_agent.service import ThreeDPrintAgent


class MemoryRepository:
    def __init__(self, snapshot: SessionSnapshot):
        self.snapshot = snapshot
        self.pending_artifacts: dict[tuple[str, str], str] = {}

    def create(self, snapshot):
        self.snapshot = snapshot.model_copy(deep=True)
        return self.snapshot.model_copy(deep=True)

    def get(self, _session_id):
        return self.snapshot.model_copy(deep=True)

    def save(self, snapshot):
        self.snapshot = snapshot.model_copy(deep=True)
        return self.snapshot.model_copy(deep=True)

    def delete(self, _session_id):
        raise NotImplementedError

    def list(self):
        return [self.snapshot.model_copy(deep=True)]

    def get_pending_artifact_url(self, session_id, operation):
        return self.pending_artifacts.get((session_id, operation))

    def save_pending_artifact_url(self, session_id, operation, source_url):
        self.pending_artifacts[(session_id, operation)] = source_url

    def clear_pending_artifact_url(self, session_id, operation):
        self.pending_artifacts.pop((session_id, operation), None)


class Store:
    def delete_session(self, _session_id):
        raise NotImplementedError


def completed_snapshot() -> SessionSnapshot:
    report = PrintabilityReport(
        status="warning",
        metrics=PrintabilityMetrics(
            is_watertight=True,
            volume=1,
            non_manifold_edges=0,
            degenerate_faces=0,
            holes=0,
        ),
    )
    return SessionSnapshot(
        session_id="session",
        status=SessionStatus.COMPLETED,
        brief=CreativeBrief(subject="cat", style="cute", product_type="figure"),
        image_prompt="prompt",
        generated_image_paths=[f"/images/{index}.png" for index in range(4)],
        selected_image_index=0,
        model_path="/models/model.glb",
        print_analysis=PrintAnalysisState(status=SubworkflowStatus.SUCCEEDED, report=report),
        print_file=PrintFileState(status=SubworkflowStatus.SUCCEEDED, max_colors=4, issues_acknowledged=True),
        color_calibration=ColorCalibrationState(status=SubworkflowStatus.SUCCEEDED),
        print_file_path="/print/print.3mf",
        calibrated_print_file_path="/print/calibrated.3mf",
        geometry_print_file_path="/print/geometry.3mf",
        geometry_status=SubworkflowStatus.SUCCEEDED,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["brief", "images", "model"])
async def test_upstream_restart_clears_all_downstream_print_artifacts(stage: str) -> None:
    repository = MemoryRepository(completed_snapshot())
    agent = ThreeDPrintAgent(repository, Store(), object(), object(), object())

    result = await agent.restart_from_stage("session", stage)

    assert result.model_path is None
    assert result.print_file_path is None
    assert result.calibrated_print_file_path is None
    assert result.geometry_print_file_path is None
    assert result.print_analysis.status is SubworkflowStatus.NOT_STARTED
    assert result.print_file.status is SubworkflowStatus.NOT_STARTED
    assert result.color_calibration.status is SubworkflowStatus.NOT_STARTED
    assert result.geometry_status is SubworkflowStatus.NOT_STARTED
    if stage in {"brief", "images"}:
        assert result.generated_image_paths == []
    else:
        assert len(result.generated_image_paths) == 4
    for artifact in ("model", "print-file", "calibrated-print-file", "geometry-print-file"):
        with pytest.raises(FileNotFoundError):
            confined_artifact(result, artifact)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["brief", "images", "model"])
async def test_upstream_restart_discards_pending_artifacts_from_the_old_model(stage: str) -> None:
    snapshot = completed_snapshot()
    snapshot.repaired_model_path = "/models/repaired.glb"
    repository = MemoryRepository(snapshot)
    repository.save_pending_artifact_url("session", "repair", "https://meshy.ai/repaired.glb")
    repository.save_pending_artifact_url("session", "print_file", "https://meshy.ai/old-model.3mf")
    agent = ThreeDPrintAgent(repository, Store(), object(), object(), object())

    result = await agent.restart_from_stage("session", stage)

    assert result.repaired_model_path is None
    assert repository.get_pending_artifact_url("session", "repair") is None
    assert repository.get_pending_artifact_url("session", "print_file") is None


@pytest.mark.asyncio
async def test_print_restart_preserves_same_model_pending_artifacts() -> None:
    repository = MemoryRepository(completed_snapshot())
    repository.save_pending_artifact_url("session", "print_file", "https://meshy.ai/same-model.3mf")
    agent = ThreeDPrintAgent(repository, Store(), object(), object(), object())

    await agent.restart_from_stage("session", "print")

    assert repository.get_pending_artifact_url("session", "print_file") == "https://meshy.ai/same-model.3mf"


def test_recovery_marks_interrupted_main_generation_failed() -> None:
    snapshot = completed_snapshot()
    snapshot.status = SessionStatus.GENERATING_3D
    repository = MemoryRepository(snapshot)
    agent = ThreeDPrintAgent(repository, Store(), object(), object(), object())

    assert agent.recover_interrupted_sessions() == 1
    assert repository.snapshot.status is SessionStatus.FAILED
    assert repository.snapshot.error == "RuntimeError: 服务重启，未完成的主生成任务已终止。"



@pytest.mark.asyncio
async def test_geometry_cancellation_persists_failed_status(monkeypatch) -> None:
    repository = MemoryRepository(completed_snapshot())
    agent = ThreeDPrintAgent(repository, Store(), object(), object(), object())

    async def cancelled_to_thread(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(service_module.asyncio, "to_thread", cancelled_to_thread)

    with pytest.raises(asyncio.CancelledError):
        await agent.generate_geometry_print_file("session")

    assert repository.snapshot.geometry_status is SubworkflowStatus.FAILED
    assert repository.snapshot.events[-1].stage == "geometry"
    assert repository.snapshot.events[-1].status == "failed"


def test_recovery_marks_interrupted_geometry_failed() -> None:
    snapshot = completed_snapshot()
    snapshot.geometry_status = SubworkflowStatus.RUNNING
    repository = MemoryRepository(snapshot)
    agent = ThreeDPrintAgent(repository, Store(), object(), object(), object())

    assert agent.recover_interrupted_sessions() == 1
    assert repository.snapshot.geometry_status is SubworkflowStatus.FAILED
    assert repository.snapshot.events[-1].stage == "geometry"
    assert repository.snapshot.events[-1].status == "failed"
