"""回答质量评估 — LLM-as-Judge。"""

from __future__ import annotations

import json
import logging
import re

from core.config import get_settings
from lc.llm.chat import chat_completion
from lc.prompts import build_judge_messages
from eval.types import AnswerEvaluation

logger = logging.getLogger(__name__)


def _parse_json_content(content: str) -> dict:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _fallback_answer_eval(retrieval_avg: float) -> AnswerEvaluation:
    score = _clamp(retrieval_avg)
    verdict = "good" if score >= 0.75 else "acceptable" if score >= 0.5 else "poor"
    return AnswerEvaluation(
        faithfulness=score,
        answer_relevance=score,
        completeness=score,
        overall_score=score,
        verdict=verdict,
        issues=["Judge 不可用，已回退到检索均分"],
        judge_model="fallback",
    )


def run_llm_judge(question: str, context: str, answer: str) -> tuple[AnswerEvaluation, list[dict]]:
    """
    调用 LLM 评估回答质量，并返回 per-source 检索评分。

    返回:
        (AnswerEvaluation, retrieval_items)
    """
    settings = get_settings()
    if not settings.openai_api_key:
        logger.warning("[Eval] API Key 未配置，使用 fallback 评分")
        return _fallback_answer_eval(0.5), []

    messages = build_judge_messages(
        question=question,
        context=context[:6000] if context else "（无检索资料）",
        answer=answer,
    )

    try:
        message = chat_completion(messages)
        raw = message.content or ""
        data = _parse_json_content(raw)
    except Exception as exc:
        logger.warning("[Eval] LLM Judge 失败: %s", exc)
        return _fallback_answer_eval(0.5), []

    faithfulness = _clamp(data.get("faithfulness", 0.5))
    answer_relevance = _clamp(data.get("answer_relevance", 0.5))
    completeness = _clamp(data.get("completeness", 0.5))
    overall = _clamp(
        data.get(
            "overall_score",
            (faithfulness + answer_relevance + completeness) / 3,
        )
    )

    verdict = str(data.get("verdict", "acceptable"))
    if verdict not in {"good", "acceptable", "poor"}:
        verdict = "good" if overall >= 0.75 else "acceptable" if overall >= 0.5 else "poor"

    issues = [str(i) for i in data.get("issues", []) if i]
    retrieval_items = data.get("retrieval_items") or []

    return (
        AnswerEvaluation(
            faithfulness=round(faithfulness, 4),
            answer_relevance=round(answer_relevance, 4),
            completeness=round(completeness, 4),
            overall_score=round(overall, 4),
            verdict=verdict,
            issues=issues,
            judge_model=settings.openai_model,
        ),
        retrieval_items,
    )
