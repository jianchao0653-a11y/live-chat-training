from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import ProviderSettings
from app.provider_factory import build_llm_provider, build_tts_provider, build_video_provider
from app.providers.llm_provider import MockLLMProvider, OpenAICompatibleLLMProvider
from app.providers.tts_provider import LocalTTSProvider
from app.providers.video_provider import FFmpegVideoProvider


def test_provider_factory_builds_expected_types() -> None:
    mock_settings = ProviderSettings()
    assert isinstance(build_llm_provider(mock_settings), MockLLMProvider)

    real_settings = ProviderSettings(llm_provider="openai_compatible", tts_provider="local", video_provider="ffmpeg")
    assert isinstance(build_llm_provider(real_settings), OpenAICompatibleLLMProvider)
    assert isinstance(build_tts_provider(real_settings), LocalTTSProvider)
    assert isinstance(build_video_provider(real_settings), FFmpegVideoProvider)


def test_ffmpeg_provider_raises_when_binary_missing(tmp_path: Path) -> None:
    provider = FFmpegVideoProvider()
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="FFmpeg not found"):
            provider.compose(tmp_path)
