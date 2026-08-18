"""
Long-term Memory 本地演示 — 不启动 FastAPI。

用法:
    cd backend
    python -m memory.demo_longterm

需要 .env 中配置 OPENAI_API_KEY（Embedding API）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from lc.memory.extractor import extract_memory
from lc.memory.ingester import ingest_turn
from lc.memory.retriever import retrieve_memories
from infra.memory_vectorstore import MemoryVectorStore


def demo_filter_only() -> None:
    print("=== Step 1: 记忆筛选（无需 API Key）===\n")
    cases = [
        "我叫张三",
        "今天天气不错",
        "我正在学习Agent开发",
        "你好",
        "记住以后用英文回答",
    ]
    for msg in cases:
        r = extract_memory(msg, user_id="demo-user", session_id="demo-session")
        status = "[SAVE]" if r.should_save else "[SKIP]"
        content = r.record.content if r.record else "-"
        print(f"{status} | {msg!r}")
        print(f"       reason={r.reason}, content={content}\n")


def demo_full_pipeline() -> None:
    print("=== Step 2~4: 筛选 → Embedding → Chroma → 检索 ===\n")

    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryVectorStore(store_dir=Path(tmp))
        user_id = "demo-user"

        turns = [
            ("我叫张三", "你好张三，很高兴认识你！"),
            ("今天天气不错", "是的，适合出门走走。"),
            ("我正在学习Agent开发", "很棒，ReAct 和 RAG 都是核心话题。"),
        ]

        for user, assistant in turns:
            result = ingest_turn(
                user,
                assistant,
                user_id=user_id,
                session_id="demo-session",
                store=store,
            )
            label = "saved" if result.should_save else "skipped"
            print(f"[{label}] user={user!r} reason={result.reason}")

        print(f"\nChroma 索引条数: {store.count}\n")

        query = "你还记得我叫什么吗？"
        hits = retrieve_memories(query, user_id=user_id, store=store)
        print(f"检索 query={query!r}")
        for hit in hits:
            print(f"  #{hit.rank} score={hit.score:.4f} content={hit.record.content}")

        hints = [hit.record.content for hit in hits]
        print(f"\n检索 hints → {hints}")


if __name__ == "__main__":
    demo_filter_only()
    print("-" * 50)
    try:
        demo_full_pipeline()
    except ValueError as exc:
        print(f"完整流水线跳过（需配置 API Key）: {exc}")
