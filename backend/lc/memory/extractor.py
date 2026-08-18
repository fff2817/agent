"""
Long-term Memory 筛选器 — 决定「什么值得存」。

流水线位置:
    用户消息 (+ 助手回复)
        ↓  Layer 1 黑白名单（零成本硬规则）
        ↓  Layer 2 启发式打分
        ↓  ExtractionResult（should_save + MemoryRecord）

设计原因:
    不能每句话都 embed 进 Chroma — 噪声会污染检索、浪费 API 成本。
    先用规则过滤 80% 无效输入，再对边界 case 打分。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from lc.memory.types import ExtractionResult, MemoryRecord, MemoryType

logger = logging.getLogger(__name__)

# --- Layer 1: Blacklist ---

_SMALL_TALK = frozenset(
    {
        "你好",
        "您好",
        "hi",
        "hello",
        "谢谢",
        "感谢",
        "多谢",
        "再见",
        "拜拜",
        "好的",
        "好",
        "嗯",
        "哦",
        "ok",
        "okay",
    }
)

_TEMPORAL_PATTERNS = (
    re.compile(r"今天.{0,6}天气"),
    re.compile(r"^(今天|刚才|现在|此刻).{0,20}(不错|很好|有点|可能)"),
    re.compile(r"^(有点累|有点忙|有点饿|在吗)\??$"),
)

_SENSITIVE_PATTERNS = (
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"\b\d{15,18}\b"),
    re.compile(r"(密码|password|api[_\s]?key)\s*[:：]\s*\S+", re.IGNORECASE),
)

# --- Layer 1: Whitelist ---

_EXPLICIT_REMEMBER = re.compile(
    r"(记住|别忘了|不要忘记|以后都|下次也要|请始终|永远|一直用)",
    re.IGNORECASE,
)

_IDENTITY_PATTERNS: list[tuple[re.Pattern[str], str, MemoryType]] = [
    (re.compile(r"我叫\s*([^\s，,。.!！?？]{1,20})"), r"用户姓名：\1", MemoryType.IDENTITY),
    (re.compile(r"我是\s*([^\s，,。.!！?？]{1,30})"), r"用户身份：\1", MemoryType.IDENTITY),
    (re.compile(r"称呼我\s*([^\s，,。.!！?？]{1,20})"), r"用户希望被称呼为：\1", MemoryType.IDENTITY),
]

_PREFERENCE_PATTERNS: list[tuple[re.Pattern[str], str, MemoryType]] = [
    (
        re.compile(r"(以后|请|始终|一直).{0,8}(用英文|说英文|英文回答)"),
        "用户偏好：助手回复使用英文",
        MemoryType.PREFERENCE,
    ),
    (
        re.compile(r"(以后|请|始终|一直).{0,8}(用中文|说中文|中文回答)"),
        "用户偏好：助手回复使用中文",
        MemoryType.PREFERENCE,
    ),
    (
        re.compile(r"(不要|别|禁止).{0,6}(emoji|表情)"),
        "用户偏好：回复中不要使用 emoji",
        MemoryType.PREFERENCE,
    ),
    (
        re.compile(r"(简洁|简短|精炼).{0,6}(回答|回复|说明)"),
        "用户偏好：回复简洁精炼",
        MemoryType.PREFERENCE,
    ),
]

_GOAL_PATTERNS: list[tuple[re.Pattern[str], str, MemoryType]] = [
    (
        re.compile(r"(正在|我在|目前在)(学习|研究|做|开发).{1,40}"),
        None,
        MemoryType.GOAL,
    ),
]

_IMPORTANCE_BY_TYPE: dict[MemoryType, float] = {
    MemoryType.IDENTITY: 0.95,
    MemoryType.PREFERENCE: 0.90,
    MemoryType.FACT: 0.85,
    MemoryType.GOAL: 0.65,
    MemoryType.EPISODIC: 0.55,
}


@dataclass(frozen=True)
class _ScoreBreakdown:
    stability: float
    reusability: float
    explicitness: float
    uniqueness: float

    @property
    def total(self) -> float:
        return (
            0.35 * self.stability
            + 0.35 * self.reusability
            + 0.20 * self.explicitness
            + 0.10 * self.uniqueness
        )


def extract_memory(
    user_message: str,
    assistant_message: str = "",
    *,
    user_id: str,
    session_id: str | None = None,
    min_score: float = 0.75,
) -> ExtractionResult:
    """
    从一轮对话中提取是否值得长期保存的记忆。

    参数:
        user_message:      用户输入
        assistant_message: 助手最终回复（可选，辅助判断）
        user_id:           记忆归属（MVP 可用 session_id）
        session_id:        来源 session
        min_score:         Layer 2 入库阈值

    返回:
        ExtractionResult — should_save=False 时 record 为 None
    """
    user = user_message.strip()
    if not user:
        return ExtractionResult(False, reason="empty_message")

    normalized = user.lower().strip("。！？!.? ")

    # Layer 1 — Blacklist
    if len(user) < 4 and not _EXPLICIT_REMEMBER.search(user):
        return ExtractionResult(False, reason="blacklist:too_short")

    if normalized in _SMALL_TALK:
        return ExtractionResult(False, reason="blacklist:small_talk")

    for pattern in _TEMPORAL_PATTERNS:
        if pattern.search(user):
            return ExtractionResult(False, reason="blacklist:temporal")

    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(user):
            return ExtractionResult(False, reason="blacklist:sensitive")

    # Layer 1 — Whitelist: identity
    for pattern, content_tpl, mem_type in _IDENTITY_PATTERNS:
        match = pattern.search(user)
        if match:
            content = pattern.sub(content_tpl, user) if r"\1" in content_tpl else content_tpl
            record = _make_record(
                user_id=user_id,
                content=content,
                memory_type=mem_type,
                raw_user=user,
                session_id=session_id,
            )
            logger.info("[Extractor] whitelist identity: %s", content)
            return ExtractionResult(True, record=record, reason="whitelist:identity", score=1.0)

    # Layer 1 — Whitelist: explicit remember
    if _EXPLICIT_REMEMBER.search(user):
        content = _normalize_explicit(user)
        record = _make_record(
            user_id=user_id,
            content=content,
            memory_type=MemoryType.PREFERENCE,
            raw_user=user,
            session_id=session_id,
        )
        logger.info("[Extractor] whitelist explicit: %s", content)
        return ExtractionResult(True, record=record, reason="whitelist:explicit", score=1.0)

    # Layer 1 — Whitelist: preference patterns
    for pattern, content, mem_type in _PREFERENCE_PATTERNS:
        if pattern.search(user):
            record = _make_record(
                user_id=user_id,
                content=content,
                memory_type=mem_type,
                raw_user=user,
                session_id=session_id,
            )
            logger.info("[Extractor] whitelist preference: %s", content)
            return ExtractionResult(
                True, record=record, reason="whitelist:preference", score=1.0
            )

    # Layer 1 — Whitelist: goal (with template expansion)
    for pattern, content_tpl, mem_type in _GOAL_PATTERNS:
        match = pattern.search(user)
        if match:
            content = content_tpl or f"用户当前目标：{match.group(0).strip('。！？')}"
            record = _make_record(
                user_id=user_id,
                content=content,
                memory_type=mem_type,
                raw_user=user,
                session_id=session_id,
            )
            logger.info("[Extractor] whitelist goal: %s", content)
            return ExtractionResult(True, record=record, reason="whitelist:goal", score=0.72)

    # Layer 2 — Heuristic scoring
    breakdown = _score_message(user, assistant_message)
    score = breakdown.total
    logger.info(
        "[Extractor] score=%.2f stability=%.2f reusability=%.2f",
        score,
        breakdown.stability,
        breakdown.reusability,
    )

    if score >= min_score:
        record = _make_record(
            user_id=user_id,
            content=f"用户相关信息：{user.rstrip('。！？')}",
            memory_type=MemoryType.FACT,
            raw_user=user,
            session_id=session_id,
        )
        return ExtractionResult(
            True, record=record, reason="score:above_threshold", score=score
        )

    return ExtractionResult(False, reason="score:below_threshold", score=score)


def _make_record(
    *,
    user_id: str,
    content: str,
    memory_type: MemoryType,
    raw_user: str,
    session_id: str | None,
) -> MemoryRecord:
    return MemoryRecord(
        user_id=user_id,
        content=content,
        memory_type=memory_type,
        importance=_IMPORTANCE_BY_TYPE.get(memory_type, 0.7),
        source_session_id=session_id,
        raw_user=raw_user,
    )


def _normalize_explicit(user: str) -> str:
    text = user.strip().rstrip("。！？")
    for prefix in ("请", "帮我", "麻烦"):
        if text.startswith(prefix):
            text = text[len(prefix) :].lstrip()
    return f"用户要求记住：{text}"


def _score_message(user: str, assistant: str) -> _ScoreBreakdown:
    """启发式打分 — 仅处理未命中黑白名单的消息。"""
    stability = 0.3
    reusability = 0.3
    explicitness = 0.2
    uniqueness = 0.5

    if re.search(r"我的|我是|我在|我们(公司|团队)", user):
        stability += 0.3
        reusability += 0.3
        uniqueness += 0.3

    if re.search(r"喜欢|偏好|习惯|总是|一般", user):
        stability += 0.2
        reusability += 0.3

    if re.search(r"^(帮|请|算|翻译|写一段)", user):
        reusability -= 0.3

    if assistant and len(assistant) > 20:
        reusability += 0.05

    return _ScoreBreakdown(
        stability=min(stability, 1.0),
        reusability=min(max(reusability, 0.0), 1.0),
        explicitness=min(explicitness, 1.0),
        uniqueness=min(uniqueness, 1.0),
    )
