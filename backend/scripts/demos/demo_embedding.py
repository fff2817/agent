"""
Embedding 演示脚本 — 看文本如何变成向量。

用法（在 backend 目录）:
    .venv\\Scripts\\python.exe -m rag.demo_embedding

需要 .env 中配置:
    OPENAI_API_KEY=...
    # 若用智谱，还需 OPENAI_BASE_URL 和 EMBEDDING_MODEL=embedding-3
"""

import logging
import sys

from lc.rag.chunker import chunk_plain_text
from lc.llm.embeddings import (
    cosine_similarity,
    embed_chunks,
    embed_text,
    format_vector_preview,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")


def _banner(title: str) -> None:
    print("\n" + "=" * 62)
    print(f"  {title}")
    print("=" * 62)


def demo_single_text() -> list[float]:
    """演示 1：单段文本 → 向量，并打印结果。"""
    _banner("演示 1 — 什么是向量？")

    print("""
  向量 = 把文字变成「一排数字」，每个数字是一个 float。

  人看:  "报销需填写电子申请单"
  机器:  [0.023, -0.156, 0.891, 0.044, ...]  ← 可能有几百到几千个数字

  这排数字编码了这句话的「语义」。
  意思相近的句子，数字排出来的「方向」也相近。
""")

    text = "报销需填写电子申请单，并附上发票。"
    print(f'  输入文本: "{text}"')
    print("  正在调用 OpenAI Embedding API...\n")

    vector = embed_text(text)

    print(f"  ✓ 向量维度: {len(vector)}  （即有 {len(vector)} 个数字）")
    print(f"  ✓ 向量预览: {format_vector_preview(vector)}")
    print(f"  ✓ 前 3 个数: {vector[0]:.6f}, {vector[1]:.6f}, {vector[2]:.6f}")

    return vector


def demo_similarity() -> None:
    """演示 2：比较不同文本的向量相似度。"""
    _banner("演示 2 — 为什么「苹果手机」和「iPhone」向量很近？")

    print("  对三句话分别生成向量，再算「余弦相似度」(越接近 1 越像):\n")

    texts = ["苹果手机", "iPhone", "今天下雨"]
    vectors = {t: embed_text(t) for t in texts}

    for t, v in vectors.items():
        print(f'    "{t}" → 维度 {len(v)}, 预览 {format_vector_preview(v, head=4, tail=2)}')

    print()
    pairs = [
        ("苹果手机", "iPhone"),
        ("苹果手机", "今天下雨"),
        ("iPhone", "今天下雨"),
    ]
    for a, b in pairs:
        sim = cosine_similarity(vectors[a], vectors[b])
        bar = "█" * int(max(0, sim) * 20)
        print(f'    "{a}" vs "{b}"')
        print(f"      相似度 = {sim:.4f}  {bar}\n")


def demo_chunks() -> None:
    """演示 3：对 TextChunk 批量 embedding（对接 RAG 流水线）。"""
    _banner("演示 3 — Chunk + Embedding（RAG 入库前一步）")

    sample_doc = """
    第一章 报销流程
    员工需在内网填写电子报销申请单，附上正规发票。
    单笔超过 5000 元需部门经理审批。

    第二章 休假制度
    年假：工作满 1 年享有 5 天带薪年假。
    """

    chunks = chunk_plain_text(sample_doc, source="员工手册.txt", chunk_size=80, chunk_overlap=10)
    print(f"  切分得到 {len(chunks)} 个 chunk，开始批量向量化...\n")

    embedded = embed_chunks(chunks)

    for item in embedded:
        c = item.chunk
        print(f"  --- Chunk #{c.chunk_id} | 第{c.page}页 | {c.char_count}字 ---")
        print(f"  文本: {c.text[:60]}{'...' if len(c.text) > 60 else ''}")
        print(f"  模型: {item.model} | 维度: {item.dimensions}")
        print(f"  向量: {format_vector_preview(item.embedding, head=5, tail=2)}")
        print()


def main() -> None:
    _banner("Embedding 模块教学 Demo")
    print("  流水线位置: PDF → Loader → Chunker → 【Embedding】→ 向量库")
    print("  确保 backend/.env 已配置 OPENAI_API_KEY\n")

    try:
        demo_single_text()
        demo_similarity()
        demo_chunks()

        _banner("完成")
        print("  下一步: 把 EmbeddedChunk 存入 Chroma，用户提问时检索相似向量\n")

    except ValueError as exc:
        print(f"\n  错误: {exc}", file=sys.stderr)
        print("  请检查 backend/.env 中的 OPENAI_API_KEY 和 EMBEDDING_MODEL", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n  API 调用失败: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
