from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from urllib import request

from app.models import CaseAnalysis, ShotItem, VideoMaterials


class LLMProvider(ABC):
    @abstractmethod
    def analyze_case(self, case_id: str, source_path: Path, case_text: str) -> CaseAnalysis:
        raise NotImplementedError

    @abstractmethod
    def generate_materials(self, analysis: CaseAnalysis) -> VideoMaterials:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for local offline V1."""

    def analyze_case(self, case_id: str, source_path: Path, case_text: str) -> CaseAnalysis:
        facts = _extract_section(case_text, "案情事实")
        focus = _extract_section(case_text, "争议焦点")
        result = _extract_section(case_text, "裁判结果")
        warning = _extract_section(case_text, "风险提醒")

        return CaseAnalysis(
            case_id=case_id,
            source_path=source_path,
            relationship_type="民间借贷",
            risk_type="证据留存不足",
            dispute_focus=focus or "是否存在真实借贷合意及款项交付证据",
            judgment_result=result or "法院综合证据后作出裁判",
            one_line_warning=warning or "口头约定风险高，关键交易要留痕。",
            raw_text=facts or case_text,
        )

    def generate_materials(self, analysis: CaseAnalysis) -> VideoMaterials:
        return _build_materials(analysis)


class OpenAICompatibleLLMProvider(LLMProvider):
    """Simple OpenAI-compatible HTTP provider for local/private LLM servers."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout_s: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    def analyze_case(self, case_id: str, source_path: Path, case_text: str) -> CaseAnalysis:
        system_prompt = (
            "你是中文法律案例结构化助手。严格基于输入文本，不虚构事实，不添加额外法律结论。"
            "输出 JSON，包含字段：relationship_type,risk_type,dispute_focus,judgment_result,one_line_warning。"
        )
        user_prompt = f"案例全文如下：\n{case_text}"
        payload = self._chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

        return CaseAnalysis(
            case_id=case_id,
            source_path=source_path,
            relationship_type=payload.get("relationship_type", "未识别关系类型"),
            risk_type=payload.get("risk_type", "未识别风险类型"),
            dispute_focus=payload.get("dispute_focus", "未识别争议焦点"),
            judgment_result=payload.get("judgment_result", "未识别裁判结果"),
            one_line_warning=payload.get("one_line_warning", "交易关键节点应留痕。"),
            raw_text=case_text,
        )

    def generate_materials(self, analysis: CaseAnalysis) -> VideoMaterials:
        system_prompt = (
            "你是中文法律短视频文案助手。风格冷静克制清楚，不鸡汤，不煽情，不虚构，不额外下法律结论。"
            "输出 JSON，包含字段：script_60s,voiceover,shots(数组，每项含id,duration,scene,prompt)。"
        )
        user_prompt = json.dumps(
            {
                "relationship_type": analysis.relationship_type,
                "risk_type": analysis.risk_type,
                "dispute_focus": analysis.dispute_focus,
                "judgment_result": analysis.judgment_result,
                "one_line_warning": analysis.one_line_warning,
            },
            ensure_ascii=False,
        )
        payload = self._chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

        shots_raw = payload.get("shots") or []
        shots = [
            ShotItem(
                id=str(item.get("id", f"shot_{idx:02d}")),
                duration=float(item.get("duration", 15)),
                scene=str(item.get("scene", "场景")),
                prompt=str(item.get("prompt", "法律题材静态画面")),
            )
            for idx, item in enumerate(shots_raw, start=1)
        ]
        if not shots:
            shots = _default_shots(analysis)

        voiceover = str(payload.get("voiceover") or _default_voiceover(analysis))
        return VideoMaterials(
            script_60s=str(payload.get("script_60s") or _default_script(analysis)),
            voiceover=voiceover,
            subtitles_srt=_voiceover_to_srt(voiceover),
            shots=shots,
        )

    def _chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))

        content = raw["choices"][0]["message"]["content"]
        return json.loads(content)


def _build_materials(analysis: CaseAnalysis) -> VideoMaterials:
    voiceover = _default_voiceover(analysis)
    return VideoMaterials(
        script_60s=_default_script(analysis),
        voiceover=voiceover,
        subtitles_srt=_voiceover_to_srt(voiceover),
        shots=_default_shots(analysis),
    )


def _default_script(analysis: CaseAnalysis) -> str:
    return (
        f"【60秒案例速览】\n"
        f"关系类型：{analysis.relationship_type}\n"
        f"风险类型：{analysis.risk_type}\n\n"
        f"争议焦点：{analysis.dispute_focus}\n"
        f"裁判结果：{analysis.judgment_result}\n\n"
        f"风险提醒：{analysis.one_line_warning}\n"
        f"提示：本文仅作案例学习，不构成法律意见。"
    )


def _default_voiceover(analysis: CaseAnalysis) -> str:
    return (
        f"今天看一个{analysis.relationship_type}案例。"
        f"核心争议是：{analysis.dispute_focus}。"
        f"法院最终认定：{analysis.judgment_result}。"
        f"最后给你一句提醒：{analysis.one_line_warning}"
    )


def _default_shots(analysis: CaseAnalysis) -> list[ShotItem]:
    return [
        ShotItem(id="shot_01", duration=6.0, scene="标题与案由", prompt=f"简洁法治风标题卡，关键词：{analysis.relationship_type}"),
        ShotItem(id="shot_02", duration=18.0, scene="争议焦点", prompt=f"法庭记录风格画面，突出争议焦点：{analysis.dispute_focus}"),
        ShotItem(id="shot_03", duration=18.0, scene="裁判要点", prompt=f"法槌与文书特写，突出裁判结果：{analysis.judgment_result}"),
        ShotItem(id="shot_04", duration=18.0, scene="风险提醒", prompt=f"冷静风法律提示版面，文案：{analysis.one_line_warning}"),
    ]


def _extract_section(case_text: str, heading: str) -> str:
    lines = case_text.splitlines()
    marker = f"- {heading}"
    found = False
    collected: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("-") and stripped != marker and found:
            break
        if stripped == marker:
            found = True
            continue
        if found and stripped:
            collected.append(stripped)

    return " ".join(collected)


def _voiceover_to_srt(voiceover: str) -> str:
    chunks = [chunk for chunk in voiceover.replace("。", "。|\n").split("|\n") if chunk.strip()]
    start = 0
    rows: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        duration = 3
        end = start + duration
        rows.extend([str(idx), f"{_sec_to_ts(start)} --> {_sec_to_ts(end)}", chunk.strip(), ""])
        start = end
    return "\n".join(rows).strip() + "\n"


def _sec_to_ts(total_seconds: int) -> str:
    hh = total_seconds // 3600
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d},000"
