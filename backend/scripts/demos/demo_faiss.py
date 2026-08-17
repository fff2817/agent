"""
Chroma 向量索引 — 可运行演示（LangChain Chroma）。

用法（backend 目录）:
    # 使用 mock 向量（无需 API Key，验证 Chroma 存取）
    .venv\\Scripts\\python.exe -m scripts.demos.demo_faiss --mock

    # 使用真实 Embedding API
    .venv\\Scripts\\python.exe -m scripts.demos.demo_faiss

流程:
    1. 每个 chunk 变成高维向量（Embedding）
    2. 向量写入 Chroma（persist_directory 持久化）
    3. 用户问题也变成向量
    4. 余弦相似度检索 Top-K，带回原文 metadata
"""

from __future__ import annotations

import argparse
import logging
import sys

import numpy as np

from infra.rag_vectorstore import FaissVectorStore
from lc.llm.embeddings import embed_chunks
from lc.rag.chunker import chunk_plain_text
from lc.rag.types import EmbeddedChunk, TextChunk

logging.basicConfig(level=logging.INFO, format="%(message)s")

SAMPLE_DOC = """
第一章 报销流程
员工需在内网填写电子报销申请单，附上正规发票原件或电子版。
单笔金额超过 5000 元需部门经理审批。
财务审核通过后，款项于 15 个工作日内打入工资卡。

第二章 差旅报销
出差交通费按实报销，住宿标准一线城市每晚不超过 500 元。
餐补按天计算，国内出差每天 100 元。

第三章 休假制度
年假：工作满 1 年享有 5 天带薪年假，每增加一年加 1 天，上限 15 天。
病假：需提交二级以上医院证明。
事假：提前 3 个工作日申请，由直属领导批准。
"""


def _banner(title: str) -> None:
    print("\n" + "=" * 62)
    print(f"  {title}")
    print("=" * 62)


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm < 1e-12:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def _make_mock_embedded(chunks: list[TextChunk], dim: int = 128) -> list[EmbeddedChunk]:
    """用固定随机种子生成 mock 向量（无需 API）。"""
    results: list[EmbeddedChunk] = []
    for chunk in chunks:
        rng = np.random.default_rng(seed=int(chunk.chunk_id) + 42)
        vec = _l2_normalize(rng.standard_normal(dim).astype(np.float32))
        results.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding=vec.tolist(),
                model="mock",
                dimensions=dim,
            )
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Chroma 向量索引 Demo")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="使用 mock 向量（不需要 OPENAI_API_KEY）",
    )
    parser.add_argument(
        "--store",
        default="rag/store/demo",
        help="索引存储目录（默认 rag/store/demo）",
    )
    args = parser.parse_args()

    _banner("Chroma 工作原理（简要）")
    print("""
  1. Embedding:  文本 → 高维向量
  2. Chroma 存储: chunk 向量 + metadata 同库，落盘到 persist_directory
  3. 用户提问:    问题也变成 query 向量
  4. Similarity Search: 余弦空间 Top-K（score = 1 - distance）
  5. 映射回原文:  metadata / documents 直接带回文本、页码、来源
""")

    _banner("Step A — 文档切分")
    chunks = chunk_plain_text(SAMPLE_DOC, source="员工手册.txt", chunk_size=120, chunk_overlap=20)
    print(f"  共 {len(chunks)} 个 chunk\n")
    for c in chunks:
        print(f"    Chunk #{c.chunk_id}: {c.text[:60].replace(chr(10), ' ')}...")

    _banner("Step B — 生成 Embedding")
    if args.mock:
        print("  模式: mock（随机向量，无需 API）\n")
        embedded = _make_mock_embedded(chunks, dim=128)
    else:
        print("  模式: 真实 API（需 .env 配置 OPENAI_API_KEY）\n")
        try:
            embedded = embed_chunks(chunks)
        except (ValueError, Exception) as exc:
            print(f"  API 失败: {exc}", file=sys.stderr)
            print("  提示: 可加 --mock 跳过 API\n", file=sys.stderr)
            sys.exit(1)

    print(f"  已向量化 {len(embedded)} 条, 维度={embedded[0].dimensions}")

    _banner("Step C — 写入 Chroma 并保存")
    store = FaissVectorStore(store_dir=args.store)
    store.clear()
    store.add_embeddings(embedded)
    store.save()
    print(f"\n  持久化目录: {args.store}/chroma.sqlite3")

    _banner("Step D — 从磁盘重新打开")
    store2 = FaissVectorStore(store_dir=args.store)
    print(f"  已加载 {store2.count} 条向量")

    _banner("Step E — Similarity Search (Top-3)")
    if args.mock:
        query_vector = embedded[min(2, len(embedded) - 1)].embedding
        print("  Query: （mock: 使用某一 chunk 向量作为 query）\n")
        results = store2.search(query_vector, top_k=3)
    else:
        from lc.rag.retriever import search_similar

        query_text = "报销需要哪些材料？"
        print(f'  Query: "{query_text}"\n')
        results = search_similar(query_text, store=store2, top_k=3)

    _banner("检索结果 Top-K")
    for r in results:
        print(f"\n  Rank #{r.rank}  |  score={r.score:.4f}  | id={r.faiss_id}")
        print(f"  来源: {r.chunk.source} 第{r.chunk.page}页")
        print(f"  文本: {r.chunk.text[:120]}{'...' if len(r.chunk.text) > 120 else ''}")

    _banner("完成")
    print("  下一步: 封装为 tools/search_docs，接入 Agent\n")


if __name__ == "__main__":
    main()
