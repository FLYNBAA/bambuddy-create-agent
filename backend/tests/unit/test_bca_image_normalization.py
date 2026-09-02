from __future__ import annotations

import io
import uuid

from PIL import Image

from backend.app.three_d_agent.config import Settings
from backend.app.three_d_agent.storage import ArtifactStore


def _png(size: tuple[int, int]) -> bytes:
    image = Image.new("RGB", size, "#123456")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_generated_image_is_letterboxed_to_a_square_png(tmp_path) -> None:
    store = ArtifactStore(Settings(data_dir=tmp_path))

    path = store.save_generated_image(str(uuid.uuid4()), 0, _png((1600, 800)))

    with Image.open(path) as image:
        assert image.size == (1600, 1600)
        assert image.getpixel((0, 0)) == (255, 255, 255)
        assert image.getpixel((800, 800)) == (18, 52, 86)
