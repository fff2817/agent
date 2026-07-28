"""回答质量评估 — LLM-as-Judge。"""

from __future__ import annotations

import json
import logging
import re

from core.config import get_settings
from core.llm import chat_completion

from eval.types import AnswerEvaluation

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = """你是 RAG 质量评估专家。根据用户问题、检索资料和 AI 回答，输出 JSON 评估结果。
只输出 JSON，不要 markdown 代码块。"""

JUDGE_USER_TEMPLATE = """请评估以下 RAG 问答质量。

【用户问题】
{question}

【检索资料】
{context}

【AI 回答】
{answer}

请输出 JSON，字段如下：
{{
  "retrieval_items": [
    {{"rank": 1, "relevant": true, "score": 0.0-1.0, "reason": "简短说明"}}
  ],
  "faithfulness": 0.0-1.0,
  "answer_relevance": 0.0-1.0,
  "completeness": 0.0-1.0,
  "overall_score": 0.0-1.0,
  "verdict": "good|acceptable|poor",
  "issues": ["问题1", "问题2"]
}}

评分标准：
- faithfulness: 回答是否被资料支撑，有无幻觉
- answer_relevance: 回答是否切题
- completeness: 是否覆盖问题要点
- retrieval_items: 对每条检索片段（按 rank）判断是否真正相关
"""


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

    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {
            "role": "user",
            "content": JUDGE_USER_TEMPLATE.format(
                question=question,
                context=context[:6000] if context else "（无检索资料）",
                answer=answer,
            ),
        },
    ]

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
    overall = _clamp(data.get("overall_score", (faithfulness + answer_relevance + completeness) / 3))

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
