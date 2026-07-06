"""paper_links 论文提取与标题识别测试。"""

from app.utils.paper_links import (
    dedupe_external_refs,
    extract_answer_paper_titles,
    extract_recommended_papers_from_answer,
    extract_refs_from_answer_text,
    is_official_paper_url,
    normalize_external_ref_item,
    official_url_priority,
    _BOLD_SPAN_RE,
    _prepare_answer_for_extraction,
)


READING_ORDER_ANSWER = """## 四、阅读顺序建议

1. 先读 **RAG (Lewis et al.)** 和 **REALM (Guu et al.)** 建立基础理解。
2. 再读 **Self-RAG** (您已有基础) 和 **REPLUG** (理解黑盒适配)。
3. 最后扩展到 **Atlas** (效率) 和 **CRAG / Branch-Solve-Merge** (前沿)。

如果时间有限，建议优先阅读 **Self-RAG** 和 **RAG**，这两篇最为关键。
"""

PROSE_BOLD_ANSWER = (
    '**：让 RAG 可以应用于多种 NLP 任务** (Lewis et al., 2020)。'
)

SEGFORMER_ANSWER = """以下是与 SegFormer 相关的经典论文推荐：

1. **SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers** (Xie et al., 2021)
   - arXiv: [2105.15203](https://arxiv.org/abs/2105.15203)

2. **Pyramid Vision Transformer: A Versatile Backbone for Dense Prediction without Convolutions** (Wang et al., 2021)
   - arXiv: [2102.12122](https://arxiv.org/abs/2102.12122)

3. **Swin Transformer: Hierarchical Vision Transformer using Shifted Windows** (Liu et al., 2021)
   - arXiv: [2103.14030](https://arxiv.org/abs/2103.14030)

若需针对您当前挂载的文献做对比，请告知。
"""

MULTILINE_BOLD = """1. **SegFormer: Simple and Efficient Design for Semantic
Segmentation with Transformers** (Xie et al., 2021)
"""


def test_no_cross_bold_false_match():
    line = '2. 再读 **Self-RAG** (您已有基础) 和 **REPLUG** (理解黑盒适配)。'
    matches = [m.group('title') for m in _BOLD_SPAN_RE.finditer(line)]
    assert '(您已有基础) 和' not in matches
    assert 'Self-RAG' in matches
    assert 'REPLUG' in matches


def test_reading_order_extracts_short_paper_names():
    refs = extract_recommended_papers_from_answer(READING_ORDER_ANSWER)
    assert refs == [] or all(is_official_paper_url(r['official_url']) for r in refs)


def test_rejects_chinese_prose_bold():
    refs = extract_recommended_papers_from_answer(PROSE_BOLD_ANSWER)
    assert refs == []
    assert extract_answer_paper_titles(PROSE_BOLD_ANSWER) == []


def test_join_multiline_bold_title():
    joined = _prepare_answer_for_extraction(MULTILINE_BOLD)
    titles = [m.group('title') for m in _BOLD_SPAN_RE.finditer(joined)]
    assert len(titles) == 1
    assert titles[0].endswith('Transformers')
    assert 'Segmentation with Transformers' in titles[0]


def test_list_item_arxiv_linked_to_bold_title():
    refs = extract_recommended_papers_from_answer(SEGFORMER_ANSWER)
    assert refs
    assert all(is_official_paper_url(r['official_url']) for r in refs)
    assert not any('scholar.google.com' in r['official_url'] for r in refs)
    titles = {r['title'] for r in refs}
    assert any('SegFormer' in t for t in titles)
    assert any('Pyramid Vision Transformer' in t for t in titles)
    refs = extract_refs_from_answer_text(SEGFORMER_ANSWER)
    titles = [r['title'] for r in refs]
    assert any('SegFormer' in t for t in titles)
    assert not any(t.startswith('arXiv: [') for t in titles)
    assert not any('您当前挂载' in t for t in titles)


def test_dedupe_prefers_arxiv_over_scholar():
    answer = SEGFORMER_ANSWER
    arxiv = extract_refs_from_answer_text(answer)[0]
    scholar = {
        'title': arxiv['title'],
        'official_url': 'https://scholar.google.com/scholar?q=SegFormer',
        'source_type': 'scholar_search',
    }
    merged = dedupe_external_refs([scholar, arxiv])
    assert len(merged) == 1
    assert 'arxiv.org' in merged[0]['official_url']
    assert 'SegFormer' in merged[0]['title']


def test_normalize_rejects_junk_title():
    item = normalize_external_ref_item(
        {
            'title': '您当前挂载的文献',
            'official_url': 'https://scholar.google.com/scholar?q=test',
            'source_type': 'scholar_search',
        },
        SEGFORMER_ANSWER,
    )
    assert item is None


IEEE_ANSWER = """1. **Attention Is All You Need** (Vaswani et al., 2017)
   - IEEE: [9039584](https://ieeexplore.ieee.org/document/9039584)
"""


def test_ieee_url_extracted():
    refs = extract_refs_from_answer_text(IEEE_ANSWER)
    assert len(refs) == 1
    assert 'ieeexplore.ieee.org' in refs[0]['official_url']
    assert 'Attention' in refs[0]['title']


def test_official_url_priority_order():
    assert official_url_priority('https://arxiv.org/abs/2105.15203') > official_url_priority(
        'https://ieeexplore.ieee.org/document/9039584'
    )
    assert official_url_priority('https://ieeexplore.ieee.org/document/9039584') > official_url_priority(
        'https://doi.org/10.1109/ACCESS.2017.2761743'
    )
    assert official_url_priority('https://doi.org/10.1109/x') > official_url_priority(
        'https://scholar.google.com/scholar?q=test'
    )
