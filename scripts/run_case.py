from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import AppConfig
from app.pipeline import CasePipeline
from app.provider_factory import build_image_provider, build_llm_provider, build_tts_provider, build_video_provider
from app.providers.llm_provider import MockLLMProvider
from app.providers.tts_provider import MockTTSProvider
from app.providers.video_provider import MockVideoProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="中文法律案例短视频生产执行器 V1")
    parser.add_argument("--case", required=True, help="案例文件路径，例如 cases/case_001.md")
    parser.add_argument("--llm-provider", choices=["mock", "openai_compatible"], default=None)
    parser.add_argument("--tts-provider", choices=["mock", "local"], default=None)
    parser.add_argument("--video-provider", choices=["mock", "ffmpeg"], default=None)
    parser.add_argument("--fallback-to-mock", action="store_true", default=False, help="真实 provider 失败时回退到 mock")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    case_path = Path(args.case)

    config = AppConfig.load()
    if args.llm_provider:
        config.providers.llm_provider = args.llm_provider
    if args.tts_provider:
        config.providers.tts_provider = args.tts_provider
    if args.video_provider:
        config.providers.video_provider = args.video_provider

    try:
        pipeline = CasePipeline(
            config=config,
            llm_provider=build_llm_provider(config.providers),
            image_provider=build_image_provider(config.providers),
            tts_provider=build_tts_provider(config.providers),
            video_provider=build_video_provider(config.providers),
        )
        result = pipeline.run(case_path)
    except Exception as exc:
        if not args.fallback_to_mock:
            raise
        print(f"[WARN] provider failed: {exc}. fallback to mock providers.")
        pipeline = CasePipeline(
            config=config,
            llm_provider=MockLLMProvider(),
            tts_provider=MockTTSProvider(),
            video_provider=MockVideoProvider(),
        )
        result = pipeline.run(case_path)

    print(f"status={result.status}")
    print(f"output={result.output_dir}")
    for file_path in result.generated_files:
        print(f"- {file_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
