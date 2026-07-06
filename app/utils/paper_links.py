from __future__ import annotations

import re
from urllib.parse import quote

_ARXIV_DOI_RE = re.compile(
    r'^10\.48550/arXiv\.(\d{4}\.\d{4,5}(?:v\d+)?)$',
    re.IGNORECASE,
)
_DOI_RE = re.compile(r'^10\.\d{4,9}/\S+$', re.IGNORECASE)
_ARXIV_ID_RE = re.compile(r'^(\d{4}\.\d{4,5}(?:v\d+)?)$')

_TEXT_DOI_RE = re.compile(
    r'(?:doi[:：\s]*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
    re.IGNORECASE,
)
_TEXT_ARXIV_RE = re.compile(
    r'(?:arxiv[:：\s]*|https?://arxiv\.org/abs/)(\d{4}\.\d{4,5}(?:v\d+)?)',
    re.IGNORECASE,
)
_TEXT_PMID_RE = re.compile(r'(?:PMID|pmid)[:：\s]*(\d{7,8})', re.I)
# 可点击的正式出版/索引链接（arXiv、DOI、IEEE、ACM、PubMed、Scopus、WoS 等）
_TEXT_OFFICIAL_URL_RE = re.compile(
    r'https?://(?:'
    r'arxiv\.org/abs/\d{4}\.\d{4,5}(?:v\d+)?'
    r'|(?:dx\.)?doi\.org/10\.\d{4,9}/[-._;()/:A-Z0-9]+'
    r'|ieeexplore\.ieee\.org/document/\d+'
    r'|dl\.acm\.org/doi/[^\s)\]>"]+'
    r'|pubmed\.ncbi\.nlm\.nih\.gov/\d+'
    r'|ncbi\.nlm\.nih\.gov/pubmed/\d+'
    r'|scopus\.com/[^\s)\]>"]+'
    r'|(?:apps\.)?webofscience\.com/[^\s)\]>"]+'
    r')',
    re.I,
)
_TEXT_URL_RE = _TEXT_OFFICIAL_URL_RE


def resolve_official_paper_url(doi: str | None) -> str | None:
    """根据 DOI 解析 arXiv / doi.org 等官方页面 URL。"""
    if not doi:
        return None
    raw = doi.strip().rstrip('.,;')
    if not raw:
        return None

    m = _ARXIV_DOI_RE.match(raw)
    if m:
        return f'https://arxiv.org/abs/{m.group(1)}'

    if _DOI_RE.match(raw):
        return f'https://doi.org/{raw}'

    m = _ARXIV_ID_RE.match(raw)
    if m:
        return f'https://arxiv.org/abs/{m.group(1)}'

    if raw.lower().startswith('arxiv:'):
        arxiv_id = raw.split(':', 1)[1].strip()
        if _ARXIV_ID_RE.match(arxiv_id):
            return f'https://arxiv.org/abs/{arxiv_id}'

    return None


def extract_doi_from_text(text: str | None) -> str | None:
    if not text:
        return None
    m = _TEXT_DOI_RE.search(text)
    if not m:
        m = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', text, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).rstrip('.,;')


def extract_arxiv_id_from_text(text: str | None) -> str | None:
    if not text:
        return None
    m = _TEXT_ARXIV_RE.search(text)
    if m:
        return m.group(1)
    doi = extract_doi_from_text(text)
    if doi:
        m = _ARXIV_DOI_RE.match(doi)
        if m:
            return m.group(1)
    return None


def extract_official_url_from_text(text: str | None) -> str | None:
    if not text:
        return None
    urls = _find_all_official_urls_in_text(text)
    best = _pick_best_official_url(urls)
    if best:
        return best
    arxiv_id = extract_arxiv_id_from_text(text)
    if arxiv_id:
        return f'https://arxiv.org/abs/{arxiv_id}'
    doi = extract_doi_from_text(text)
    return resolve_official_paper_url(doi)


def scholar_search_url(query: str) -> str:
    return f'https://scholar.google.com/scholar?q={quote(query.strip())}'


def is_official_paper_url(url: str | None) -> bool:
    """是否为 arXiv / DOI / IEEE / ACM / PubMed / Scopus / WoS 等正式链接。"""
    if not url:
        return False
    u = url.lower().strip()
    if 'scholar.google.com' in u:
        return False
    return bool(
        'arxiv.org' in u
        or 'doi.org' in u
        or 'ieeexplore.ieee.org' in u
        or 'dl.acm.org' in u
        or 'pubmed.ncbi.nlm.nih.gov' in u
        or 'ncbi.nlm.nih.gov/pubmed' in u
        or 'scopus.com' in u
        or 'webofscience.com' in u
    )


def official_url_priority(url: str | None) -> int:
    """数值越大越优先（用于多链接去重）。"""
    if not url:
        return 0
    u = url.lower()
    if 'arxiv.org' in u:
        return 100
    if 'ieeexplore.ieee.org' in u or 'dl.acm.org' in u:
        return 95
    if 'pubmed.ncbi.nlm.nih.gov' in u or 'ncbi.nlm.nih.gov/pubmed' in u:
        return 95
    if 'scopus.com' in u:
        return 90
    if 'webofscience.com' in u:
        return 90
    if 'doi.org' in u:
        return 80
    if 'scholar.google.com' in u:
        return 5
    return 50


def official_link_label(url: str | None) -> str:
    if not url:
        return '官网溯源'
    u = url.lower()
    if 'arxiv.org' in u:
        return '查看 arXiv'
    if 'doi.org' in u:
        return '查看 DOI'
    if 'ieeexplore.ieee.org' in u:
        return '查看 IEEE'
    if 'dl.acm.org' in u:
        return '查看 ACM'
    if 'pubmed.ncbi.nlm.nih.gov' in u or 'ncbi.nlm.nih.gov/pubmed' in u:
        return '查看 PubMed'
    if 'scopus.com' in u:
        return '查看 Scopus'
    if 'webofscience.com' in u:
        return '查看 WoS'
    if 'scholar.google.com' in u:
        return 'Scholar 检索'
    return '官网溯源'


def _find_all_official_urls_in_text(text: str | None) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for m in _TEXT_OFFICIAL_URL_RE.finditer(text):
        clean = m.group(0).rstrip('.,;')
        if clean not in seen:
            seen.add(clean)
            urls.append(clean)
    for m in _TEXT_PMID_RE.finditer(text):
        url = f'https://pubmed.ncbi.nlm.nih.gov/{m.group(1)}/'
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _pick_best_official_url(urls: list[str]) -> str | None:
    if not urls:
        return None
    return max(urls, key=official_url_priority)


_MAX_TITLE_LEN = 512
_JUNK_REF_TITLE_RE = re.compile(
    r'^(arxiv|doi|http|www\.|您当前|当前挂载|挂载的文献|文献库|参见|如上|以下|说明|若需)[^\w]*$',
    re.I,
)

_CITATION_ONLY_RE = re.compile(
    r'^[A-Z][A-Za-z\-]+(?:\s+(?:et al\.?|&|and)\b)?,\s*\d{4}\.?\s*$'
    r'|^[A-Z][A-Za-z\-]+\s*&\s*[A-Z][A-Za-z\-]+,\s*\d{4}\.?\s*$',
    re.I,
)
_LIST_LINE_RE = re.compile(r'(?m)^\s*(?:\d+[.)]|[-*•])\s+(?P<body>.+?)\s*$')
_YEAR_IN_CITATION_RE = re.compile(r'\b(19|20)\d{2}\b')
_AUTHOR_YEAR_IN_PARENS_RE = re.compile(
    r'[（(][^）)]*(?:et al\.?|&|and\b|等人)[^）)]*,?\s*\d{4}[^）)]*[）)]'
    r'|[（(][^）)]*\d{4}[^）)]*[）)]',
    re.I,
)
_AUTHOR_YEAR_ITALIC_RE = re.compile(
    r'\*[^*\n]*(?:et al\.?|&|and\b|等人)[^*\n]*,?\s*\d{4}[^*\n]*\*'
    r'|\*[^*\n]*(?:NeurIPS|ICML|ICLR|ACL|EMNLP|NAACL|CVPR|AAAI|COLING|KDD|WWW|SIGIR)[^*\n]*\*',
    re.I,
)
_PROSE_START_RE = re.compile(
    r'^(提出|是|在|通过|采用|基于|用于|可以|能够|这种|如果|由于|作为|其中|该|此|其|也|还|而|但|让|使|为|与|和|对|从|由|以|将|会|已|被|把|给|向|这|那|它|它们|上述|以下|如下|首先|其次|最后|推荐|建议)',
)
_GENERIC_TITLE_RE = re.compile(r'^(论文|文献|方法|模型|工作|研究|综述|paper|survey)$', re.I)
_INTERNAL_CITATION_TAIL_RE = re.compile(r'\[\d+\]\s*$')
# 开头 ** 不能紧跟字母/数字（避免把 **TitleA** 的闭合 ** 误当作新加粗起点）
_BOLD_SPAN_RE = re.compile(
    rf'(?<![*\w])\*\*["\u201c]?(?P<title>[^*"\n\u201c\u201d]{{3,{_MAX_TITLE_LEN}}})["\u201d]?\*\*(?!\*)',
)
_INVALID_BOLD_TITLE_RE = re.compile(
    r'^[\s(（：:，,、和与及]|和\s*$|^\(您已有',
)
_SHORT_EN_PAPER_RE = re.compile(
    r'^[A-Z][A-Za-z0-9\-/\.]{1,}(?:\s*[(/][^）)]*(?:et al\.?|&|and\b)?[^）)]*[）)])?$',
)
_AUTHOR_IN_PARENS_RE = re.compile(
    r'[（(][^）)]*(?:et al\.?|&|and\b|等人)[^）)]*[）)]',
    re.I,
)
_INLINE_BOLD_PAPER_RE = re.compile(
    rf'(?<![*\w])\*\*(?P<title>[^*\n]{{3,{_MAX_TITLE_LEN}}})\*\*\s*[（(](?P<cite>[^）)\n]{{4,80}})[）)]',
)
_INLINE_BOLD_TITLE_ONLY_RE = _BOLD_SPAN_RE
_INLINE_EN_PAPER_RE = re.compile(
    rf'(?P<title>[A-Z][A-Za-z0-9:,\-–—][A-Za-z0-9:,\-–— ]{{9,{_MAX_TITLE_LEN - 1}}}?)'
    r'\s*[（(](?P<cite>[^）)\n]*(?:et al\.?|&|and\b)[^）)\n]*,\s*\d{4}[^）)\n]*)[）)]',
)
# 参考文献行中常见标题词（非作者名）
_BIB_TITLE_WORDS = frozenset({
    'Tasks', 'Models', 'Learning', 'Generation', 'Retrieval', 'Training',
    'Processing', 'Language', 'Organized', 'Tree', 'Intensive', 'Augmented',
    'Knowledge', 'Few', 'Shot', 'Recursive', 'Abstractive', 'Pre', 'Real',
    'World', 'Large', 'Scale', 'Neural', 'Machine', 'Deep', 'Natural',
})


def _is_probable_author_token(word: str) -> bool:
    w = (word or '').strip().strip(',')
    if not w or w in _BIB_TITLE_WORDS:
        return False
    if w.isupper() and len(w) <= 5:
        return False
    return bool(re.match(r'^[A-Z][a-z\-]+$', w))


def _split_title_from_author_block(line: str) -> str | None:
    """在「First Last」序列中定位作者块起点（排除标题词误判）。"""
    tokens = line.split()
    author_starts: list[int] = []
    i = 0
    while i < len(tokens) - 1:
        if _is_probable_author_token(tokens[i]) and _is_probable_author_token(tokens[i + 1]):
            author_starts.append(i)
            i += 2
        else:
            i += 1
    if len(author_starts) >= 2:
        head = ' '.join(tokens[:author_starts[0]]).strip(' .,;:-"')
        if len(head) >= 10:
            return head
    return None


def _is_citation_only(text: str) -> bool:
    """判断是否为「作者 et al., 年份」式短引用，而非论文标题。"""
    t = re.sub(r'\*+', '', (text or '').strip()).rstrip('.')
    if not t:
        return True
    if _CITATION_ONLY_RE.match(t):
        return True
    if re.search(r'\bet al\.?\b', t, re.I) and _YEAR_IN_CITATION_RE.search(t) and len(t) < 48:
        return True
    return False


def _strip_inline_markdown(text: str) -> str:
    s = (text or '').strip()
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'__(.+?)__', r'\1', s)
    s = re.sub(r'`([^`]+)`', r'\1', s)
    s = re.sub(r'\*+', '', s)
    s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)
    return s.strip()


def _join_split_bold_spans(text: str) -> str:
    """合并被换行拆开的 **Title\\n continues**。"""
    if not text:
        return text
    prev = None
    out = text
    while prev != out:
        prev = out
        out = re.sub(
            rf'(\*\*(?:(?!\*\*)[^*]){{3,{_MAX_TITLE_LEN}}})\n(?=[^*\n])',
            r'\1 ',
            out,
        )
    return out


def _prepare_answer_for_extraction(answer: str) -> str:
    return _join_split_bold_spans(answer or '')


def _sanitize_display_title(title: str) -> str:
    t = _strip_inline_markdown(title or '')
    t = re.sub(r'^\*+|\*+$', '', t).strip()
    return re.sub(r'\s+', ' ', t).strip()


def _is_junk_ref_title(title: str) -> bool:
    t = _sanitize_display_title(title)
    if not t or len(t) < 4:
        return True
    if _JUNK_REF_TITLE_RE.match(t):
        return True
    if re.match(r'^arXiv\s*[:\[]', t, re.I):
        return True
    if re.match(r'^[\[\(]', t):
        return True
    if t.lower() in {'arxiv', 'doi', 'pvt', 'vit', 'nlp', 'cv', 'ai'}:
        return True
    if re.search(r'您当前|挂载的文献|请告知', t):
        return True
    if t.startswith('**') or t.endswith('**'):
        return True
    return False


def _find_bold_title_before(text: str, index: int) -> str | None:
    window = text[max(0, index - 900): index]
    best: str | None = None
    for m in _BOLD_SPAN_RE.finditer(window):
        title = _sanitize_display_title(m.group('title'))
        if title and not _is_junk_ref_title(title) and _looks_like_paper_title(title, m.group(0)):
            best = title
    return best


def _ref_priority(item: dict) -> int:
    url = item.get('official_url') or ''
    base = official_url_priority(url)
    if base >= 80:
        return base // 20
    source = item.get('source_type') or ''
    if source == 'answer_text':
        return 3
    if source in ('reference_bibliography', 'library_recommendation'):
        return 2
    return 1


def dedupe_external_refs(refs: list[dict]) -> list[dict]:
    """按论文标题去重，保留 arXiv/DOI 优于 Scholar 的条目。"""
    by_title: dict[str, dict] = {}
    order: list[str] = []

    for item in refs:
        title = _sanitize_display_title(item.get('title') or '')
        if _is_junk_ref_title(title):
            continue
        cleaned = {**item, 'title': title}
        norm = re.sub(r'\s+', ' ', title.lower())
        if norm in by_title:
            if _ref_priority(cleaned) > _ref_priority(by_title[norm]):
                by_title[norm] = cleaned
            continue
        by_title[norm] = cleaned
        order.append(norm)

    return [by_title[k] for k in order]


def _has_author_year_citation(text: str) -> bool:
    t = text or ''
    if _AUTHOR_YEAR_IN_PARENS_RE.search(t):
        return True
    if _AUTHOR_YEAR_ITALIC_RE.search(t):
        return True
    return bool(re.search(r'\*[^*\n]*,\s*\d{4}[^*\n]*\*', t))


def _has_scholar_citation_signal(text: str) -> bool:
    """有作者-年份、或 (Author et al.) / 标题内嵌作者，即可生成 Scholar 兜底。"""
    t = text or ''
    if _has_author_year_citation(t):
        return True
    if _AUTHOR_IN_PARENS_RE.search(t):
        return True
    return bool(re.search(r'\([^)]*(?:et al\.?|&|and\b)[^)]*\)', t, re.I))


def _is_valid_bold_title_text(title: str) -> bool:
    t = (title or '').strip()
    if len(t) < 3 or _INVALID_BOLD_TITLE_RE.match(t):
        return False
    if re.match(r'^[：:]', t):
        return False
    return True


def _looks_like_paper_title(title: str, full_line: str = '') -> bool:
    """过滤说明性 bullet / 句子片段，只保留像论文标题的文本。"""
    t = _strip_inline_markdown(title).strip().rstrip('，,;:：')
    if not t or len(t) < 3:
        return False
    if _GENERIC_TITLE_RE.match(t):
        return False
    if _is_citation_only(t):
        return False
    if _PROSE_START_RE.match(t):
        return False
    if re.match(r'^[：:]', t):
        return False
    if _INTERNAL_CITATION_TAIL_RE.search(t):
        return False
    if t.endswith('，') or t.endswith(','):
        return False

    line = full_line or t
    if extract_official_url_from_text(line):
        return True
    if _has_scholar_citation_signal(line):
        return True

    en_words = re.findall(r'[A-Za-z]{3,}', t)
    if len(en_words) >= 3 and (':' in t or '-' in t or len(en_words) >= 4):
        return True

    # 短英文论文名/缩写：RAG、Self-RAG、REPLUG、Atlas、REALM 等
    if len(t) < 12 and _SHORT_EN_PAPER_RE.match(t):
        return True

    # 中文标题（书名/论文名）通常较短且不以动词开头；长中文句多为说明
    cn_count = len(re.findall(r'[\u4e00-\u9fff]', t))
    en_count = len(re.findall(r'[A-Za-z]', t))
    if cn_count >= 8 and en_count < 4:
        if '。' in t or '，' in t or '；' in t:
            return False
        if cn_count > 24:
            return False
        if '：' in t or ':' in t:
            return False

    if line.strip().startswith('**') and not _is_citation_only(t) and en_count >= 2:
        return True

    return False


def _parse_recommendation_line(body: str) -> tuple[str, str]:
    """从列表行解析 (论文标题, 行内剩余说明/引用)。仅在有明确论文信号时返回。"""
    raw = body.strip()
    if not raw:
        return '', ''

    # **Title** (Author, Year) 或 **Title** — 说明
    m = re.match(r'^\*\*(.+?)\*\*(?:\s*(.*))?$', raw, re.S)
    if m:
        title = m.group(1).strip()
        rest = (m.group(2) or '').strip()
        if _looks_like_paper_title(title, raw):
            return title, rest

    plain = _strip_inline_markdown(raw)

    # Title (Author et al., Year)
    m = re.match(r'^(.+?)\s*[（(]([^）)]+)[）)]\s*(.*)$', plain)
    if m:
        title = m.group(1).strip().strip('—-–: ')
        citation = m.group(2).strip()
        if _has_author_year_citation(f'({citation})') and _looks_like_paper_title(title, raw):
            return title, citation

    # Title — 说明（左侧必须是论文型标题，不能是说明句）
    m = re.match(r'^(.+?)\s*[—\-–]\s*(.+)$', plain)
    if m:
        title = m.group(1).strip()
        if _looks_like_paper_title(title, raw):
            return title, m.group(2).strip()

    return '', ''


def _bold_spans_in_text(text: str) -> list[tuple[str, str, str]]:
    """从文本中提取有效加粗论文名：(title, snippet, body)。"""
    results: list[tuple[str, str, str]] = []
    for m in _BOLD_SPAN_RE.finditer(text):
        title = _normalize_quotes(m.group('title'))
        if not _is_valid_bold_title_text(title):
            continue
        before = text[max(0, m.start() - 80): m.start()]
        window = text[m.end(): m.end() + 200]
        snippet = f'{before}{m.group(0)}{window}'.strip()
        body = f'{m.group(0)}\n{before}{window}'
        results.append((title, snippet, body))
    return results


def _is_recognizable_english_paper_name(title: str) -> bool:
    """短缩写或典型英文论文名，无引用上下文也可生成 Scholar 链接。"""
    t = _strip_inline_markdown(title).strip()
    if not t:
        return False
    if _SHORT_EN_PAPER_RE.match(t):
        return True
    en_words = re.findall(r'[A-Za-z]{3,}', t)
    return len(en_words) >= 2 and ('-' in t or '/' in t or ':' in t)


def _match_context(answer: str, start: int, end: int, *, before: int = 80, after: int = 500) -> str:
    return answer[max(0, start - before): min(len(answer), end + after)]


def _list_item_start(answer: str, pos: int) -> int:
    """定位 pos 所在编号列表项的起点（支持 `  2. **` 同行续写格式）。"""
    chunk = answer[:pos]
    matches = list(re.finditer(r'(?:^|\n|\s{2,})(\d+[.)]\s)', chunk))
    if matches:
        return matches[-1].start()
    return answer.rfind('\n', 0, pos) + 1


def _expand_list_context(answer: str, start: int, end: int) -> str:
    """列表项上下文：从当前编号项起，延伸到子行（arXiv/IEEE 等），直到下一条编号。"""
    line_start = _list_item_start(answer, start)
    ext_end = min(len(answer), end + 700)
    tail = answer[end:ext_end]
    next_item = re.search(r'(?:\n\s*|\s{2,})\d+[.)]\s', tail)
    if next_item:
        ext_end = end + next_item.start()
    return answer[line_start:ext_end]


def _find_best_official_url_in_context(body: str) -> tuple[str | None, str | None]:
    """从上下文中取最合适的官方链接（arXiv / IEEE / ACM / PubMed / Scopus / WoS / DOI）。"""
    if not body:
        return None, None

    urls = _find_all_official_urls_in_text(body)
    if urls:
        # 同一 block 内取最靠后的链接（对应该条目子行），同位置再比优先级
        best = max(urls, key=lambda u: (body.rfind(u), official_url_priority(u)))
        doi = extract_doi_from_text(body) or extract_doi_from_text(best or '')
        if best and 'arxiv.org' in best.lower():
            arxiv_m = re.search(r'/abs/(\d{4}\.\d{4,5}(?:v\d+)?)', best, re.I)
            if arxiv_m and not doi:
                doi = f'10.48550/arXiv.{arxiv_m.group(1)}'
        return best, doi

    doi = extract_doi_from_text(body)
    url = resolve_official_paper_url(doi)
    if url:
        return url, doi

    return None, doi


def _collect_paper_candidate(
    refs: list[dict],
    seen_urls: set[str],
    seen_titles: set[str],
    *,
    title: str,
    snippet: str,
    body: str,
    limit: int,
) -> None:
    if len(refs) >= limit or not _looks_like_paper_title(title, body):
        return

    doi = extract_doi_from_text(body)
    official_url, doi = _find_best_official_url_in_context(body)
    if not official_url:
        official_url = resolve_official_paper_url(doi)
    norm = re.sub(r'\s+', ' ', title.lower().strip())

    if official_url:
        if official_url in seen_urls or norm in seen_titles:
            return
        seen_urls.add(official_url)
        seen_titles.add(norm)
        refs.append({
            'title': _sanitize_display_title(title),
            'snippet': snippet[:240],
            'doi': doi,
            'official_url': official_url,
            'source_type': 'answer_text',
            'paper_id': None,
        })
        return

    # 无正式直链时不生成 Scholar
    return


def extract_recommended_papers_from_answer(answer: str, *, limit: int = 12) -> list[dict]:
    """从推荐类回答提取论文：仅识别带标题/作者年份/DOI 的条目，忽略说明性 bullet。"""
    answer = _prepare_answer_for_extraction(answer)
    if not answer:
        return []

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    refs: list[dict] = []

    # 1) 全文 inline：**Title** (Author, Year)
    for m in _INLINE_BOLD_PAPER_RE.finditer(answer):
        title = m.group('title').strip()
        cite = m.group('cite').strip()
        body = _expand_list_context(answer, m.start(), m.end())
        _collect_paper_candidate(
            refs, seen_urls, seen_titles,
            title=title, snippet=body, body=body, limit=limit,
        )

    # 2) 全文 inline：English Title (Author et al., Year)
    for m in _INLINE_EN_PAPER_RE.finditer(answer):
        title = m.group('title').strip().strip('—-–: ')
        cite = m.group('cite').strip()
        body = _expand_list_context(answer, m.start(), m.end())
        _collect_paper_candidate(
            refs, seen_urls, seen_titles,
            title=title, snippet=body, body=body, limit=limit,
        )

    # 2b) **Title** 加粗论文名（含列表行内多个 **Title**）
    for m in _INLINE_BOLD_TITLE_ONLY_RE.finditer(answer):
        title = _normalize_quotes(m.group('title'))
        if not _is_valid_bold_title_text(title):
            continue
        if any(re.sub(r'\s+', ' ', title.lower()) == t for t in seen_titles):
            continue
        body = _expand_list_context(answer, m.start(), m.end())
        _collect_paper_candidate(
            refs, seen_urls, seen_titles,
            title=title, snippet=body.strip(), body=body, limit=limit,
        )

    # 3) 列表行：提取行内全部 **Title**，并保留行首 **Title** 解析
    for m in _LIST_LINE_RE.finditer(answer):
        body = m.group('body').strip()
        if not body:
            continue
        block = _expand_list_context(answer, m.start(), m.end())
        seen_in_line: set[str] = set()
        for title, snippet, _ctx_body in _bold_spans_in_text(body):
            norm = re.sub(r'\s+', ' ', title.lower())
            if norm in seen_in_line:
                continue
            seen_in_line.add(norm)
            _collect_paper_candidate(
                refs, seen_urls, seen_titles,
                title=title, snippet=snippet, body=block, limit=limit,
            )
        title, rest = _parse_recommendation_line(body)
        if not title:
            continue
        norm = re.sub(r'\s+', ' ', title.lower())
        if norm in seen_in_line:
            continue
        _collect_paper_candidate(
            refs, seen_urls, seen_titles,
            title=title, snippet=block, body=block, limit=limit,
        )

    return refs[:limit]


def _normalize_quotes(text: str) -> str:
    return (text or '').strip().strip('"\'""''')


def extract_answer_paper_titles(answer: str) -> list[str]:
    """从回答 Markdown 中提取 AI 给出的论文标题（**加粗** / 引号）。"""
    answer = _prepare_answer_for_extraction(answer)
    if not answer:
        return []

    seen: set[str] = set()
    titles: list[str] = []

    def add(raw: str, context: str) -> None:
        t = _normalize_quotes(_strip_inline_markdown(raw))
        if not t or not _looks_like_paper_title(t, context):
            return
        norm = re.sub(r'\s+', ' ', t.lower())
        if norm in seen:
            return
        seen.add(norm)
        titles.append(t)

    for m in _INLINE_BOLD_TITLE_ONLY_RE.finditer(answer):
        if _is_valid_bold_title_text(m.group('title')):
            add(m.group('title'), m.group(0))

    for m in _INLINE_BOLD_PAPER_RE.finditer(answer):
        add(m.group('title'), m.group(0))

    for m in _INLINE_EN_PAPER_RE.finditer(answer):
        add(m.group('title'), m.group(0))

    return titles


def title_referenced_in_answer(clean_title: str, answer: str, answer_titles: list[str] | None = None) -> bool:
    """判断论文标题是否在回答中被明确提及（对齐 **加粗标题**，避免参考文献脏文本误匹配）。"""
    ct = re.sub(r'\s+', ' ', (clean_title or '').lower().strip())
    if len(ct) < 3:
        return False

    candidates = answer_titles or extract_answer_paper_titles(answer)
    for at in candidates:
        an = re.sub(r'\s+', ' ', at.lower().strip())
        if ct == an or ct in an or an in ct:
            return True
        if len(ct) >= 16 and len(an) >= 16 and ct[:36] == an[:36]:
            return True

    return False


def best_display_title(clean_title: str, answer_titles: list[str]) -> str:
    """优先使用回答中的完整加粗标题作为展示名。"""
    base = _sanitize_display_title(clean_title)
    if not answer_titles:
        return base
    ct = re.sub(r'\s+', ' ', base.lower().strip())
    best = base
    best_len = len(base)
    for at in answer_titles:
        display = _sanitize_display_title(at)
        an = re.sub(r'\s+', ' ', display.lower().strip())
        if not an:
            continue
        if ct == an or ct in an or an in ct:
            if len(display) >= best_len:
                best = display
                best_len = len(display)
        elif len(ct) >= 16 and len(an) >= 16 and ct[:36] == an[:36]:
            if len(display) >= best_len:
                best = display
                best_len = len(display)
    return best


def looks_like_dirty_bibliography_title(title: str) -> bool:
    """判断 title 是否像未清洗的参考文献行（作者名拼接 / 160 字截断）。"""
    t = (title or '').strip()
    if not t:
        return False
    if len(t) == 160 and t[-1].isalpha() and ' ' in t:
        return True
    clean = clean_title_from_reference(t)
    if clean != t and len(clean) < len(t) * 0.75:
        return True
    if re.search(r'\barXiv:\S+|\bdoi:\S+', t, re.I):
        return True
    # 标题后连续出现 2+ 个「名 姓」对（典型参考文献作者列表）
    if len(re.findall(r'[A-Z][a-z]+\s+[A-Z][a-z\-]+', t)) >= 3:
        return True
    return False


def normalize_external_ref_item(
    item: dict,
    answer: str,
    answer_titles: list[str] | None = None,
) -> dict | None:
    """入库/出参前统一清洗标题，并丢弃与回答无关的参考文献拓展。"""
    if not item or not item.get('official_url'):
        return None

    prepared = _prepare_answer_for_extraction(answer)
    titles = answer_titles if answer_titles is not None else extract_answer_paper_titles(prepared)
    source_type = item.get('source_type') or ''
    raw_title = _sanitize_display_title(item.get('title') or '')
    snippet = (item.get('snippet') or raw_title or '').strip()

    if _is_junk_ref_title(raw_title):
        if source_type == 'answer_text':
            nearby = _find_bold_title_before(prepared, prepared.find(snippet[:40]) if snippet else 0)
            if nearby:
                raw_title = nearby
            else:
                return None
        else:
            return None

    if source_type == 'reference_bibliography':
        clean = clean_title_from_reference(snippet or raw_title)
        if not title_referenced_in_answer(clean, prepared, titles):
            return None
        display = best_display_title(clean, titles)
        return {**item, 'title': display, 'snippet': snippet[:500] if snippet else item.get('snippet')}

    if source_type == 'library_recommendation':
        lib_title = raw_title
        if not title_referenced_in_answer(lib_title, prepared, titles):
            return None
        return {**item, 'title': best_display_title(lib_title, titles)}

    if looks_like_dirty_bibliography_title(raw_title):
        clean = clean_title_from_reference(snippet or raw_title)
        return {**item, 'title': best_display_title(clean, titles)}

    if raw_title and _looks_like_paper_title(raw_title, snippet or raw_title):
        return {**item, 'title': best_display_title(raw_title, titles)}

    return None


def clean_title_from_reference(content: str) -> str:
    """从参考文献原始行解析论文标题（去掉作者、arxiv、年份等）。"""
    line = (content or '').strip().split('\n', 1)[0]
    line = re.sub(r'^\[\s*\d+\s*\]\s*', '', line)
    line = re.sub(r'^\d+\.\s*', '', line).strip()

    # 去掉 arXiv / DOI 及之后内容
    line = re.split(r'\barXiv:\S+|\bdoi:\S+|https?://', line, maxsplit=1, flags=re.I)[0].strip()
    # 去掉末尾年份 + venue
    line = re.sub(
        r'\s+\d{4}\s*(?:arXiv preprint|preprint|NeurIPS|ICML|ICLR|ACL|EMNLP|NAACL|CVPR|AAAI|COLING|KDD).*?$',
        '',
        line,
        flags=re.I,
    ).strip(' .,;:')

    head = _split_title_from_author_block(line)
    if head:
        return head

    m = re.match(
        r'^(.+?)\s+(?=(?:[A-Z][a-z\-]+\s+[A-Z][A-Za-z\-]+(?:\s+[A-Z][a-z\-]+)?\s*){2,})',
        line,
    )
    if m:
        title = m.group(1).strip(' .,;:-"')
        if len(title) >= 10:
            return title

    # 标题在句号/问号前（部分格式）
    if '. ' in line and line.index('. ') < 120:
        head = line.split('. ', 1)[0].strip()
        if len(head) >= 10 and not re.search(r'\barXiv\b', head, re.I):
            return head

    return line.strip(' .,;:-"') or '外部文献'


def _guess_title_from_reference(content: str) -> str:
    return clean_title_from_reference(content)


def extract_refs_from_answer_text(answer: str, *, limit: int = 8) -> list[dict]:
    """从回答正文中提取 arXiv / DOI / IEEE / ACM / PubMed / Scopus / WoS 等官方 URL。"""
    answer = _prepare_answer_for_extraction(answer)
    if not answer:
        return []

    seen: set[str] = set()
    refs: list[dict] = []

    def add_ref(*, title: str, snippet: str, doi: str | None, official_url: str | None, source_type: str, pos: int = 0):
        if not official_url or not is_official_paper_url(official_url) or official_url in seen:
            return
        display = _sanitize_display_title(title)
        if _is_junk_ref_title(display):
            nearby = _find_bold_title_before(answer, pos)
            display = nearby or display
        if _is_junk_ref_title(display):
            return
        seen.add(official_url)
        refs.append({
            'title': display,
            'snippet': snippet[:240],
            'doi': doi,
            'official_url': official_url,
            'source_type': source_type,
            'paper_id': None,
        })

    def _doi_for_url(url: str, context: str) -> str | None:
        doi = extract_doi_from_text(context) or extract_doi_from_text(url)
        if doi:
            return doi
        if 'arxiv.org' in url.lower():
            arxiv_m = re.search(r'/abs/(\d{4}\.\d{4,5}(?:v\d+)?)', url, re.I)
            if arxiv_m:
                return f'10.48550/arXiv.{arxiv_m.group(1)}'
        return None

    for m in _TEXT_OFFICIAL_URL_RE.finditer(answer):
        clean = m.group(0).rstrip('.,;')
        pos = m.start()
        snippet = answer[max(0, pos - 120): pos + len(clean) + 80]
        nearby = _find_bold_title_before(answer, pos)
        doi = _doi_for_url(clean, snippet)
        title = nearby or doi or clean
        add_ref(
            title=title,
            snippet=snippet,
            doi=doi,
            official_url=clean,
            source_type='answer_text',
            pos=pos,
        )
        if len(refs) >= limit:
            return refs

    for m in _TEXT_PMID_RE.finditer(answer):
        pos = m.start()
        url = f'https://pubmed.ncbi.nlm.nih.gov/{m.group(1)}/'
        if url in seen:
            continue
        nearby = _find_bold_title_before(answer, pos)
        add_ref(
            title=nearby or f'PMID:{m.group(1)}',
            snippet=m.group(0),
            doi=None,
            official_url=url,
            source_type='answer_text',
            pos=pos,
        )
        if len(refs) >= limit:
            return refs

    for m in _TEXT_ARXIV_RE.finditer(answer):
        arxiv_id = m.group(1)
        pos = m.start()
        url = f'https://arxiv.org/abs/{arxiv_id}'
        if url in seen:
            continue
        nearby = _find_bold_title_before(answer, pos)
        add_ref(
            title=nearby or f'arXiv:{arxiv_id}',
            snippet=m.group(0),
            doi=f'10.48550/arXiv.{arxiv_id}',
            official_url=url,
            source_type='answer_text',
            pos=pos,
        )
        if len(refs) >= limit:
            return refs

    for m in re.finditer(r'(?<![\w/.])(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', answer, re.I):
        doi = m.group(1).rstrip('.,;')
        pos = m.start()
        url = resolve_official_paper_url(doi)
        if url and url not in seen:
            nearby = _find_bold_title_before(answer, pos)
            add_ref(title=nearby or doi, snippet=doi, doi=doi, official_url=url, source_type='answer_text', pos=pos)
        if len(refs) >= limit:
            break

    return refs
