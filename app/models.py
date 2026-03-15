from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CaseAnalysis:
    """Structured analysis extracted from a case document."""

    case_id: str
    source_path: Path
    relationship_type: str
    risk_type: str
    dispute_focus: str
    judgment_result: str
    one_line_warning: str
    raw_text: str


@dataclass(slots=True)
class ShotItem:
    """Single shot item for a short video."""

    id: str
    duration: float
    scene: str
    prompt: str


@dataclass(slots=True)
class VideoMaterials:
    """Textual materials produced for short video generation."""

    script_60s: str
    voiceover: str
    subtitles_srt: str
    shots: list[ShotItem] = field(default_factory=list)


@dataclass(slots=True)
class RunResult:
    """Pipeline execution result."""

    case_id: str
    output_dir: Path
    status: str
    generated_files: list[Path] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        data["generated_files"] = [str(item) for item in self.generated_files]
        data["source"] = "local-v1"
        return data
