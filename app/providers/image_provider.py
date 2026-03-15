from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models import ShotItem


class ImageProvider(ABC):
    @abstractmethod
    def render(self, output_dir: Path, shots: list[ShotItem]) -> list[Path]:
        raise NotImplementedError


class MockImageProvider(ImageProvider):
    def render(self, output_dir: Path, shots: list[ShotItem]) -> list[Path]:
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        rendered: list[Path] = []
        for shot in shots:
            target = images_dir / f"{shot.id}.txt"
            target.write_text(
                f"MOCK IMAGE PLACEHOLDER\nscene={shot.scene}\nprompt={shot.prompt}\n",
                encoding="utf-8",
            )
            rendered.append(target)
        return rendered
