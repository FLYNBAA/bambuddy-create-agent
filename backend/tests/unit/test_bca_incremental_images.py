from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.three_d_agent.contracts import CreativeBrief, GeneratedImage, SessionSnapshot, SessionStatus
from backend.app.three_d_agent.service import ThreeDPrintAgent


class MemoryRepository:
    def __init__(self, snapshot: SessionSnapshot):
        self.snapshot = snapshot
        self.persisted_counts: list[int] = []

    def create(self, snapshot):
        self.snapshot = snapshot
        return snapshot.model_copy(deep=True)

    def get(self, _session_id):
        return self.snapshot.model_copy(deep=True)

    def save(self, snapshot):
        self.snapshot = snapshot.model_copy(deep=True)
        self.persisted_counts.append(len(snapshot.generated_image_paths))
        return self.snapshot.model_copy(deep=True)

    def delete(self, _session_id):
        raise NotImplementedError

    def list(self):
        return [self.snapshot.model_copy(deep=True)]

    def get_pending_artifact_url(self, *_):
        return None

    def save_pending_artifact_url(self, *_):
        raise NotImplementedError

    def clear_pending_artifact_url(self, *_):
        raise NotImplementedError


class Store:
    def save_generated_image(self, session_id, image_index, content, media_type):
        assert content == bytes([image_index])
        return Path(f"/{session_id}/image-{image_index}.png")


class StreamingImages:
    async def generate(self, _prompt, _reference_image=None, image_ready=None):
        images = []
        for index in range(4):
            image = GeneratedImage(content=bytes([index]))
            images.append(image)
            assert image_ready is not None
            await image_ready(index, image)
        return images


@pytest.mark.asyncio
async def test_images_are_persisted_one_by_one_before_final_selection_state():
    snapshot = SessionSnapshot(
        session_id="session",
        status=SessionStatus.QUEUED_IMAGE,
        brief=CreativeBrief(subject="cat", style="cute", product_type="figure"),
        image_prompt="prompt",
    )
    repository = MemoryRepository(snapshot)
    agent = ThreeDPrintAgent(repository, Store(), object(), StreamingImages(), object())

    result = await agent.run_image_generation("session")

    assert result.status is SessionStatus.AWAITING_IMAGE_SELECTION
    assert len(result.generated_image_paths) == 4
    assert any(repository.persisted_counts[index : index + 4] == [1, 2, 3, 4] for index in range(len(repository.persisted_counts)))
