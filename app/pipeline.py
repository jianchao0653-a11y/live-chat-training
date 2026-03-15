from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from app.config import AppConfig
from app.models import RunResult
from app.providers.image_provider import ImageProvider, MockImageProvider
from app.providers.llm_provider import LLMProvider, MockLLMProvider
from app.providers.tts_provider import TTSProvider, MockTTSProvider
from app.providers.video_provider import VideoProvider, MockVideoProvider
from app.steps.generate_materials import generate_materials
from app.steps.parse_case import parse_case
from app.steps.render_audio import render_audio
from app.steps.render_images import render_images
from app.steps.render_video import render_video


class CasePipeline:
    def __init__(
        self,
        config: AppConfig,
        llm_provider: LLMProvider | None = None,
        image_provider: ImageProvider | None = None,
        tts_provider: TTSProvider | None = None,
        video_provider: VideoProvider | None = None,
    ) -> None:
        self.config = config
        self.llm_provider = llm_provider or MockLLMProvider()
        self.image_provider = image_provider or MockImageProvider()
        self.tts_provider = tts_provider or MockTTSProvider()
        self.video_provider = video_provider or MockVideoProvider()

    def run(self, case_path: Path) -> RunResult:
        case_id = case_path.stem
        output_dir = self.config.output_root / case_id
        output_dir.mkdir(parents=True, exist_ok=True)
        logger = _build_logger(output_dir / "run.log")

        result = RunResult(case_id=case_id, output_dir=output_dir, status="running", started_at=datetime.utcnow())
        logger.info("Pipeline started for case=%s", case_path)

        try:
            analysis = parse_case(case_path, self.llm_provider, encoding=self.config.encoding)
            logger.info("Case parsed: dispute_focus=%s", analysis.dispute_focus)

            materials, base_files = generate_materials(
                analysis=analysis,
                output_dir=output_dir,
                llm_provider=self.llm_provider,
                encoding=self.config.encoding,
            )
            result.generated_files.extend(base_files)
            logger.info("Materials generated: %s", [p.name for p in base_files])

            image_files = render_images(materials, output_dir, self.image_provider)
            audio_file = render_audio(materials, output_dir, self.tts_provider)
            video_file = render_video(output_dir, self.video_provider)

            result.generated_files.extend(image_files)
            result.generated_files.extend([audio_file, video_file, output_dir / "run.log"])
            result.status = "success"
            logger.info("Render completed: images=%d audio=%s video=%s", len(image_files), audio_file.name, video_file.name)
            return result
        except Exception as exc:  # noqa: BLE001
            result.status = "failed"
            result.error_message = str(exc)
            logger.exception("Pipeline failed: %s", exc)
            raise
        finally:
            result.finished_at = datetime.utcnow()
            logger.info("Pipeline finished with status=%s", result.status)
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)


def _build_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger(f"case-pipeline-{log_file}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger
