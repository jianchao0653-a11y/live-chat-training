from __future__ import annotations

from pathlib import Path

from app.models import CaseAnalysis
from app.providers.llm_provider import LLMProvider


def parse_case(case_path: Path, llm_provider: LLMProvider, encoding: str = "utf-8") -> CaseAnalysis:
    if not case_path.exists():
        raise FileNotFoundError(f"Case file not found: {case_path}")

    text = case_path.read_text(encoding=encoding)
    case_id = case_path.stem
    return llm_provider.analyze_case(case_id=case_id, source_path=case_path, case_text=text)
