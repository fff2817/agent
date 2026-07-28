"""引用对齐 — 解析回答中的 [n] 标记并与检索来源匹配。"""

from __future__ import annotations

import re

from rag.types import SearchResult

from eval.types import CitationEvaluation, CitationItem

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def extract_cited_ranks(answer: str) -> list[int]:
    seen: set[int] = set()
    ranks: list[int] = []
    for match in CITATION_PATTERN.finditer(answer):
        rank = int(match.group(1))
        if rank not in seen:
            seen.add(rank)
            ranks.append(rank)
    return ranks


def _word_overlap(a: str, b: str) -> float:
    words_a = {w for w in re.findall(r"[\u4e00-\u9fff\w]{2,}", a.lower())}
    words_b = {w for w in re.findall(r"[\u4e00-\u9fff\w]{2,}", b.lower())}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))


def infer_cited_ranks_from_content(answer: str, sources: list[SearchResult]) -> list[int]:
    """无 [n] 标记时，用内容重叠推断可能引用的来源。"""
    if not answer.strip() or not sources:
        return []

    sentences = [s.strip() for s in re.split(r"[。！？.!?]\s*", answer) if s.strip()]
    if not sentences:
        sentences = [answer.strip()]

    cited: list[int] = []
    for source in sources:
        best = max(_word_overlap(sentence, source.chunk.text) for sentence in sentences)
        if best >= 0.15:
            cited.append(source.rank)
    return cited


def evaluate_citations(answer: str, sources: list[SearchResult]) -> CitationEvaluation:
    explicit = extract_cited_ranks(answer)
    cited_ranks = explicit or infer_cited_ranks_from_content(answer, sources)
    cited_set = set(cited_ranks)

    items: list[CitationItem] = []
    for source in sources:
        items.append(
            CitationItem(
                rank=source.rank,
                cited=source.rank in cited_set,
                source=source.chunk.source,
                page=source.chunk.page,
                excerpt=source.chunk.text[:160],
            )
        )

    coverage = len(cited_set) / len(sources) if sources else 0.0
    return CitationEvaluation(
        cited_source_ranks=sorted(cited_set),
        items=items,
        citation_coverage=round(coverage, 4),
    )
