"""
完整 RAG 流程演示 — 从入库到问答。

用法（backend 目录）:

    # 1. 入库 + 问答（mock 向量，无需 Embedding API，但 LLM 回答仍需 API Key）
    .venv\\Scripts\\python.exe -m rag.demo_rag --mock

    # 2. 分步: 仅入库
    .venv\\Scripts\\python.exe -m rag.demo_rag --ingest

    # 3. 分步: 仅问答（需先入库）
    .venv\\Scripts\\python.exe -m rag.demo_rag --ask "报销需要哪些材料？"

完整数据流:
    用户问题 → Embedding → FAISS Search → Top-K Chunk
             → Prompt 拼接 → LLM 回答
"""

import argparse
import logging
import sys

import faiss
import numpy as np

from lc.rag.chain import rag_ask
from lc.rag.chunker import chunk_plain_text
from lc.llm.embeddings import embed_chunks
from lc.rag.types import EmbeddedChunk, TextChunk
from infra.rag_vectorstore import FaissVectorStore

logging.basicConfig(level=logging.INFO, format="%(message)s")

SAMPLE_DOC = """
第一章 报销流程
1. 员工需在内网填写电子报销申请单。
2. 附上正规发票原件或电子版，发票抬头须与公司全称一致。
3. 单笔金额超过 5000 元需部门经理审批。
4. 财务审核通过后，款项于 15 个工作日内打入工资卡。

第二章 差旅报销
出差交通费按实报销，住宿标准一线城市每晚不超过 500 元。
餐补按天计算，国内出差每天 100 元。

第三章 休假制度
年假：工作满 1 年享有 5 天带薪年假，每增加一年加 1 天，上限 15 天。
病假：需提交二级以上医院证明。
事假：提前 3 个工作日申请，由直属领导批准。
"""

DEFAULT_QUESTION = "报销需要哪些材料？"
DEFAULT_STORE = "rag/store/rag_demo"


def _banner(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def _mock_embedded(chunks: list[TextChunk], dim: int = 128) -> list[EmbeddedChunk]:
    results: list[EmbeddedChunk] = []
    for chunk in chunks:
        rng = np.random.default_rng(seed=chunk.chunk_id + 42)
        vec = rng.standard_normal(dim).astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        results.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding=vec[0].tolist(),
                model="mock",
                dimensions=dim,
            )
        )
    return results


def run_ingest(store_dir: str, use_mock: bool) -> FaissVectorStore:
    _banner("阶段 0 — 文档入库（离线准备）")
    print("""
  作用: 把文档切成 chunk → 向量化 → 存入 FAISS
  这是一次性/定期更新的步骤，不是每次问答都做
""")

    chunks = chunk_plain_text(SAMPLE_DOC, source="员工手册.txt", chunk_size=150, chunk_overlap=20)
    print(f"  切分得到 {len(chunks)} 个 chunk\n")

    store = FaissVectorStore(store_dir=store_dir)

    if use_mock:
        print("  使用 mock 向量入库（跳过 Embedding API）\n")
        embedded = _mock_embedded(chunks)
    else:
        print("  使用真实 Embedding API 入库\n")
        embedded = embed_chunks(chunks)

    store.add_embeddings(embedded)
    store.save()
    print(f"  [OK] 入库完成: {store.count} 条向量 -> {store_dir}/")
    return store


def run_ask(question: str, store_dir: str) -> None:
    _banner("完整 RAG 数据流")

    print("""
  ┌─────────────────────────────────────────────────────────┐
  │  Step 1  用户问题     接收用户自然语言提问                  │
  │  Step 2  Embedding    把问题变成向量（语义坐标）            │
  │  Step 3  FAISS Search 在向量库中找最相似的 Top-K chunk     │
  │  Step 4  Top-K Chunk  取出对应的文档原文 + 页码 + 分数      │
  │  Step 5  Prompt 拼接   资料 + 问题 → LLM messages          │
  │  Step 6  LLM 回答      基于资料生成回答（不编造）             │
  └─────────────────────────────────────────────────────────┘
""")

    store = FaissVectorStore(store_dir=store_dir)

    print(f'  问题: "{question}"\n')
    print("  --- 开始执行（详见 [RAG] 日志）---\n")

    result = rag_ask(question, store=store)

    _banner("RAG 结果")

    print(f'  问题: {result.question}\n')
    print("  【检索到的 Top-K Chunk】")
    for s in result.sources:
        print(f"\n  Rank #{s.rank} | score={s.score:.4f} | {s.chunk.source} p.{s.chunk.page}")
        print(f"  {s.chunk.text[:120]}{'...' if len(s.chunk.text) > 120 else ''}")

    print("\n  【LLM 最终回答】")
    print(f"  {result.answer}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="完整 RAG 流程 Demo")
    parser.add_argument("--mock", action="store_true", help="入库时使用 mock 向量")
    parser.add_argument("--ingest", action="store_true", help="仅执行入库")
    parser.add_argument("--ask", type=str, default=None, help="指定问题（默认: 报销需要哪些材料？）")
    parser.add_argument("--store", default=DEFAULT_STORE, help="FAISS 存储目录")
    args = parser.parse_args()

    question = args.ask or DEFAULT_QUESTION

    try:
        if args.ingest:
            run_ingest(args.store, use_mock=args.mock)
            return

        if args.ask is not None or not args.ingest:
            # 若索引不存在，先入库
            store = FaissVectorStore(store_dir=args.store)
            if store.count == 0:
                print("  向量库为空，先执行入库...\n")
                store = run_ingest(args.store, use_mock=args.mock)

            if args.mock and store.count == 0:
                store = run_ingest(args.store, use_mock=True)

            run_ask(question, args.store)

    except ValueError as exc:
        print(f"\n  错误: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n  失败: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
