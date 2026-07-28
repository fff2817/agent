"""
PDF 提取 + Chunk 切分 — 可运行演示脚本。

用法:
    # 使用内置示例文本（无需 PDF）
    python -m rag.demo_pdf_chunk

    # 指定 PDF 文件
    python -m rag.demo_pdf_chunk path/to/your.pdf

    # 指定文本文件
    python -m rag.demo_pdf_chunk path/to/doc.txt

在 backend 目录下运行。
"""

import logging
import sys
from pathlib import Path

from rag.chunker import chunk_document
from rag.loader import load_pdf, load_text_file
from rag.types import ExtractedDocument, PageText

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

# 内置示例：模拟一份「员工手册」片段，方便没有 PDF 时学习
SAMPLE_TEXT = """
员工手册 — 报销与休假

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


def _print_separator(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _run_pipeline(document: ExtractedDocument, chunk_size: int = 500, overlap: int = 50) -> None:
    """演示完整流水线: 文档 → 切分 → 打印每个 chunk。"""
    _print_separator("Step 1 — 文档概览（Loader 输出）")
    print(f"  来源:     {document.source}")
    print(f"  页数:     {len(document.pages)}")
    print(f"  总字符:   {len(document.full_text)}")

    for p in document.pages:
        preview = p.text[:80].replace("\n", " ")
        print(f"  第 {p.page} 页: {len(p.text)} 字符 — {preview}...")

    _print_separator("Step 2 — Chunk 切分（Chunker 输出）")
    print(f"  chunk_size={chunk_size}, overlap={overlap}")
    print()
    print("  为什么需要 Chunk?")
    print("    · 整篇文档太大，无法一次塞进 LLM")
    print("    · 检索时要「段落级」命中，而不是整本书")
    print("    · 每块会变成向量库里的一个检索单元")
    print()

    chunks = chunk_document(document, chunk_size=chunk_size, chunk_overlap=overlap)

    _print_separator(f"Step 3 — 共 {len(chunks)} 个 Chunk（RAG 检索单元）")

    for c in chunks:
        print(f"\n  --- Chunk #{c.chunk_id} | 第 {c.page} 页 | {c.char_count} 字符 ---")
        print(f"  {c.text[:200]}{'...' if len(c.text) > 200 else ''}")

    _print_separator("完成")
    print("  下一步: 对每个 Chunk 做 Embedding → 存入向量库 → 用户提问时检索")
    print()


def main() -> None:
    chunk_size = 500
    overlap = 50

    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        suffix = input_path.suffix.lower()

        if suffix == ".pdf":
            document = load_pdf(input_path)
        elif suffix in (".txt", ".md"):
            document = load_text_file(input_path)
        else:
            print(f"不支持的文件类型: {suffix}，请使用 .pdf / .txt / .md")
            sys.exit(1)
    else:
        _print_separator("Demo 模式 — 使用内置示例文本（无需 PDF）")
        print("  提示: python -m rag.demo_pdf_chunk your.pdf  可指定真实 PDF")
        document = ExtractedDocument(
            source="员工手册_sample.txt",
            pages=[PageText(page=1, text=SAMPLE_TEXT.strip())],
            full_text=SAMPLE_TEXT.strip(),
        )
        _run_pipeline(document, chunk_size=chunk_size, overlap=overlap)
        return

    _run_pipeline(document, chunk_size=chunk_size, overlap=overlap)


if __name__ == "__main__":
    main()
