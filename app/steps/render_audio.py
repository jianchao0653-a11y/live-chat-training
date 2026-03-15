from __future__ import annotations

from pathlib import Path

from app.models import VideoMaterials
from app.providers.tts_provider import TTSProvider


def render_audio(materials: VideoMaterials, output_dir: Path, tts_provider: TTSProvider) -> Path:
    return tts_provider.synthesize(output_dir=output_dir, voiceover_text=materials.voiceover)
