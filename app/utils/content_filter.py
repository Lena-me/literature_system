from __future__ import annotations

import re
from typing import Any

# ── 章节标题：整段跳过（前后置 matter） ──
BACK_MATTER_SECTION_KEYWORDS = {
    'references',
    'bibliography',
    'acknowledgement',
    'acknowledgements',
    'appendix',
    'appendices',
    '参考文献',
    '致谢',
    '附录',
    '后记',
}

NAV_SECTION_KEYWORDS = {
    'table of contents',
    'contents',
    'list of figures',
    'list of tables',
    '目录',
    '图目录',
    '表目录',
    '附表索引',
    '插图索引',
}

FRONT_MATTER_SECTION_KEYWORDS = {
    '独创性声明',
    '原创性声明',
    '学位论文原创性声明',
    '学位论文版权使用授权书',
    '关于学位论文使用授权的说明',
    '授权使用说明',
    'cover',
    'declaration',
    'copyright',
}

GLOBAL_BAD_SECTION_KEYWORDS = (
    BACK_MATTER_SECTION_KEYWORDS | NAV_SECTION_KEYWORDS | FRONT_MATTER_SECTION_KEYWORDS
)

_SKIP_ITEM_TYPES = {'page_header', 'page_footer', 'page_number'}

# ── 正文特征：行政/封面元数据（不依赖章节标题） ──
_ADMIN_TEXT_PATTERNS = (
    r'培养单位',
    r'培养\s*单位',
    r'指导教师',
    r'答辩日期',
    r'答辩委员会',
    r'答辩时间',
    r'专业名称',
    r'学位类别',
    r'研究方向',
    r'学校代码',
    r'中图分类号',
    r'分类号',
    r'UDC',
    r'密\s*级',
    r'学\s*号',
    r'作者姓名',
    r'授予学位单位',
    r'提交日期',
    r'送交日期',
    r'submitted in partial satisfaction',
    r'a thesis submitted',
    r'graduate school of',
    r'in partial fulfillment',
    r'supervisor',
    r'degree of master',
    r'degree of doctor',
    r'中国知网',
    r'cnki\.net',
    r'万方数据',
    r'国家图书馆',
)

_ADMIN_TEXT_RE = re.compile('|'.join(_ADMIN_TEXT_PATTERNS), re.I)
_TOC_LINE_RE = re.compile(r'(?:\.{3,}|\u2026{2,})\s*\d+\s*$')
_DUP_TITLE_WS_RE = re.compile(r'\s+')


def _normalize_title(text: str) -> str:
    return _DUP_TITLE_WS_RE.sub('', (text or '').strip().lower())


def _section_matches(section_title: str | None, keywords: set[str]) -> bool:
    section = (section_title or '').strip().lower()
    if not section:
        return False
    return any(keyword in section for keyword in keywords)


def is_bad_section_title(section_title: str | None) -> bool:
    """参考文献、目录、致谢等不适合科研阅读的章节。"""
    return _section_matches(section_title, GLOBAL_BAD_SECTION_KEYWORDS)


def is_back_matter_section(section_title: str | None) -> bool:
    return _section_matches(section_title, BACK_MATTER_SECTION_KEYWORDS)


def is_nav_section(section_title: str | None) -> bool:
    return _section_matches(section_title, NAV_SECTION_KEYWORDS)


def is_front_matter_section(section_title: str | None) -> bool:
    return _section_matches(section_title, FRONT_MATTER_SECTION_KEYWORDS)


def is_administrative_text(text: str) -> bool:
    """学位论文封面、答辩信息、CNKI 页脚等行政元数据。"""
    content = (text or '').strip()
    if not content:
        return False
    compact = content.replace(' ', '').replace('\n', '')
    if len(compact) < 220 and _ADMIN_TEXT_RE.search(content):
        return True
    if _TOC_LINE_RE.search(content):
        return True
    if re.match(r'^(目录|Contents?|图目录|表目录)$', content.strip(), re.I):
        return True
    return False


def is_duplicate_title(text: str, paper_title: str | None) -> bool:
    if not paper_title:
        return False
    a = _normalize_title(text)
    b = _normalize_title(paper_title)
    if not a or not b:
        return False
    return a == b or (len(a) > 20 and (a in b or b in a))


def is_likely_cover_image(item: dict[str, Any]) -> bool:
    """前几页的 logo / 校徽图（非正文图表）。"""
    item_type = item.get('item_type') or item.get('type') or ''
    content = (item.get('content') or '').strip()
    is_image = item_type in ('figure', 'image') or content.startswith('![](')
    if not is_image:
        return False
    order_index = item.get('order_index')
    page_number = item.get('page_number')
    if isinstance(order_index, int) and order_index < 15:
        return True
    if isinstance(page_number, int) and page_number <= 1:
        return True
    return False


def should_skip_content_item(
    item: dict[str, Any],
    *,
    current_section_title: str | None,
    paper_title: str | None,
    seen_titles: set[str],
) -> bool:
    item_type = item.get('item_type') or item.get('type') or ''
    if item_type in _SKIP_ITEM_TYPES:
        return True
    if is_bad_section_title(current_section_title):
        return True

    content = (item.get('content') or '').strip()
    if not content and item_type != 'heading':
        return True

    if item_type == 'heading':
        if is_bad_section_title(content):
            return True
        norm = _normalize_title(content)
        if is_duplicate_title(content, paper_title) and norm in seen_titles:
            return True
        return False

    if is_administrative_text(content):
        return True
    if is_likely_cover_image(item):
        return True
    if len(content) < 200 and is_duplicate_title(content, paper_title):
        norm = _normalize_title(content)
        if norm in seen_titles:
            return True
    return False


def filter_content_items_for_display(
    items: list[dict[str, Any]],
    *,
    paper_title: str | None = None,
) -> list[dict[str, Any]]:
    """过滤不适合科研阅读的 content_items，供前端 Markdown / 大纲展示。"""
    if not items:
        return []

    result: list[dict[str, Any]] = []
    current_section = ''
    seen_titles: set[str] = set()

    for item in items:
        item_type = item.get('item_type') or item.get('type') or ''
        content = (item.get('content') or '').strip()

        if item_type == 'heading':
            current_section = content[:200]
            if should_skip_content_item(
                item,
                current_section_title=current_section,
                paper_title=paper_title,
                seen_titles=seen_titles,
            ):
                continue
            seen_titles.add(_normalize_title(content))
            result.append(item)
            continue

        if should_skip_content_item(
            item,
            current_section_title=current_section,
            paper_title=paper_title,
            seen_titles=seen_titles,
        ):
            continue

        if len(content) < 200 and is_duplicate_title(content, paper_title):
            norm = _normalize_title(content)
            if norm in seen_titles:
                continue
            seen_titles.add(norm)

        result.append(item)

    return result
