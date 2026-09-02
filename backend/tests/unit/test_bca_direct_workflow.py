from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.api.routes import creator_modules
from backend.app.api.routes.creator import router
from backend.app.three_d_agent.contracts import (
    ColorCalibrationState,
    CreativeBrief,
    PrintabilityMetrics,
    PrintabilityReport,
    PrintAssessment,
    SessionSnapshot,
    SessionStatus,
    SubworkflowStatus,
)
from backend.app.three_d_agent.service import ThreeDPrintAgent


class Repository:
    def __init__(self, snapshot: SessionSnapshot) -> None:
        self.snapshot = snapshot

    def get(self, _session_id: str) -> SessionSnapshot:
        return self.snapshot.model_copy(deep=True)

    def save(self, snapshot: SessionSnapshot) -> SessionSnapshot:
        self.snapshot = snapshot.model_copy(deep=True)
        return self.get(snapshot.session_id)


@pytest.mark.asyncio
async def test_direct_stage_actions_queue_without_confirmation_states() -> None:
    repository = Repository(
        SessionSnapshot(
            session_id="session",
            status=SessionStatus.READY_FOR_IMAGES,
            brief=CreativeBrief(subject="cat", style="cute", product_type="figure"),
            image_prompt="cat figure",
        )
    )
    agent = ThreeDPrintAgent(repository, object(), object(), object(), object())

    images = await agent.queue_image_generation("session")
    assert images.status is SessionStatus.QUEUED_IMAGE

    repository.snapshot.status = SessionStatus.AWAITING_IMAGE_SELECTION
    repository.snapshot.generated_image_paths = [f"/{index}.png" for index in range(4)]
    model = await agent.queue_3d_generation("session", 2)
    assert model.status is SessionStatus.QUEUED_3D
    assert model.selected_image_index == 2


def test_creator_router_exposes_only_direct_generation_actions() -> None:
    paths = {route.path for route in router.routes}
    assert "/creator/sessions/{session_id}/images/generate" in paths
    assert "/creator/sessions/{session_id}/model/generate" in paths
    assert "/creator/sessions/{session_id}/print/calibrate" in paths
    assert "/creator/sessions/{session_id}/print/analyze" in paths
    assert "/creator/sessions/{session_id}/chat" not in paths
    assert "/creator/sessions/{session_id}/confirm-image" not in paths
    assert "/creator/sessions/{session_id}/confirm-3d" not in paths
    assert "/creator/sessions/{session_id}/print/generate" not in paths



def test_creator_module_router_exposes_independent_capabilities() -> None:
    paths = {route.path for route in creator_modules.router.routes}
    assert paths == {
        "/creator/modules/brief/prepare",
        "/creator/modules/image2/generate",
        "/creator/modules/model/generate",
        "/creator/modules/print/multicolor",
        "/creator/modules/print/calibrate",
        "/creator/modules/print/analyze",
    }


@pytest.mark.asyncio
async def test_large_calibration_slot_rejects_second_request_until_release() -> None:
    assert await creator_modules._try_acquire_calibration_slot()
    try:
        assert not await creator_modules._try_acquire_calibration_slot()
        assert creator_modules._CALIBRATION_RETRY_AFTER_SECONDS == 120
    finally:
        creator_modules._CALIBRATION_SLOT.release()

@pytest.mark.asyncio
async def test_post_calibration_analysis_uses_persisted_glb() -> None:
    snapshot = SessionSnapshot(
        session_id="session",
        status=SessionStatus.COMPLETED,
        model_path="/models/model.glb",
        calibrated_print_file_path="/print/final.3mf",
        color_calibration=ColorCalibrationState(status=SubworkflowStatus.SUCCEEDED, mode="multicolor"),
    )
    repository = Repository(snapshot)

    class PrintProvider:
        analyzed_path = None

        async def analyze(self, _session_id, model_path, **_kwargs):
            self.analyzed_path = model_path
            return PrintabilityReport(
                status="healthy",
                metrics=PrintabilityMetrics(
                    is_watertight=True,
                    volume=1,
                    non_manifold_edges=0,
                    degenerate_faces=0,
                    holes=0,
                ),
            )

    class Assessor:
        async def assess_printability(self, _report):
            return PrintAssessment(score=92, insights=["The mesh is watertight."])

    provider = PrintProvider()
    agent = ThreeDPrintAgent(
        repository,
        object(),
        object(),
        object(),
        object(),
        print_provider=provider,
        print_assessor=Assessor(),
    )

    await agent.queue_print_analysis("session")
    result = await agent.run_print_analysis("session")

    assert provider.analyzed_path == Path("/models/model.glb")
    assert result.print_analysis.status is SubworkflowStatus.SUCCEEDED
    assert result.print_analysis.score == 92
