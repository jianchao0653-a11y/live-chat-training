from __future__ import annotations

from pathlib import Path

from app.models import VideoMaterials
from app.providers.image_provider import ImageProvider


def render_images(materials: VideoMaterials, output_dir: Path, image_provider: ImageProvider) -> list[Path]:
    return image_provider.render(output_dir=output_dir, shots=materials.shots)
