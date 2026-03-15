from __future__ import annotations

from pathlib import Path

from app.providers.video_provider import VideoProvider


def render_video(output_dir: Path, video_provider: VideoProvider) -> Path:
    return video_provider.compose(output_dir=output_dir)
