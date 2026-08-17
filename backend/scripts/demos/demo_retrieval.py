"""
Long-term Memory 检索演示 — 展示完整 5 步数据流。

用法:
    cd backend
    python -m memory.demo_retrieval

Step 1~4 可用本地 FAISS 演示；Step 5 需 OPENAI_API_KEY。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from lc.memory.chain import memory_ask, retrieve_memories_for_question
from lc.memory.ingester import ingest_turn
from lc.memory.router import should_retrieve_memory
from infra.memory_vectorstore import MemoryVectorStore


def _seed_store(store: MemoryVectorStore, user_id: str) -> None:
    turns = [
        ("我叫张三", "你好张三，很高兴认识你！"),
        ("我正在学习Agent开发", "很棒，ReAct 和 RAG 都是核心话题。"),
    ]
    for user, assistant in turns:
        ingest_turn(user, assistant, user_id=user_id, session_id="demo", store=store)


def demo_retrieval_flow() -> None:
    print("=== Long-term Memory Retrieval 完整数据流 ===\n")

    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryVectorStore(store_dir=Path(tmp))
        user_id = "demo-user"
        _seed_store(store, user_id)

        queries = [
            ("你还记得我叫什么吗？", "应检索"),
            ("1+1等于几", "应跳过检索"),
            ("今天天气不错", "应跳过检索"),
        ]

        for query, note in queries:
            print(f"--- 问题: {query!r} ({note}) ---")

            decision = should_retrieve_memory(query, user_id=user_id, store=store)
            print(f"Step 1 是否检索: {decision.should_retrieve}  reason={decision.reason}")

            if not decision.should_retrieve:
                print("Step 2~4 跳过\n")
                continue

            try:
                result = retrieve_memories_for_question(
                    query, user_id=user_id, store=store
                )
            except ValueError as exc:
                print(f"Embedding 失败: {exc}\n")
                continue

            print(f"Step 2 Embedding: 完成 (维度索引={store.count} 条)")
            print(f"Step 3 FAISS Top-K: 命中 {len(result.memories)} 条")
            for m in result.memories:
                print(
                    f"       #{m.rank} score={m.score:.4f} "
                    f"type={m.record.memory_type.value} | {m.record.content}"
                )
            print(f"Step 4 Prompt hints:")
            for hint in result.hints:
                print(f"       - {hint}")
            print()

        print("--- Step 5: memory_ask 完整链路 ---")
        try:
            ask_result = memory_ask(
                "你还记得我叫什么吗？",
                user_id=user_id,
                store=store,
            )
            print(f"should_retrieve={ask_result.should_retrieve}")
            print(f"memories={len(ask_result.memories)}")
            print(f"answer={ask_result.answer[:120]}")
        except ValueError as exc:
            print(f"Step 5 跳过（需 API Key）: {exc}")


if __name__ == "__main__":
    demo_retrieval_flow()
