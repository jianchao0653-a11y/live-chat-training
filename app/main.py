from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.pipeline import CasePipeline


def run_case(case_path: Path) -> None:
    config = AppConfig.load()
    pipeline = CasePipeline(config=config)
    pipeline.run(case_path)
