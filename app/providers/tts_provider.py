from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, output_dir: Path, voiceover_text: str) -> Path:
        raise NotImplementedError


class MockTTSProvider(TTSProvider):
    def synthesize(self, output_dir: Path, voiceover_text: str) -> Path:
        audio_dir = output_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        voice_file = audio_dir / "voice.txt"
        voice_file.write_text(f"MOCK AUDIO\n{voiceover_text}\n", encoding="utf-8")
        return voice_file


class LocalTTSProvider(TTSProvider):
    """Local offline TTS via pyttsx3, outputs wav for Windows compatibility."""

    def __init__(self, voice_name: str | None = None, rate: int = 180) -> None:
        self.voice_name = voice_name
        self.rate = rate

    def synthesize(self, output_dir: Path, voiceover_text: str) -> Path:
        try:
            import pyttsx3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("LocalTTSProvider requires pyttsx3. Install with: pip install pyttsx3") from exc

        audio_dir = output_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        voice_file = audio_dir / "voice.wav"

        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        if self.voice_name:
            for voice in engine.getProperty("voices"):
                if self.voice_name in (voice.id, getattr(voice, "name", "")):
                    engine.setProperty("voice", voice.id)
                    break

        engine.save_to_file(voiceover_text, str(voice_file))
        engine.runAndWait()
        return voice_file
