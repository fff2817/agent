"""可选 LangSmith / 运行追踪钩子（占位）。"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_tracing() -> None:
    """若设置 LANGCHAIN_TRACING_V2 / LANGSMITH_API_KEY 则启用环境侧追踪。"""
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() in {"1", "true", "yes"}:
        logger.info("[Tracing] LangSmith tracing env detected")
    else:
        logger.debug("[Tracing] LangSmith not enabled")
