from __future__ import annotations

import re

from app.utils.mineru_text import looks_like_mineru_json_blob, unwrap_mineru_json_text
from app.utils.content_filter import GLOBAL_BAD_SECTION_KEYWORDS, is_administrative_text, is_bad_section_title

__all__ = [
    'GLOBAL_BAD_SECTION_KEYWORDS',
    'is_bad_section_title',
    'is_compare_question',
    'is_low_quality_chunk',
    'is_overview_question',
    'normalize_chunk_text',
    'normalize_page_number',
    'strip_chunk_context_prefix',
]

_CONTEXT_PREFIX_LINE = re.compile(r'^\[(?:文献|核心方法)：[^\]]+\]\s*$')

# 单条参考文献条目（章节标题为空时也要识别）
_CN_REF_ENTRY = re.compile(
    r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\s*\].*?[JDCMPNR]\s*[\.。]',
)
_EN_REF_ENTRY = re.compile(
    r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\s*\].*?(?:et\s+al|Proceedings|Journal|Trans\.|IEEE|ACM|Springer|arXiv|doi:)',
    re.I,
)
_MINERU_FIGURE_JUNK = re.compile(r'Figure extracted by MinerU|!\[\]\([^)]+\)\s*$', re.I)


def strip_chunk_context_prefix(text: str) -> str:
    """去掉入库向量时附加的 [文献：…] / [核心方法：…] 前缀行。"""
    if not text:
        return text
    lines = text.split('\n')
    while lines and _CONTEXT_PREFIX_LINE.match(lines[0].strip()):
        lines.pop(0)
    return '\n'.join(lines).strip()


def looks_like_bibliography_entry(text: str) -> bool:
    content = strip_chunk_context_prefix(text or '').strip()
    if not content:
        return False
    if _CN_REF_ENTRY.search(content):
        return True
    if _EN_REF_ENTRY.search(content):
        return True
    lower = content.lower()
    if re.match(r'^\[\s*\d+\]', content) and (
        'proceedings' in lower or 'arxiv' in lower or 'doi:' in lower or 'vol.' in lower
    ):
        return True
    return False


def is_image_only_chunk(text: str) -> bool:
    content = strip_chunk_context_prefix(text or '').strip()
    if not content:
        return True
    if _MINERU_FIGURE_JUNK.search(content):
        return True
    if content.startswith('![](') and len(content) < 300:
        return True
    return False


def normalize_chunk_text(text: str) -> str:
    return unwrap_mineru_json_text(strip_chunk_context_prefix(text or '')).strip()


def is_figure_table_index(text: str) -> bool:
    content = normalize_chunk_text(text)
    if not content:
        return False
    if any(k in content for k in ('附表索引', '图目录', '表目录', 'List of Figures', 'List of Tables')):
        return True
    fig_refs = re.findall(r'图\s*\d+(?:\.\d+)*', content)
    tbl_refs = re.findall(r'表\s*\d+(?:\.\d+)*', content)
    if len(fig_refs) + len(tbl_refs) >= 3 and len(content) < 2000:
        prose = re.sub(r'[图表格\d\.\s]', '', content)
        if len(prose) < len(content) * 0.35:
            return True
    return False


def is_copyright_or_license(text: str) -> bool:
    content = normalize_chunk_text(text)
    lower = content.lower()
    markers = (
        'open-access',
        'creativecommons',
        'copyright',
        'all rights reserved',
        'this is an open-access article',
        '版权所有',
        '开放获取',
    )
    return any(m in lower for m in markers) or '©' in content


def is_toc_dot_line(text: str) -> bool:
    content = normalize_chunk_text(text)
    if re.search(r'(?:\.{4,}|\u2026{3,})\s*\d+\s*$', content):
        return True
    dot_ratio = content.count('.') / max(len(content), 1)
    return dot_ratio > 0.35 and len(content) < 500


def is_low_quality_chunk(
    text: str,
    section_title: str | None = None,
) -> bool:
    """判断文本块是否不适合作为问答证据（参考文献、目录、过短片段等）。"""
    content = normalize_chunk_text(text)
    lower = content.lower()

    if not content or len(content) < 80:
        return True
    if looks_like_mineru_json_blob(text or '') and len(content) < 120:
        return True
    if is_image_only_chunk(content):
        return True
    if looks_like_bibliography_entry(content):
        return True
    if is_bad_section_title(section_title):
        return True
    if is_administrative_text(content):
        return True
    if is_copyright_or_license(content):
        return True
    if is_figure_table_index(content):
        return True
    if is_toc_dot_line(content):
        return True
    if any(marker in lower[:300] for marker in ('references', 'bibliography', 'table of contents')):
        return True

    citation_count = len(re.findall(r'\[\d+\]', content))
    arxiv_count = lower.count('arxiv preprint')
    proceedings_count = lower.count('proceedings of')
    if citation_count >= 3 or arxiv_count >= 2 or proceedings_count >= 2:
        return True

    numbered_toc = len(re.findall(r'\b\d+(?:\.\d+)*\s+[A-Z][A-Za-z ]{3,}', content[:1000]))
    if numbered_toc >= 6:
        return True

    return False


def normalize_page_number(page_number: int | None) -> int | None:
    if page_number is None or page_number <= 0:
        return None
    return int(page_number)


def is_overview_question(question: str | None) -> bool:
    if not question:
        return False
    q = question.strip().lower()
    tokens = (
        '讲的什么',
        '讲的是什么',
        '讲什么',
        '主要内容',
        '主要讲',
        '概述',
        '总结',
        '这篇论文',
        '这篇文章',
        '这篇文献',
        '论文介绍',
        '简介',
        'what is this paper about',
        'summarize',
        'summary',
        'overview',
    )
    return any(token in q for token in tokens)


def is_compare_question(question: str | None) -> bool:
    if not question:
        return False
    q = question.strip().lower()
    tokens = (
        '比较',
        '对比',
        '异同',
        '区别',
        '相同',
        '不同',
        '两篇',
        '两篇论文',
        '这些论文',
        '这些文献',
        'compare',
        'contrast',
        'difference',
        'versus',
        ' vs ',
    )
    return any(token in q for token in tokens)
