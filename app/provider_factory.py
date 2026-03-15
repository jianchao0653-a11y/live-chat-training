from __future__ import annotations

from app.config import ProviderSettings
from app.providers.image_provider import ImageProvider, MockImageProvider
from app.providers.llm_provider import LLMProvider, MockLLMProvider, OpenAICompatibleLLMProvider
from app.providers.tts_provider import LocalTTSProvider, MockTTSProvider, TTSProvider
from app.providers.video_provider import FFmpegVideoProvider, MockVideoProvider, VideoProvider


def build_llm_provider(settings: ProviderSettings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
        )
    raise ValueError(f"Unsupported llm provider: {settings.llm_provider}")


def build_image_provider(settings: ProviderSettings) -> ImageProvider:
    if settings.image_provider == "mock":
        return MockImageProvider()
    raise ValueError(f"Unsupported image provider: {settings.image_provider}")


def build_tts_provider(settings: ProviderSettings) -> TTSProvider:
    if settings.tts_provider == "mock":
        return MockTTSProvider()
    if settings.tts_provider == "local":
        return LocalTTSProvider()
    raise ValueError(f"Unsupported tts provider: {settings.tts_provider}")


def build_video_provider(settings: ProviderSettings) -> VideoProvider:
    if settings.video_provider == "mock":
        return MockVideoProvider()
    if settings.video_provider == "ffmpeg":
        return FFmpegVideoProvider()
    raise ValueError(f"Unsupported video provider: {settings.video_provider}")
