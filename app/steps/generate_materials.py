from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.models import CaseAnalysis, VideoMaterials
from app.providers.llm_provider import LLMProvider


def generate_materials(
    analysis: CaseAnalysis,
    output_dir: Path,
    llm_provider: LLMProvider,
    encoding: str = "utf-8",
) -> tuple[VideoMaterials, list[Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    materials = llm_provider.generate_materials(analysis)

    script_path = output_dir / "script_60s.md"
    voiceover_path = output_dir / "voiceover.txt"
    subtitles_path = output_dir / "subtitles.srt"
    shots_path = output_dir / "shots.json"

    script_path.write_text(materials.script_60s, encoding=encoding)
    voiceover_path.write_text(materials.voiceover, encoding=encoding)
    subtitles_path.write_text(materials.subtitles_srt, encoding=encoding)

    shots_payload = [asdict(shot) for shot in materials.shots]
    shots_path.write_text(json.dumps(shots_payload, ensure_ascii=False, indent=2), encoding=encoding)

    return materials, [script_path, voiceover_path, subtitles_path, shots_path]
