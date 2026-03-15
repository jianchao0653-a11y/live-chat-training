from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class VideoProvider(ABC):
    @abstractmethod
    def compose(self, output_dir: Path) -> Path:
        raise NotImplementedError


class MockVideoProvider(VideoProvider):
    def compose(self, output_dir: Path) -> Path:
        target = output_dir / "final.mock.txt"
        target.write_text(
            "MOCK VIDEO OUTPUT\nUse FFmpeg provider in later versions to produce final.mp4\n",
            encoding="utf-8",
        )
        return target


class FFmpegVideoProvider(VideoProvider):
    """Generate a baseline silent final.mp4 template using local ffmpeg."""

    def __init__(self, duration_seconds: int = 60, size: str = "1080x1920", fps: int = 25) -> None:
        self.duration_seconds = duration_seconds
        self.size = size
        self.fps = fps

    def compose(self, output_dir: Path) -> Path:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("FFmpeg not found in PATH. Please install FFmpeg to enable final.mp4 rendering.")

        target = output_dir / "final.mp4"
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={self.size}:d={self.duration_seconds}:r={self.fps}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo:d={self.duration_seconds}",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(target),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"FFmpeg compose failed: {exc.stderr.strip()}") from exc
        return target
