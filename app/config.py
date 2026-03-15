from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ProviderSettings:
    llm_provider: str = "mock"
    image_provider: str = "mock"
    tts_provider: str = "mock"
    video_provider: str = "mock"
    llm_base_url: str = "http://127.0.0.1:8000/v1"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_api_key: str | None = None


@dataclass(slots=True)
class AppConfig:
    project_root: Path
    output_root: Path
    assets_root: Path
    encoding: str = "utf-8"
    providers: ProviderSettings = field(default_factory=ProviderSettings)

    @classmethod
    def load(cls, project_root: Path | None = None) -> "AppConfig":
        base = project_root or Path(__file__).resolve().parents[1]
        providers = ProviderSettings(
            llm_provider=os.getenv("LCT_LLM_PROVIDER", "mock"),
            image_provider=os.getenv("LCT_IMAGE_PROVIDER", "mock"),
            tts_provider=os.getenv("LCT_TTS_PROVIDER", "mock"),
            video_provider=os.getenv("LCT_VIDEO_PROVIDER", "mock"),
            llm_base_url=os.getenv("LCT_LLM_BASE_URL", "http://127.0.0.1:8000/v1"),
            llm_model=os.getenv("LCT_LLM_MODEL", "qwen2.5:7b-instruct"),
            llm_api_key=os.getenv("LCT_LLM_API_KEY"),
        )
        return cls(
            project_root=base,
            output_root=base / "output",
            assets_root=base / "assets",
            providers=providers,
        )
