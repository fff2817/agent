"""
FAISS 向量索引 — 可运行演示。

用法（backend 目录）:
    # 使用 mock 向量（无需 API Key，验证 FAISS 逻辑）
    .venv\\Scripts\\python.exe -m rag.demo_faiss --mock

    # 使用真实 Embedding API
    .venv\\Scripts\\python.exe -m rag.demo_faiss

FAISS 工作原理（本 demo 会逐步打印）:
    1. 每个 chunk 变成高维向量（Embedding）
    2. 向量存入 FAISS 索引（坐标系里的点）
    3. 用户问题也变成向量
    4. FAISS 计算 query 与所有点的相似度，返回 Top-K 最近的
"""

import argparse
import logging
import sys

import faiss
import numpy as np

from rag.chunker import chunk_plain_text
from rag.embedder import embed_chunks
from rag.types import EmbeddedChunk, TextChunk
from rag.vectorstore import FaissVectorStore

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


def _make_mock_embedded(chunks: list[TextChunk], dim: int = 128) -> list[EmbeddedChunk]:
    """
    用固定随机种子生成 mock 向量（无需 API）。
    注意: mock 向量没有真实语义，仅用于验证 FAISS 存取与搜索流程。
    """
    results: list[EmbeddedChunk] = []
    for i, chunk in enumerate(chunks):
        rng = np.random.default_rng(seed=chunk.chunk_id + 42)
        vec = rng.standard_normal(dim).astype(np.float32)
        vec_2d = vec.reshape(1, -1)
        faiss.normalize_L2(vec_2d)
        results.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding=vec_2d[0].tolist(),
                model="mock",
                dimensions=dim,
            )
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="FAISS 向量索引 Demo")
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

    _banner("FAISS 工作原理（简要）")
    print("""
  1. Embedding:  文本 → 高维向量（一排 float）
  2. FAISS 存储:  所有 chunk 向量放进「索引」（类似搜索引擎的倒排表）
  3. 用户提问:    问题也变成 query 向量
  4. Similarity Search: FAISS 在索引里找与 query 最相似的 Top-K 个向量
  5. 映射回原文:  FAISS 只返回「第几个向量 + 分数」，metadata.json 存原文

  本 demo 使用 IndexFlatIP:
    · 精确搜索（暴力比对每一条，适合 demo 和小规模数据）
    · IP = Inner Product 内积；向量 L2 归一化后，内积 = 余弦相似度
""")

    # --- Step A: 切分文档 ---
    _banner("Step A — 文档切分")
    chunks = chunk_plain_text(SAMPLE_DOC, source="员工手册.txt", chunk_size=120, chunk_overlap=20)
    print(f"  共 {len(chunks)} 个 chunk\n")
    for c in chunks:
        print(f"    Chunk #{c.chunk_id}: {c.text[:60].replace(chr(10), ' ')}...")

    # --- Step B: Embedding ---
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

    # --- Step C: 写入 FAISS ---
    _banner("Step C — 写入 FAISS 并保存")
    store = FaissVectorStore(store_dir=args.store)
    store.add_embeddings(embedded)
    store.save()
    print(f"\n  索引路径: {args.store}/faiss.index")
    print(f"  元数据:   {args.store}/metadata.json")

    # --- Step D: 重新加载（模拟重启后检索）---
    _banner("Step D — 从磁盘 load 索引")
    store2 = FaissVectorStore(store_dir=args.store)
    print(f"  已加载 {store2.count} 条向量")

    # --- Step E: Similarity Search ---
    _banner("Step E — Similarity Search (Top-3)")

    if args.mock:
        # mock 模式下用第一个 chunk 的向量模拟「相关问题」
        query_vector = embedded[2].embedding
        query_text = "（mock: 使用 chunk#2 的向量作为 query）"
        print(f"  Query: {query_text}\n")
        results = store2.search(query_vector, top_k=3)
    else:
        from rag.embedder import embed_text
        from rag.retriever import search_similar

        query_text = "报销需要哪些材料？"
        print(f'  Query: "{query_text}"\n')
        results = search_similar(query_text, store=store2, top_k=3)

    _banner("检索结果 Top-K")
    for r in results:
        print(f"\n  Rank #{r.rank}  |  score={r.score:.4f}  |  faiss_id={r.faiss_id}")
        print(f"  来源: {r.chunk.source} 第{r.chunk.page}页")
        print(f"  文本: {r.chunk.text[:120]}{'...' if len(r.chunk.text) > 120 else ''}")

    _banner("完成")
    print("  下一步: 封装为 tools/search_docs，接入 ReAct Agent\n")


if __name__ == "__main__":
    main()
