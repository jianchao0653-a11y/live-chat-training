from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.pipeline import CasePipeline


def test_pipeline_generates_core_files(tmp_path: Path) -> None:
    case_file = tmp_path / "case_001.md"
    case_file.write_text(
        """# 案例\n\n- 案情事实\n存在借款往来。\n\n- 争议焦点\n借款是否成立。\n\n- 裁判结果\n法院认定借款关系成立。\n\n- 风险提醒\n交易留痕。\n""",
        encoding="utf-8",
    )

    config = AppConfig(project_root=tmp_path, output_root=tmp_path / "output", assets_root=tmp_path / "assets")
    result = CasePipeline(config=config).run(case_file)

    assert result.status == "success"
    out_dir = tmp_path / "output" / "case_001"
    assert (out_dir / "script_60s.md").exists()
    assert (out_dir / "voiceover.txt").exists()
    assert (out_dir / "subtitles.srt").exists()
    assert (out_dir / "shots.json").exists()
    assert (out_dir / "run.log").exists()
