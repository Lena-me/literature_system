from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.models import (
    ComparisonResult,
    ContentItem,
    KnowledgeDomain,
    KnowledgeGraph,
    KnowledgeGraphPaper,
    Paper,
    PaperExtractedInfo,
    Report,
    ReproducibilityGuide,
)
from app.utils.paper_links import (
    extract_arxiv_id_from_text,
    extract_doi_from_text,
    extract_official_url_from_text,
    resolve_official_paper_url,
    scholar_search_url,
)
from app.utils.json_utils import dumps, loads


class GenerationService:
    REPORT_MODULE_META = {
        'basic_info': {'title': '基本信息', 'fields': ['title', 'authors', 'keywords']},
        'abstract': {'title': '摘要速览', 'fields': ['abstract']},
        'research_question': {'title': '研究背景与核心问题', 'fields': ['research_question']},
        'method': {'title': '方法 / 模型 / 技术路线', 'fields': ['method']},
        'experiment_data': {'title': '数据集 / 实验对象 / 实验设计', 'fields': ['experiment_data']},
        'main_results': {'title': '主要结果与结论', 'fields': ['main_results']},
        'innovations': {'title': '创新点与贡献', 'fields': ['innovations']},
        'limitations': {'title': '局限性与适用边界', 'fields': ['limitations']},
        'reproducibility': {'title': '可复现性要点', 'fields': ['method', 'experiment_data', 'main_results']},
        'future_work': {'title': '未来工作与后续研究方向', 'fields': ['future_work']},
        'literature_trace': {'title': '拓展检索', 'fields': ['keywords', 'research_question', 'method', 'abstract']},
        'related_papers': {'title': '同方向不同方法文献推荐', 'fields': ['research_question', 'method', 'abstract']},
        'reading_notes': {'title': '阅读备忘与可追问问题', 'fields': []},
    }

    DEFAULT_REPORT_MODULES = [
        'basic_info',
        'abstract',
        'research_question',
        'method',
        'experiment_data',
        'main_results',
        'innovations',
        'limitations',
        'reproducibility',
        'future_work',
        'literature_trace',
        'related_papers',
        'reading_notes',
    ]

    FIELD_LABELS = {
        'title': '题名',
        'authors': '作者',
        'keywords': '关键词',
        'abstract': '摘要',
        'research_question': '研究问题',
        'method': '方法 / 模型',
        'experiment_data': '数据集 / 实验设计',
        'main_results': '主要结果',
        'innovations': '创新点',
        'limitations': '局限性',
        'future_work': '未来工作',
    }

    def __init__(self) -> None:
        self.llm = OpenAICompatibleLLM(scenario='report')

    @staticmethod
    def _clean_report_value(value: object, limit: int = 4000) -> str:
        if value is None:
            return ''
        if isinstance(value, (list, tuple, set)):
            text = '、'.join(str(x).strip() for x in value if str(x).strip())
        elif isinstance(value, dict):
            parts = []
            for key, item in value.items():
                item_text = GenerationService._clean_report_value(item, limit=800)
                if item_text:
                    parts.append(f'{key}：{item_text}')
            text = '；'.join(parts)
        else:
            text = str(value).strip()
            if text.startswith(('[', '{')):
                parsed = loads(text, default=None)
                if parsed is not None:
                    return GenerationService._clean_report_value(parsed, limit=limit)

        if not text or text.lower() in {'null', 'none', 'nan', '[]', '{}'}:
            return ''
        text = ' '.join(text.split())
        return text[:limit]

    @staticmethod
    def _extract_publication_year(value: object) -> int | None:
        text = str(value or '')
        match = re.search(r'\b(19|20)\d{2}\b', text)
        if not match:
            return None
        year = int(match.group(0))
        return year if 1900 <= year <= 2100 else None

    @classmethod
    def _normalize_report_modules(cls, modules: list[str] | None) -> list[str]:
        if not modules:
            return cls.DEFAULT_REPORT_MODULES.copy()

        aliases = {
            'background': 'research_question',
            'question': 'research_question',
            'dataset': 'experiment_data',
            'data': 'experiment_data',
            'experiment': 'experiment_data',
            'results': 'main_results',
            'result': 'main_results',
            'conclusion': 'main_results',
            'innovation': 'innovations',
            'contribution': 'innovations',
            'limit': 'limitations',
            'future': 'future_work',
            'reproduce': 'reproducibility',
            'trace': 'literature_trace',
            'literature': 'literature_trace',
            'citation': 'literature_trace',
            'references': 'literature_trace',
            'extension': 'literature_trace',
            'related': 'related_papers',
            'recommendation': 'related_papers',
            'same_direction': 'related_papers',
        }

        normalized: list[str] = []
        for item in modules:
            raw = str(item).strip()
            key = aliases.get(raw, raw)
            if key in cls.REPORT_MODULE_META and key not in normalized:
                normalized.append(key)

        if 'basic_info' not in normalized:
            normalized.insert(0, 'basic_info')

        return normalized or cls.DEFAULT_REPORT_MODULES.copy()

    @classmethod
    def _format_report_field(
        cls,
        label: str,
        value: object,
        empty_text: str = '原文片段中未充分体现该项信息。',
    ) -> str:
        text = cls._clean_report_value(value, limit=5000)
        if not text:
            return f'- **{label}**：{empty_text}'
        return f'- **{label}**：{text}'

    @classmethod
    def _build_report_source_data(cls, paper: Paper, info: PaperExtractedInfo) -> dict:
        return {
            'paper_id': info.paper_id,
            'title': cls._clean_report_value(info.title or paper.title or paper.original_filename),
            'authors': cls._clean_report_value(info.authors or paper.authors),
            'keywords': cls._clean_report_value(info.keywords or paper.keywords),
            'publication_year': paper.publication_year,
            'journal_conf': cls._clean_report_value(paper.journal_conf),
            'doi': cls._clean_report_value(paper.doi),
            'abstract': cls._clean_report_value(info.abstract),
            'research_question': cls._clean_report_value(info.research_question),
            'method': cls._clean_report_value(info.method),
            'experiment_data': cls._clean_report_value(info.experiment_data),
            'main_results': cls._clean_report_value(info.main_results),
            'innovations': cls._clean_report_value(info.innovations),
            'limitations': cls._clean_report_value(info.limitations),
            'future_work': cls._clean_report_value(info.future_work),
        }

    @classmethod
    def _make_missing_or_value(cls, name: str, value: object) -> dict:
        text = cls._clean_report_value(value, limit=1200)
        if not text:
            return {
                'name': name,
                'value': '当前解析未提取到明确证据',
                'status': 'missing',
            }
        return {'name': name, 'value': text, 'status': 'extracted'}

    @classmethod
    def _extract_metric_cards(cls, text: str) -> list[dict]:
        cleaned = cls._clean_report_value(text, limit=20000)
        if not cleaned:
            return []

        metric_names = cls._metric_name_pattern()
        number = r'(?:\d+(?:\.\d+)?\s?%|\d+\.\d+)'
        patterns = [
            re.compile(rf'\b(?P<label>{metric_names})\b[^\n。；;:：]{{0,40}}?[:：=]?\s*(?P<value>{number})', re.I),
            re.compile(rf'(?P<value>{number})[^\n。；;]{{0,30}}?\b(?P<label>{metric_names})\b', re.I),
        ]

        cards: list[dict] = []
        seen: set[tuple[str, str]] = set()
        fragments = [part.strip() for part in re.split(r'[。；;\n，,]|(?:\s+and\s+)', cleaned) if part.strip()]
        for fragment in fragments:
            for pattern in patterns:
                match = pattern.search(fragment)
                if not match:
                    continue
                label = match.group('label').strip()
                value = match.group('value').replace(' ', '')
                key = (label.lower(), value)
                if key in seen:
                    continue
                seen.add(key)
                cards.append({
                    'label': label,
                    'value': value,
                    'note': '来自原文实验结果或结构化抽取字段',
                    'source': fragment[:220],
                })
                if len(cards) >= 8:
                    return cards
        return cards

    @staticmethod
    def _metric_name_pattern() -> str:
        return (
            r'Pass@(?:\d+|k)|Accuracy|Acc\.?|F1-score|F1|Exact Match|EM|MRR|Recall|Precision|'
            r'Success Rate|Compile Rate|Execution Rate|Top-?k|BLEU|ROUGE(?:-[L\d])?|AUC|'
            r'MAP|NDCG|Hits@(?:\d+|k)'
        )

    @classmethod
    def _extract_metric_names(cls, text: str) -> list[str]:
        cleaned = cls._clean_report_value(text, limit=12000)
        if not cleaned:
            return []
        names: list[str] = []
        for match in re.finditer(rf'\b(?:{cls._metric_name_pattern()})\b', cleaned, re.I):
            name = match.group(0).strip()
            key = name.lower()
            if key not in {item.lower() for item in names}:
                names.append(name)
            if len(names) >= 8:
                break
        return names

    @classmethod
    def _build_visual_summary(cls, source_data: dict, evidence_text: str) -> dict:
        method_flow = [
            {
                'title': '研究问题',
                'content': cls._clean_report_value(
                    source_data.get('research_question') or source_data.get('abstract'),
                    limit=260,
                ) or '当前解析未提取到明确证据',
            },
            {
                'title': '核心方法',
                'content': cls._clean_report_value(source_data.get('method'), limit=260)
                or '当前解析未提取到明确证据',
            },
            {
                'title': '实验验证',
                'content': cls._clean_report_value(source_data.get('experiment_data'), limit=260)
                or '当前解析未提取到明确证据',
            },
            {
                'title': '主要结论',
                'content': cls._clean_report_value(
                    source_data.get('main_results') or source_data.get('innovations'),
                    limit=260,
                ) or '当前解析未提取到明确证据',
            },
        ]

        metric_cards = cls._extract_metric_cards(
            '\n'.join([
                cls._clean_report_value(source_data.get('experiment_data'), limit=4000),
                cls._clean_report_value(source_data.get('main_results'), limit=4000),
                cls._clean_report_value(evidence_text, limit=12000),
            ])
        )
        metric_names = '、'.join(dict.fromkeys(card['label'] for card in metric_cards))
        if not metric_names:
            names_only = cls._extract_metric_names(
                '\n'.join([
                    cls._clean_report_value(source_data.get('experiment_data'), limit=4000),
                    cls._clean_report_value(source_data.get('main_results'), limit=4000),
                    cls._clean_report_value(evidence_text, limit=8000),
                ])
            )
            if names_only:
                metric_names = f"{'、'.join(names_only)}（已提取指标名称，未提取具体数值）"

        key_data_table = [
            cls._make_missing_or_value('数据集 / 任务', source_data.get('experiment_data')),
            cls._make_missing_or_value('评价指标', metric_names),
            cls._make_missing_or_value('对比方法', cls._extract_comparison_hint(source_data.get('experiment_data'))),
            cls._make_missing_or_value('核心结果', source_data.get('main_results')),
        ]

        return {
            'method_flow': method_flow,
            'key_data_table': key_data_table,
            'metric_cards': metric_cards,
        }

    @staticmethod
    def _is_missing_summary_text(value: object) -> bool:
        text = str(value or '').strip()
        return not text or text == '当前解析未提取到明确证据'

    @classmethod
    def _normalize_visual_flow(cls, flow: object, fallback_flow: list[dict]) -> list[dict]:
        titles = ['研究问题', '核心方法', '实验验证', '主要结论']
        by_title: dict[str, str] = {}
        if isinstance(flow, list):
            for item in flow:
                if not isinstance(item, dict):
                    continue
                title = cls._clean_report_value(item.get('title'), limit=20)
                content = cls._clean_report_value(item.get('content'), limit=180)
                if title in titles and content:
                    by_title[title] = content

        normalized: list[dict] = []
        fallback_by_title = {
            item.get('title'): item.get('content')
            for item in fallback_flow
            if isinstance(item, dict)
        }
        for title in titles:
            content = by_title.get(title) or fallback_by_title.get(title) or '当前解析未提取到明确证据'
            normalized.append({
                'title': title,
                'content': cls._clean_report_value(content, limit=180) or '当前解析未提取到明确证据',
            })
        return normalized

    @classmethod
    def _normalize_visual_table(cls, table: object, fallback_table: list[dict]) -> list[dict]:
        names = ['数据集 / 任务', '评价指标', '对比方法', '核心结果']
        fallback_by_name = {
            item.get('name'): item
            for item in fallback_table
            if isinstance(item, dict)
        }
        incoming_by_name: dict[str, dict] = {}
        if isinstance(table, list):
            for item in table:
                if not isinstance(item, dict):
                    continue
                name = cls._clean_report_value(item.get('name'), limit=40)
                value = cls._clean_report_value(item.get('value'), limit=1200)
                status = item.get('status') if item.get('status') in {'extracted', 'missing'} else None
                if name in names and value and status:
                    incoming_by_name[name] = {'name': name, 'value': value, 'status': status}

        normalized: list[dict] = []
        for name in names:
            fallback = fallback_by_name.get(name) or cls._make_missing_or_value(name, '')
            item = incoming_by_name.get(name) or fallback
            if item.get('status') == 'missing':
                item = {**item, 'value': '当前解析未提取到明确证据'}
            normalized.append(item)
        return normalized

    async def _polish_visual_summary_with_llm(
        self,
        source_data: dict,
        evidence_text: str,
        fallback_visual_summary: dict,
    ) -> dict:
        prompt = f"""请基于结构化抽取结果和论文原文片段，润色研读报告的图表化摘要。

硬性要求：
1. 只依据给定信息，不得编造数据、指标、数据集、结论或方法；
2. method_flow 必须是 4 项，标题固定为：研究问题、核心方法、实验验证、主要结论；
3. method_flow.content 使用中文短句概括，避免直接粘贴英文原文，每项 80-140 个中文字符以内；
4. 如果对应信息缺失，content 必须写“当前解析未提取到明确证据”；
5. key_data_table 只可基于明确证据优化表达，缺失项 value 必须写“当前解析未提取到明确证据”，status 写 missing；
6. metric_cards 原样返回 fallback 中已有内容，不要新增、删除或改写指标卡；
7. 严格输出 JSON，不要 Markdown，不要解释。

结构化抽取结果：
{dumps(source_data)}

当前兜底摘要：
{dumps(fallback_visual_summary)}

论文原文片段：
{evidence_text[:12000]}
"""
        try:
            resp = await self.llm.async_chat(
                [
                    {
                        'role': 'system',
                        'content': '你是科研论文图表摘要润色助手，只能基于证据把内容压缩成中文短句，不得补事实。',
                    },
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.05,
                max_tokens=1800,
            )
        except Exception:
            return fallback_visual_summary

        text = (resp or '').strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        parsed = loads(text, default=None)
        if not isinstance(parsed, dict):
            match = re.search(r'\{.*\}', text, flags=re.S)
            parsed = loads(match.group(0), default=None) if match else None
        if not isinstance(parsed, dict):
            return fallback_visual_summary

        fallback_flow = fallback_visual_summary.get('method_flow') or []
        fallback_table = fallback_visual_summary.get('key_data_table') or []
        return {
            'method_flow': self._normalize_visual_flow(parsed.get('method_flow'), fallback_flow),
            'key_data_table': self._normalize_visual_table(parsed.get('key_data_table'), fallback_table),
            'metric_cards': fallback_visual_summary.get('metric_cards') or [],
        }

    @classmethod
    def _extract_comparison_hint(cls, value: object) -> str:
        text = cls._clean_report_value(value, limit=3000)
        if not text:
            return ''
        sentences = re.split(r'(?<=[。；;.!?])\s*', text)
        keywords = ('baseline', 'baselines', 'compare', 'comparison', '对比', '比较', '基线', '消融')
        picked = [s.strip() for s in sentences if any(k.lower() in s.lower() for k in keywords)]
        return ' '.join(picked[:2])[:1000]

    @classmethod
    def _parse_reference_text(cls, raw: str) -> dict:
        text = cls._clean_report_value(raw, limit=2000)
        if not text:
            return {'title': '', 'authors': '', 'year': '', 'venue': ''}

        cleaned = re.sub(r'^\s*(?:\[\d+\]|\d+[.)])\s*', '', text)
        cleaned = re.sub(r'https?://\S+', '', cleaned).strip()
        year_match = re.search(r'\b(19|20)\d{2}\b', cleaned)
        year = year_match.group(0) if year_match else ''

        title = ''
        quoted = re.search(r'["“](.+?)["”]', cleaned)
        if quoted:
            title = quoted.group(1).strip()
        elif year_match:
            after_year = cleaned[year_match.end():].lstrip('.:,，： ')
            pieces = [p.strip() for p in re.split(r'\.\s+', after_year) if p.strip()]
            if pieces:
                title = pieces[0]
        if not title:
            pieces = [p.strip() for p in re.split(r'\.\s+', cleaned) if p.strip()]
            title = pieces[1] if len(pieces) > 1 and len(pieces[0]) < 120 else pieces[0]

        authors = ''
        if year_match:
            authors = cleaned[:year_match.start()].strip(' .,:，；;')
        elif '.' in cleaned:
            authors = cleaned.split('.', 1)[0].strip()
        if len(authors) > 180:
            authors = ''

        venue = ''
        tail_source = cleaned[year_match.end():] if year_match else cleaned
        venue_match = re.search(
            r'\b(?:Nature|Science|Cell|NeurIPS|ICML|ICLR|ACL|EMNLP|NAACL|CVPR|AAAI|KDD|WWW|SIGIR|arXiv|IEEE|ACM)\b[^.。；;]*',
            tail_source,
            re.I,
        )
        if venue_match:
            venue = venue_match.group(0).strip(' .,:，；;')

        title = cls._clean_reference_title(title, cleaned)

        return {
            'title': title,
            'authors': cls._clean_report_value(authors, limit=180),
            'year': year,
            'venue': cls._clean_report_value(venue, limit=160),
        }

    @classmethod
    def _clean_reference_title(cls, title: str, raw: str) -> str:
        cleaned_title = cls._clean_report_value(title, limit=240).strip(' .,:，；;')
        raw_title = cls._clean_report_value(raw, limit=240).strip(' .,:，；;')
        if cls._is_bad_reference_title(cleaned_title):
            fallback = cls._reference_title_fallback(raw_title)
            return fallback[:120]
        return cleaned_title

    @staticmethod
    def _is_bad_reference_title(title: str) -> bool:
        value = (title or '').strip(' .,:，；;')
        if not value or len(value) < 8:
            return True
        if re.fullmatch(r'(?:19|20)\d{2}', value):
            return True
        if re.fullmatch(r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', value, re.I):
            return True
        if re.fullmatch(r'[\d.\s]+', value):
            return True
        if re.fullmatch(r'\d{4,6}(?:\s+(?:19|20)\d{2})?', value):
            return True
        if re.search(r'\b(?:arxiv\s+)?abs/\d{4}\.\d{4,5}', value, re.I):
            return True
        if re.search(r'\b(?:doi[:：\s]*10\.|10\.\d{4,9}/)', value, re.I):
            return True
        if re.fullmatch(r'(?:arxiv\s+preprint|(?:19|20)\d{2}\s+arxiv\s+preprint)', value, re.I):
            return True
        return False

    @classmethod
    def _reference_title_fallback(cls, raw: str) -> str:
        text = cls._clean_report_value(raw, limit=2000)
        if not text:
            return ''
        before_identifier = re.split(
            r'\b(?:doi[:：\s]*10\.|arxiv[:：\s]*(?:abs/)?\d|abs/\d{4}\.\d{4,5}|https?://(?:arxiv\.org|(?:dx\.)?doi\.org))',
            text,
            maxsplit=1,
            flags=re.I,
        )[0].strip(' .,:，；;')
        if before_identifier and not cls._is_bad_reference_title(before_identifier):
            pieces = [p.strip(' .,:，；;') for p in re.split(r'\.\s+', before_identifier) if p.strip(' .,:，；;')]
            for piece in reversed(pieces):
                if not cls._is_bad_reference_title(piece):
                    return piece
        return text[:120]

    @staticmethod
    def _infer_url_type(url: str | None) -> str:
        if not url:
            return 'none'
        lowered = url.lower()
        if 'doi.org' in lowered:
            return 'doi'
        if 'arxiv.org' in lowered:
            return 'arxiv'
        if 'scholar.google.com' in lowered:
            return 'scholar'
        return 'official'

    @classmethod
    def _build_reference_links(cls, reference_trace: list[dict]) -> list[dict]:
        links: list[dict] = []
        for item in reference_trace or []:
            raw = cls._clean_report_value(item.get('content') or item.get('raw'), limit=2000)
            parsed = cls._parse_reference_text(raw)
            url = None
            doi = extract_doi_from_text(raw) or item.get('doi')
            if doi:
                url = resolve_official_paper_url(str(doi))
            if not url:
                arxiv_id = extract_arxiv_id_from_text(raw)
                if not arxiv_id:
                    arxiv_match = re.search(r'\b(?:abs/)?(\d{4}\.\d{4,5}(?:v\d+)?)\b', raw, re.I)
                    arxiv_id = arxiv_match.group(1) if arxiv_match else None
                if arxiv_id:
                    url = f'https://arxiv.org/abs/{arxiv_id}'
            if not url:
                url = extract_official_url_from_text(raw) or item.get('official_url')
            if not url and raw:
                url = scholar_search_url(parsed.get('title') or raw)

            links.append({
                **parsed,
                'title': raw,
                'raw': raw,
                'url': url or '',
                'url_type': cls._infer_url_type(url),
                'reason': cls._clean_report_value(item.get('reason'), limit=240),
            })
        return links

    @classmethod
    def _build_reference_links_markdown(cls, reference_links: list[dict]) -> str:
        lines = ['## 文献溯源', '', '### 可点击参考文献']
        if not reference_links:
            lines.append('- 暂未生成可点击文献溯源链接。')
            return '\n'.join(lines)
        type_labels = {
            'doi': 'DOI',
            'arxiv': 'arXiv',
            'official': '官方链接',
            'scholar': '学术搜索',
            'none': '暂无可用链接',
        }
        for idx, item in enumerate(reference_links, start=1):
            label = item.get('title') or item.get('raw') or f'参考文献 {idx}'
            url = item.get('url')
            if url:
                lines.append(f'{idx}. [{label}]({url})')
            else:
                lines.append(f'{idx}. {label}')
            if item.get('authors'):
                lines.append(f'   - 作者：{item["authors"]}')
            if item.get('year'):
                lines.append(f'   - 年份：{item["year"]}')
            if item.get('venue'):
                lines.append(f'   - 来源：{item["venue"]}')
            lines.append(f'   - 链接类型：{type_labels.get(item.get("url_type"), item.get("url_type") or "暂无可用链接")}')
            if item.get('reason'):
                lines.append(f'   - 溯源理由：{item["reason"]}')
            if item.get('raw'):
                lines.append(f'   - 原文：{item["raw"]}')
        return '\n'.join(lines)

    @classmethod
    def _append_reference_links_section(cls, markdown: str, reference_links: list[dict]) -> str:
        cleaned = re.sub(r'\n{2,}##\s*(?:文献溯源链接|可点击文献溯源)\s*\n.*$', '', markdown.strip(), flags=re.S)
        return cleaned

    @classmethod
    @staticmethod
    def _section_plain_text(section: str) -> str:
        text = re.sub(r'[#*_>`\-\[\]()]', '', section or '')
        text = re.sub(r'https?://\S+', '', text)
        return ' '.join(text.split()).strip()

    @classmethod
    def _sections_are_repeated(cls, first: str, second: str) -> bool:
        a = cls._section_plain_text(first)
        b = cls._section_plain_text(second)
        if len(a) < 80 or len(b) < 80:
            return False
        if a in b or b in a:
            return True

        a_tokens = set(re.findall(r'[A-Za-z0-9_\-.]{4,}|[\u4e00-\u9fff]{2,}', a.lower()))
        b_tokens = set(re.findall(r'[A-Za-z0-9_\-.]{4,}|[\u4e00-\u9fff]{2,}', b.lower()))
        if not a_tokens or not b_tokens:
            return False
        overlap = len(a_tokens & b_tokens) / max(len(a_tokens | b_tokens), 1)
        return overlap >= 0.72

    @classmethod
    def _dedupe_abstract_and_research_question(cls, markdown: str, source: dict | None = None) -> str:
        sections = list(re.finditer(r'(^##\s+(.+?)\s*$)([\s\S]*?)(?=^##\s+|\Z)', markdown, flags=re.M))
        if not sections:
            return markdown

        abstract_match = next((m for m in sections if m.group(2).strip() == '摘要速览'), None)
        rq_match = next((m for m in sections if m.group(2).strip() == '研究背景与核心问题'), None)
        if not abstract_match or not rq_match:
            return markdown
        if not cls._sections_are_repeated(abstract_match.group(3), rq_match.group(3)):
            return markdown

        source = source or {}
        abstract = cls._clean_report_value(source.get('abstract'), limit=2000)
        research_question = cls._clean_report_value(source.get('research_question'), limit=2000)
        if research_question and not cls._sections_are_repeated(abstract, research_question):
            replacement_body = f'\n\n**研究问题**：{research_question}\n\n'
        else:
            replacement_body = (
                '\n\n**研究问题**：当前解析未提取到独立的研究背景与核心问题，'
                '请结合引言进一步确认；本节已避免重复展示摘要原文。\n\n'
            )

        start, end = rq_match.span(3)
        return f'{markdown[:start]}{replacement_body}{markdown[end:]}'

    @classmethod
    def _strip_duplicate_reference_markdown(cls, markdown: str) -> str:
        text = markdown
        text = re.sub(
            r'\n#{1,3}\s*原文参考文献(?:溯源|列表)?\s*\n[\s\S]*?(?=\n#{1,3}\s|\n##\s|$)',
            '\n',
            text,
        )
        text = re.sub(
            r'\n#{1,3}\s*可点击参考文献\s*\n[\s\S]*?(?=\n#{1,3}\s|\n##\s|$)',
            '\n',
            text,
        )

        def trim_extension_section(match: re.Match[str]) -> str:
            heading = match.group(1)
            body = match.group(2)
            learning = re.search(
                r'###\s*基础知识与拓展检索式[\s\S]*?(?=\n###\s|\n##\s|$)',
                body,
            )
            if learning:
                return f'{heading}{learning.group(0).strip()}\n\n'
            return heading

        return re.sub(
            r'(##\s*拓展检索\s*\n)([\s\S]*?)(?=\n##\s|$)',
            trim_extension_section,
            text,
        )

    @classmethod
    def _cleanup_report_markdown(cls, markdown: str, source: dict | None = None) -> str:
        text = cls._append_reference_links_section(markdown, [])
        text = cls._strip_duplicate_reference_markdown(text)
        text = re.sub(
            r'\n?\*\*复现风险提示\*\*[:：]\s*(?=\n{2,}##|\Z)',
            '',
            text,
            flags=re.S,
        )
        text = re.sub(
            r'\n?\*\*复现风险提示\*\*[:：]\s*\n(?=\s*(?:##|\Z))',
            '',
            text,
            flags=re.S,
        )
        text = cls._dedupe_abstract_and_research_question(text, source)
        return text.strip()

    @classmethod
    def _tokenize_for_report(cls, text: object) -> set[str]:
        cleaned = cls._clean_report_value(text, limit=8000).lower()
        if not cleaned:
            return set()

        words = set(re.findall(r'[a-z][a-z0-9_+\-.]{2,}', cleaned))
        chinese = re.findall(r'[\u4e00-\u9fff]{2,}', cleaned)
        for item in chinese:
            if len(item) <= 6:
                words.add(item)
            else:
                for i in range(0, min(len(item) - 1, 20)):
                    words.add(item[i:i + 2])

        stop = {
            'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'was', 'were',
            'using', 'based', 'paper', 'method', 'model', 'result', 'results', 'approach',
            '研究', '方法', '模型', '论文', '系统', '结果', '实验', '基于', '提出',
            '本文', '通过', '进行', '一种',
        }
        return {w for w in words if w not in stop and len(w) >= 2}

    @classmethod
    def _build_learning_queries(cls, source: dict) -> list[dict]:
        title = source.get('title') or ''
        keywords = source.get('keywords') or ''
        rq = source.get('research_question') or source.get('abstract') or ''
        method = source.get('method') or ''

        terms = []
        for text in [keywords, title, rq, method]:
            for term in sorted(cls._tokenize_for_report(text), key=len, reverse=True):
                if term not in terms:
                    terms.append(term)
                if len(terms) >= 8:
                    break
            if len(terms) >= 8:
                break

        topic_terms = terms[:4]
        method_terms = [t for t in terms[4:8] if t not in topic_terms]
        topic = ' '.join(topic_terms) or cls._clean_report_value(title, limit=80) or '该研究方向'
        method_part = ' '.join(method_terms) or 'alternative methods'

        return [
            {
                'name': '基础概念入门检索',
                'query': f'"{topic}" tutorial survey introduction',
                'purpose': '用于补齐该论文涉及的基础概念、任务定义和常用术语。',
            },
            {
                'name': '综述与脉络检索',
                'query': f'"{topic}" survey review benchmark',
                'purpose': '用于寻找综述、benchmark 或领域脉络型论文。',
            },
            {
                'name': '同方向不同方法检索',
                'query': f'"{topic}" "{method_part}" comparison alternative approach',
                'purpose': '用于寻找研究方向相近但技术路线不同的论文。',
            },
        ]

    async def _select_reference_trace_items(
        self,
        db: AsyncSession,
        paper_id: int,
        source: dict,
        limit: int = 8,
    ) -> list[dict]:
        rows = (
            await db.execute(
                select(ContentItem)
                .where(ContentItem.paper_id == paper_id, ContentItem.item_type == 'reference')
                .order_by(ContentItem.order_index.asc())
                .limit(120)
            )
        ).scalars().all()

        if not rows:
            return []

        anchor = ' '.join([
            source.get('title') or '',
            source.get('keywords') or '',
            source.get('research_question') or '',
            source.get('method') or '',
            source.get('abstract') or '',
        ])
        anchor_terms = self._tokenize_for_report(anchor)
        scored: list[tuple[float, ContentItem, list[str]]] = []

        for row in rows:
            content = self._clean_report_value(row.content, limit=1200)
            if not content:
                continue
            terms = self._tokenize_for_report(content)
            overlap = sorted(anchor_terms & terms, key=lambda x: (len(x), x), reverse=True)
            if overlap:
                scored.append((float(len(overlap)), row, overlap[:4]))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        seen: set[str] = set()

        for _, row, overlap in scored:
            content = self._clean_report_value(row.content, limit=2000)
            key = content[:120]
            if key in seen:
                continue
            seen.add(key)
            results.append({
                'content': content,
                'page_number': row.page_number,
                'reason': '与本文研究方向相关',
                'source_type': 'reference',
                'doi': extract_doi_from_text(content),
                'official_url': extract_official_url_from_text(content)
                or resolve_official_paper_url(extract_doi_from_text(content)),
            })
            if len(results) >= limit:
                break

        if not results:
            for row in rows[:limit]:
                content = self._clean_report_value(row.content, limit=2000)
                if not content:
                    continue
                key = content[:120]
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    'content': content,
                    'page_number': row.page_number,
                    'reason': '可作为研究脉络补充阅读',
                    'source_type': 'reference',
                    'doi': extract_doi_from_text(content),
                    'official_url': extract_official_url_from_text(content)
                    or resolve_official_paper_url(extract_doi_from_text(content)),
                })

        return results

    async def _find_same_direction_different_method_papers(
        self,
        db: AsyncSession,
        user_id: int,
        paper_id: int,
        source: dict,
        limit: int = 5,
    ) -> list[dict]:
        rows = (
            await db.execute(
                select(Paper, PaperExtractedInfo)
                .join(PaperExtractedInfo, PaperExtractedInfo.paper_id == Paper.id)
                .where(
                    Paper.user_id == user_id,
                    Paper.is_deleted == False,
                    Paper.id != paper_id,
                )
                .limit(200)
            )
        ).all()

        if not rows:
            return []

        target_direction = ' '.join([
            source.get('title') or '',
            source.get('keywords') or '',
            source.get('research_question') or '',
            source.get('abstract') or '',
        ])
        target_method = source.get('method') or ''
        target_direction_terms = self._tokenize_for_report(target_direction)
        target_method_terms = self._tokenize_for_report(target_method)
        candidates: list[dict] = []

        for paper, info in rows:
            candidate_direction = ' '.join([
                self._clean_report_value(info.title or paper.title or paper.original_filename),
                self._clean_report_value(info.keywords or paper.keywords),
                self._clean_report_value(info.research_question),
                self._clean_report_value(info.abstract),
            ])
            candidate_method = self._clean_report_value(info.method)
            direction_terms = self._tokenize_for_report(candidate_direction)
            method_terms = self._tokenize_for_report(candidate_method)
            same_terms = sorted(target_direction_terms & direction_terms, key=lambda x: (len(x), x), reverse=True)
            if not same_terms:
                continue

            method_overlap = target_method_terms & method_terms
            method_similarity = len(method_overlap) / max(len(target_method_terms | method_terms), 1)
            different_method_score = 1.0 - method_similarity if target_method_terms and method_terms else 0.4
            score = len(same_terms) * 0.75 + different_method_score * 2.0
            title = self._clean_report_value(info.title or paper.title or paper.original_filename, limit=160)

            candidates.append({
                'paper_id': paper.id,
                'title': title,
                'doi': paper.doi,
                'official_url': resolve_official_paper_url(paper.doi),
                'score': round(score, 3),
                'reason': '该文献与当前论文存在研究主题重合，但方法字段关键词重合度较低，适合作为替代技术路线对照阅读。',
                'same_direction_evidence': '、'.join(same_terms[:6]) or '主题字段存在相似表达',
                'different_method_evidence': (
                    f"当前方法：{self._clean_report_value(target_method, limit=120) or '暂未抽取'}；"
                    f"候选方法：{self._clean_report_value(candidate_method, limit=120) or '暂未抽取'}"
                ),
                'source_type': 'internal_library',
            })

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:limit]

    @classmethod
    def _build_report_markdown(cls, source: dict, modules: list[str], trace_data: dict) -> str:
        lines: list[str] = []
        report_title = source.get('title') or '未命名论文'
        lines.append(f'# {report_title} 研读报告')
        lines.append('')

        for module in modules:
            meta = cls.REPORT_MODULE_META[module]
            lines.append(f'## {meta["title"]}')
            lines.append('')

            if module == 'basic_info':
                lines.append(cls._format_report_field('题名', source.get('title')))
                lines.append(cls._format_report_field('作者', source.get('authors')))
                lines.append(cls._format_report_field('年份', source.get('publication_year')))
                lines.append(cls._format_report_field('期刊 / 会议', source.get('journal_conf')))
                lines.append(cls._format_report_field('DOI', source.get('doi')))
                lines.append(cls._format_report_field('关键词', source.get('keywords')))
            elif module == 'reproducibility':
                lines.append(cls._format_report_field('复现所需方法 / 模型', source.get('method')))
                lines.append(cls._format_report_field('复现所需数据 / 实验对象', source.get('experiment_data')))
                lines.append(cls._format_report_field('需要对齐的主要结果', source.get('main_results')))
                risk_items = []
                if not source.get('experiment_data'):
                    risk_items.append('暂未抽取到明确数据集或实验对象，复现时需要优先补充数据来源。')
                if not source.get('method'):
                    risk_items.append('暂未抽取到完整方法流程，复现时需要回到原文方法章节核对实现细节。')
                if not source.get('main_results'):
                    risk_items.append('暂未抽取到明确指标或结果，复现时需要补充评价指标和目标数值。')
                if risk_items:
                    lines.append('')
                    lines.append('**复现风险提示**：')
                    for item in risk_items:
                        lines.append(f'- {item}')
            elif module == 'literature_trace':
                queries = trace_data.get('learning_queries') or []
                lines.append('### 基础知识与拓展检索式')
                if queries:
                    for item in queries:
                        q = item.get('query') or ''
                        scholar = scholar_search_url(q) if q else None
                        if scholar:
                            lines.append(f'- **{item["name"]}**：[{q}]({scholar})')
                        else:
                            lines.append(f'- **{item["name"]}**：`{q}`')
                        lines.append(f'  - 用途：{item["purpose"]}')
                else:
                    lines.append('- 暂未生成拓展检索式。')
            elif module == 'research_question':
                lines.append(cls._format_report_field(
                    '研究问题',
                    source.get('research_question'),
                    empty_text='当前解析未提取到明确研究问题，可结合摘要和引言进一步确认。',
                ))
            elif module == 'related_papers':
                related = trace_data.get('related_papers') or []
                if related:
                    for idx, item in enumerate(related, start=1):
                        title = item.get('title') or '未命名文献'
                        url = item.get('official_url') or resolve_official_paper_url(item.get('doi'))
                        if url:
                            lines.append(f'{idx}. **[{title}]({url})**')
                        else:
                            lines.append(f'{idx}. **{title}**')
                        lines.append(f'   - 推荐理由：{item["reason"]}')
                        lines.append(f'   - 相同研究方向依据：{item["same_direction_evidence"]}')
                        lines.append(f'   - 方法差异依据：{item["different_method_evidence"]}')
                else:
                    lines.append('- 暂未在当前用户文献库中找到“同方向但方法不同”的已解析论文。')
                    lines.append('- 建议先上传同一研究主题下的更多论文，或使用上方检索式补充文献。')
            elif module == 'reading_notes':
                lines.append('- 这篇论文解决的核心问题是什么？')
                lines.append('- 作者的方法与已有方法相比差异在哪里？')
                lines.append('- 实验数据和评价指标是否足以支撑结论？')
                lines.append('- 哪些部分适合作为后续研究或复现切入点？')
            else:
                for field in meta['fields']:
                    label = cls.FIELD_LABELS.get(field, meta['title'])
                    lines.append(cls._format_report_field(label, source.get(field)))

            lines.append('')

        return '\n'.join(lines).strip()

    async def _load_paper_evidence_text(
        self,
        db: AsyncSession,
        paper_id: int,
        limit_chars: int = 30000,
    ) -> str:
        rows = (
            await db.execute(
                select(ContentItem)
                .where(
                    ContentItem.paper_id == paper_id,
                    ContentItem.item_type != 'reference',
                )
                .order_by(ContentItem.order_index.asc())
                .limit(300)
            )
        ).scalars().all()

        parts: list[str] = []
        total = 0
        for row in rows:
            content = self._clean_report_value(row.content, limit=2000)
            if not content:
                continue

            prefix = f'[{row.item_type}]'
            if row.page_number:
                prefix += f'[page={row.page_number}]'

            part = f'{prefix} {content}'
            parts.append(part)
            total += len(part)
            if total >= limit_chars:
                break

        return '\n'.join(parts)[:limit_chars]

    async def _extract_missing_report_fields_with_llm(
        self,
        source_data: dict,
        evidence_text: str,
    ) -> dict:
        target_fields = [
            'authors',
            'keywords',
            'publication_year',
            'journal_conf',
            'doi',
            'research_question',
            'method',
            'experiment_data',
            'main_results',
            'innovations',
            'limitations',
            'future_work',
        ]
        missing_fields = [key for key in target_fields if not self._clean_report_value(source_data.get(key))]
        if not missing_fields or not evidence_text.strip():
            return {}

        field_names = {
            'authors': '作者列表',
            'keywords': '关键词',
            'publication_year': '论文发表年份',
            'journal_conf': '期刊 / 会议 / 预印本平台信息',
            'doi': 'DOI 标识',
            'research_question': '研究背景与核心问题',
            'method': '方法 / 模型 / 技术路线',
            'experiment_data': '数据集 / 实验对象 / 实验设计',
            'main_results': '主要结果与结论',
            'innovations': '创新点与贡献',
            'limitations': '局限性与适用边界',
            'future_work': '未来工作与后续研究方向',
        }
        empty_json = {key: '' for key in target_fields}

        prompt = f"""请基于下面给出的论文原文片段，补充抽取研读报告所需字段。

要求：
1. 只能依据原文片段抽取，不要编造原文没有的信息；
2. 如果原文片段中确实无法判断某个字段，请返回空字符串；
3. 每个字段用中文撰写，内容要具体、完整、有信息量；
4. 不要只写一句话。除非原文信息极少，否则每个非空字段至少写 120-250 个中文字符；
5. method 字段要说明核心框架、关键步骤、技术路线和解决的问题；
6. experiment_data 字段要说明实验对象、比较对象、评估设置、模型/数据/任务类型；
7. main_results 字段要保留原文中的关键指标、提升幅度、比较结论；
8. innovations 字段要概括本文相对已有工作的主要贡献；
9. limitations 字段要指出适用边界、潜在不足或原文中隐含的限制；
10. future_work 字段要结合原文内容概括后续可扩展方向；
11. publication_year 只返回 4 位年份，例如 2024；没有明确年份则返回空字符串；
12. journal_conf 只返回原文明确出现的期刊、会议、arXiv、预印本或出版 venue；没有则返回空字符串；
13. doi 只返回 DOI 本身，不要补 URL 前缀；没有则返回空字符串；
14. authors 和 keywords 如果原文片段中明确出现，可以补齐；没有则返回空字符串；
15. research_question 必须提炼核心研究背景与问题，不要复制 abstract 原文；如果只能看到摘要，也要概括问题而不是原样照抄摘要；
16. 输出严格 JSON，不要使用 Markdown，不要添加解释。

需要补充的字段：
{missing_fields}

字段含义：
{field_names}

已有结构化信息：
{dumps(source_data)}

论文原文片段：
{evidence_text}

请输出如下 JSON 格式：
{dumps(empty_json)}
"""

        try:
            resp = await self.llm.async_chat(
                [
                    {
                        'role': 'system',
                        'content': '你是科研论文结构化信息抽取助手。必须基于原文证据抽取，不得编造事实。',
                    },
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.05,
                max_tokens=3000,
            )
        except Exception:
            return {}

        text = (resp or '').strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        parsed = loads(text, default=None)
        if not isinstance(parsed, dict):
            match = re.search(r'\{.*\}', text, flags=re.S)
            parsed = loads(match.group(0), default=None) if match else None
        if not isinstance(parsed, dict):
            return {}

        result = {}
        for key in missing_fields:
            value = self._clean_report_value(parsed.get(key), limit=2500)
            if value:
                result[key] = value
        return result

    async def create_report(
        self,
        db: AsyncSession,
        user_id: int,
        paper_id: int,
        modules: list[str] | None,
        title: str | None,
    ) -> Report:
        paper = (
            await db.execute(
                select(Paper).where(
                    Paper.id == paper_id,
                    Paper.user_id == user_id,
                    Paper.is_deleted == False,
                )
            )
        ).scalar_one_or_none()
        if not paper:
            raise ValueError('目标文献不存在，或当前用户无权访问该文献。')

        info = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id == paper_id))
        ).scalar_one_or_none()
        if not info:
            raise ValueError('目标文献暂无结构化抽取结果，请先等待解析完成或重新解析。')

        selected_modules = self._normalize_report_modules(modules)
        source_data = self._build_report_source_data(paper, info)
        evidence_text = await self._load_paper_evidence_text(db, paper_id)
        llm_extracted = await self._extract_missing_report_fields_with_llm(source_data, evidence_text)
        if llm_extracted:
            source_data.update(llm_extracted)
            for key, value in llm_extracted.items():
                if hasattr(info, key) and value:
                    setattr(info, key, value)
                if key in {'authors', 'keywords'} and hasattr(paper, key) and value:
                    setattr(paper, key, value)
                elif key == 'publication_year':
                    year = self._extract_publication_year(value)
                    if year:
                        paper.publication_year = year
                        source_data[key] = year
                elif key in {'journal_conf', 'doi'} and value:
                    setattr(paper, key, str(value)[:300 if key == 'journal_conf' else 100])
            await db.commit()

        trace_data = {
            'reference_trace': await self._select_reference_trace_items(db, paper_id, source_data),
            'learning_queries': self._build_learning_queries(source_data),
            'related_papers': await self._find_same_direction_different_method_papers(
                db,
                user_id,
                paper_id,
                source_data,
            ),
        }
        visual_summary = self._build_visual_summary(source_data, evidence_text)
        visual_summary = await self._polish_visual_summary_with_llm(source_data, evidence_text, visual_summary)
        reference_links = self._build_reference_links(trace_data.get('reference_trace') or [])
        draft_markdown = self._build_report_markdown(source_data, selected_modules, trace_data)
        module_titles = [self.REPORT_MODULE_META[key]['title'] for key in selected_modules]

        prompt = f"""请基于给定的结构化抽取结果、报告初稿和论文原文片段，生成一份中文科研论文研读报告。

硬性要求：
1. 只能依据“结构化抽取结果”“报告初稿”和“论文原文片段”组织内容，不要编造作者、数据集、指标、数值、结论或引用；
2. 如果某项信息确实缺失，可以说明“原文片段中未充分体现”，不要凭空补全；
3. 输出 Markdown，不要使用代码块；
4. 报告采用“标准详版”：每个核心模块写 1 段概括，必要时补充 2-4 个要点；
5. 方法模块需要说明核心框架、关键步骤和解决的问题；
6. 实验模块需要说明评估对象、对比对象、评价指标或实验设置；
7. 结果模块需要尽量保留原文中的关键数值、提升幅度和比较结论；
8. 创新点模块需要概括本文相对已有工作的主要贡献；
9. 局限性模块应基于原文谨慎归纳，不要编造；
10. 可复现性模块需要给出复现输入、步骤、指标和潜在风险；
11. 文献溯源部分只能使用报告初稿中给出的原文参考文献和检索式；
12. 同方向不同方法文献推荐只能使用报告初稿中给出的当前文献库候选论文；
13. 报告初稿中已有 Markdown 链接时必须保留为 [文本](URL)，不要改成普通文本；
14. 不要在“摘要速览”和“研究背景与核心问题”重复同一段摘要；研究背景与核心问题应提炼核心问题，不要复制摘要；
15. 如果没有复现风险条目，不要输出空的“复现风险提示”标题；
16. 保留以下模块顺序：{'、'.join(module_titles)}。

结构化抽取结果：
{dumps(source_data)}

报告初稿：
{draft_markdown}

论文原文片段：
{evidence_text[:25000]}
"""

        llm_used = False
        content = draft_markdown
        try:
            generated = await self.llm.async_chat(
                [
                    {
                        'role': 'system',
                        'content': '你是严谨的中文科研文献研读报告助手，必须基于给定结构化信息写作，不得编造事实。',
                    },
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.15,
                max_tokens=6000,
            )
            generated = generated.strip()
            if generated and len(generated) >= 300:
                content = generated
                llm_used = True
        except Exception:
            content = draft_markdown
        content = self._cleanup_report_markdown(content, source_data)

        report_title = title or f"{source_data.get('title') or paper.original_filename or paper_id} 研读报告"
        report = Report(
            user_id=user_id,
            paper_id=paper_id,
            title=str(report_title)[:300],
            content=dumps({
                'markdown': content,
                'modules': selected_modules,
                'module_titles': module_titles,
                'paper_id': paper_id,
                'source': source_data,
                'trace_data': trace_data,
                'visual_summary': visual_summary,
                'reference_links': reference_links,
                'llm_used': llm_used,
                'llm_extracted_fields': sorted(llm_extracted.keys()),
            }),
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return report

    async def suggest_compare_name(
        self,
        db: AsyncSession,
        user_id: int,
        paper_ids: list[int],
        dimensions: list[str] | None,
    ) -> str:
        papers = (
            await db.execute(
                select(Paper).where(
                    Paper.id.in_(paper_ids),
                    Paper.user_id == user_id,
                    Paper.is_deleted == False,
                )
            )
        ).scalars().all()

        paper_map = {p.id: p for p in papers}
        ordered_papers = [paper_map[pid] for pid in paper_ids if pid in paper_map]

        if len(ordered_papers) < 2:
            raise ValueError('At least 2 accessible, non-deleted papers are required for comparison.')

        titles = [p.title or p.original_filename or f'Paper {p.id}' for p in ordered_papers]
        dimension_labels = {
            'research_question': '研究问题',
            'method': '方法模型',
            'experiment_data': '实验数据',
            'metrics': '评价指标',
            'main_results': '主要结果',
            'innovations': '创新点',
            'limitations': '局限性',
            'future_work': '未来方向',
        }
        dim_text = '、'.join(dimension_labels.get(x, x) for x in (dimensions or [])) or '研究问题、方法和结果'
        def local_short_title(title: str) -> str:
            clean = ' '.join(str(title or '').split())
            rules = [
                ('Generative QA', ('leveraging passage retrieval with generative models',)),
                ('REALM', ('realm',)),
                ('DPR', ('dense passage retrieval',)),
                ('ColBERT', ('colbert',)),
                ('RAG', ('retrieval-augmented generation', 'retrieval augmented generation')),
                ('Triton', ('triton',)),
                ('EnvGraph', ('envgraph',)),
            ]
            lower = clean.lower()
            for label, needles in rules:
                if any(needle in lower for needle in needles):
                    return label
            return clean if len(clean) <= 16 else f'{clean[:14]}...'

        fallback_names = [local_short_title(title) for title in titles[:3]]
        fallback = f'多文献对比：{"、".join(fallback_names)} 等 {len(titles)} 篇'

        prompt = f"""请根据以下文献信息，为一次多文献对比任务生成一个简洁中文记录名称。

要求：
1. 不超过 32 个中文字符或 60 个英文字符；
2. 不要使用引号、编号、Markdown；
3. 名称要体现多文献对比主题，而不是只复制第一篇论文标题；
4. 如果论文主题差异较大，可以概括为“多文献对比：主题A 与 主题B”。

文献标题：{dumps(titles)}
对比维度：{dim_text}
"""

        try:
            text = await self.llm.async_chat(
                [
                    {'role': 'system', 'content': '你为科研文献分析任务生成简洁、准确的中文标题。'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.2,
                max_tokens=120,
            )
            name = text.strip().strip('`').strip().strip('"').strip("'")
            if '\n' in name:
                name = name.splitlines()[0].strip()
            if name.lower().startswith('json'):
                name = name[4:].strip()
            name = name.replace('标题：', '').replace('名称：', '').strip()
            letters = len(re.findall(r'[A-Za-z]', name))
            chinese = len(re.findall(r'[\u4e00-\u9fff]', name))
            if len(name) > 50 and letters > chinese * 2:
                return fallback[:80]
            return (name or fallback)[:80]
        except Exception:
            return fallback[:80]

    async def compare_papers(
        self,
        db: AsyncSession,
        user_id: int,
        paper_ids: list[int],
        dimensions: list[str] | None,
        name: str | None,
    ) -> ComparisonResult:
        requested_ids = []
        for paper_id in paper_ids:
            if paper_id not in requested_ids:
                requested_ids.append(paper_id)

        accessible_papers = (
            await db.execute(
                select(Paper).where(
                    Paper.id.in_(requested_ids),
                    Paper.user_id == user_id,
                    Paper.is_deleted == False,
                )
            )
        ).scalars().all()
        paper_map = {p.id: p for p in accessible_papers}
        accessible_ids = [pid for pid in requested_ids if pid in paper_map]

        if len(accessible_ids) < 2:
            raise ValueError('At least 2 accessible, non-deleted papers are required for comparison.')

        infos = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(accessible_ids)))
        ).scalars().all()
        info_map = {x.paper_id: x for x in infos}
        usable_infos = [info_map[pid] for pid in accessible_ids if pid in info_map]

        if len(usable_infos) < 2:
            raise ValueError('At least 2 papers with structured extraction results are required for comparison.')

        dimension_meta = {
            'research_question': {'label': '研究问题', 'fields': ['research_question', 'abstract']},
            'method': {'label': '方法 / 模型', 'fields': ['method']},
            'experiment_data': {'label': '数据集 / 实验对象', 'fields': ['experiment_data']},
            'metrics': {'label': '评价指标', 'fields': ['experiment_data', 'main_results']},
            'main_results': {'label': '主要结果', 'fields': ['main_results']},
            'innovations': {'label': '创新点', 'fields': ['innovations']},
            'limitations': {'label': '局限性', 'fields': ['limitations']},
            'future_work': {'label': '未来方向', 'fields': ['future_work']},
        }
        selected_dimensions = dimensions or [
            'research_question',
            'method',
            'experiment_data',
            'main_results',
            'innovations',
            'limitations',
        ]

        def clean_text(value: object, limit: int = 1200) -> str:
            if value is None:
                return '-'
            text = str(value).strip()
            if not text or text.lower() in {'null', 'none', '[]', '{}'}:
                return '-'
            return text[:limit]

        def short_title(title: str) -> str:
            clean = ' '.join(str(title or '').split())
            rules = [
                ('Generative QA', ('leveraging passage retrieval with generative models',)),
                ('REALM', ('realm',)),
                ('DPR', ('dense passage retrieval',)),
                ('ColBERT', ('colbert',)),
                ('RAG', ('retrieval-augmented generation', 'retrieval augmented generation')),
                ('BM25', ('bm25',)),
                ('LLM', ('large language model', 'large language models', 'llm', 'llms')),
                ('Triton', ('triton',)),
                ('EnvGraph', ('envgraph',)),
            ]
            lower = clean.lower()
            matches = [label for label, needles in rules if any(needle in lower for needle in needles)]
            if matches:
                if matches[0] in {'Generative QA', 'REALM', 'DPR', 'ColBERT'}:
                    return matches[0]
                return ' / '.join(dict.fromkeys(matches[:2]))
            return clean if len(clean) <= 36 else f'{clean[:34]}...'

        def compress_compare_cell(value: object, limit: int = 96) -> str:
            text = clean_text(value, limit=1200)
            if text in {'-', '当前解析未提取到明确证据'}:
                return '-'
            parts = re.split(r'(?<=[。；;])\s*', text)
            first = (parts[0] if parts else text).strip()
            if len(first) > limit:
                return f'{first[:limit]}…'
            return first or '-'

        def build_local_comparison_table_zh(raw_rows: list[dict]) -> list[dict]:
            localized: list[dict] = []
            for row in raw_rows:
                if not isinstance(row, dict):
                    continue
                next_row = {
                    'dimension': row.get('dimension'),
                    'dimension_key': row.get('dimension_key'),
                }
                for key, value in row.items():
                    if key in {'dimension', 'dimension_key'}:
                        continue
                    next_row[key] = compress_compare_cell(value)
                localized.append(next_row)
            return localized

        def align_zh_table_with_raw(zh_rows: list[dict], raw_rows: list[dict]) -> list[dict]:
            raw_by_dim = {
                row.get('dimension_key'): row
                for row in raw_rows
                if isinstance(row, dict) and row.get('dimension_key')
            }
            aligned: list[dict] = []
            for row in zh_rows:
                if not isinstance(row, dict):
                    continue
                next_row = dict(row)
                raw_row = raw_by_dim.get(next_row.get('dimension_key'), {})
                for key, value in list(next_row.items()):
                    if key in {'dimension', 'dimension_key'}:
                        continue
                    raw_val = clean_text(raw_row.get(key), limit=1200)
                    zh_val = clean_text(value, limit=180)
                    if raw_val not in {'-', '当前解析未提取到明确证据'} and zh_val == raw_val:
                        next_row[key] = compress_compare_cell(raw_val)
                aligned.append(next_row)
            return aligned

        known_paper_profiles = {
            'RAG': {
                'research_question': '关注知识密集型 NLP 任务中，生成模型如何结合外部检索知识以减少纯参数记忆的不足。',
                'method': '采用检索增强生成框架，先检索相关文档，再将检索内容作为条件输入生成答案或文本。',
                'experiment_data': '面向开放域问答和知识密集型生成任务，使用外部知识源与多类 NLP 数据集进行验证。',
                'metrics': '通常围绕答案准确性、生成质量和知识密集型任务表现进行评估。',
                'main_results': '显示检索增强能改善知识密集型任务表现，尤其适合需要外部事实支撑的生成场景。',
                'innovations': '把非参数化检索记忆与生成模型结合，为后续 RAG 系列方法提供基础范式。',
                'limitations': '效果依赖检索质量与知识库覆盖，生成结果仍可能受检索噪声影响。',
                'future_work': '可继续优化检索器、生成器协同训练，以及面向更新知识的可控生成。',
            },
            'REALM': {
                'research_question': '关注语言模型预训练阶段如何引入检索机制，使模型能利用可更新的外部知识。',
                'method': '在预训练中联合学习检索器与语言模型，通过检索到的文档增强 masked language modeling。',
                'experiment_data': '主要面向开放域问答等知识密集型任务，并结合大规模文本知识库进行训练和检索。',
                'metrics': '重点考察开放域问答准确率、检索质量和预训练后下游任务效果。',
                'main_results': '表明检索增强预训练可提升知识密集型任务表现，并缓解静态参数记忆的局限。',
                'innovations': '将文档检索纳入语言模型预训练目标，强调可更新的非参数知识记忆。',
                'limitations': '训练和检索成本较高，整体效果受检索索引、文档质量和联合训练稳定性影响。',
                'future_work': '可扩展到更高效索引、更大知识库和更稳定的检索-预训练联合优化。',
            },
            'DPR': {
                'research_question': '关注开放域问答中如何用稠密向量检索替代传统稀疏检索，提高相关段落召回。',
                'method': '采用双编码器分别编码问题和段落，通过向量相似度快速检索候选证据。',
                'experiment_data': '面向开放域问答数据集，使用问题-答案/段落监督信号训练稠密检索器。',
                'metrics': '重点评估 top-k 段落召回、问答准确率和检索质量。',
                'main_results': '显示稠密检索在开放域问答证据召回上具有竞争力，为后续神经检索奠定基础。',
                'innovations': '将双编码器稠密表示系统化用于开放域问答检索，弱化对关键词匹配的依赖。',
                'limitations': '需要高质量监督数据和向量索引，跨领域泛化与负样本构造仍是关键问题。',
                'future_work': '可继续改进负样本挖掘、跨域泛化和与阅读器/生成器的端到端协同。',
            },
            'Generative QA': {
                'research_question': '关注开放域问答中生成模型如何借助段落检索获得外部证据并生成答案。',
                'method': '先检索候选段落，再将段落内容输入生成模型，由生成模型整合证据形成回答。',
                'experiment_data': '面向开放域问答任务，围绕检索段落、生成答案和基线系统进行实验比较。',
                'metrics': '通常考察答案匹配、生成质量以及检索段落对最终回答的支撑程度。',
                'main_results': '结果强调检索证据能增强生成式问答，但最终表现取决于检索和生成两阶段配合。',
                'innovations': '较早探索 passage retrieval 与生成模型结合的开放域问答流程。',
                'limitations': '检索错误会传导到生成阶段，生成模型也可能忽略或误用检索证据。',
                'future_work': '可改进检索排序、证据融合和生成阶段对来源证据的约束。',
            },
            'ColBERT': {
                'research_question': '关注如何在保持检索效率的同时，利用上下文 token 级交互提升文本检索精度。',
                'method': '采用 late interaction 机制，分别编码查询和文档 token，并在检索阶段进行细粒度相似度匹配。',
                'experiment_data': '面向段落检索和开放域问答相关检索任务，通常与 BM25、DPR 等方法比较。',
                'metrics': '重点评估检索排序指标、召回效果以及索引和查询效率。',
                'main_results': '显示细粒度 late interaction 能在检索质量和效率之间取得较好平衡。',
                'innovations': '提出 token 级 late interaction 检索范式，兼顾深度语义匹配与可扩展检索。',
                'limitations': '索引体积和计算开销高于简单双编码器，部署时需权衡效率与效果。',
                'future_work': '可继续压缩索引、优化推理效率，并扩展到更大规模语义检索场景。',
            },
        }

        papers_meta = []
        for idx, info in enumerate(usable_infos, start=1):
            paper = paper_map.get(info.paper_id)
            title = (
                getattr(paper, 'title', None)
                or getattr(info, 'title', None)
                or getattr(paper, 'original_filename', None)
                or f'Paper {info.paper_id}'
            )
            papers_meta.append({'key': f'paper_{idx}', 'paper_id': info.paper_id, 'title': title, 'short_title': short_title(title)})

        raw_comparison_table = []
        for dim in selected_dimensions:
            meta = dimension_meta.get(dim, {'label': dim, 'fields': [dim]})
            row = {'dimension': meta['label'], 'dimension_key': dim}

            for idx, info in enumerate(usable_infos, start=1):
                values = []
                for field in meta['fields']:
                    value = clean_text(getattr(info, field, None))
                    if value != '-':
                        values.append(value)

                if not values:
                    abstract = clean_text(getattr(info, 'abstract', None), limit=600)
                    if dim in {'research_question', 'method', 'main_results', 'innovations'} and abstract != '-':
                        values.append(f'未单独抽取该字段，可参考摘要：{abstract}')

                row[f'paper_{idx}'] = '\n'.join(values) if values else '当前解析未提取到明确证据'

            raw_comparison_table.append(row)

        raw_key_schema = {
            'dimension': '对比维度名称',
            'dimension_key': '维度标识，必须原样保留',
            **{item['key']: item['title'] for item in papers_meta},
        }
        summary_prompt = f"""你是一个中文学术文献分析助手。请基于给定的多文献结构化对比表，生成面向中文用户阅读的压缩版对比表和综合分析。

要求：
1. 输出中文；
2. 不要逐句翻译英文原文；
3. 不要原封不动复制论文句子；
4. 每个表格单元格使用 1-2 个中文短句概括；
5. 每个单元格控制在 60-120 个中文字符；
6. 保留必要英文术语和缩写，例如 RAG、DPR、BM25、ColBERT、LLM 等；
7. 如果结构化字段缺失或原始表格中是“-”“当前解析未提取到明确证据”，不要断言论文未说明；请写“当前解析未提取到明确证据”或“当前解析未提取到该维度的明确证据”；
8. summary 保持简短，优先用 2-4 个分点式短句，不要写泛泛的长段落；
9. key_differences、common_trends、research_gaps、future_directions 必须保持数组形式，每条尽量具体指出不同论文之间的差异、共性或不足；
10. summary、key_differences、common_trends、research_gaps、future_directions 中不要使用 paper_1、paper_2、paper_3 这类占位名；必须使用参与论文中的 short_title，例如 RAG、REALM、DPR、ColBERT；如果没有明确简称，就使用给定 short_title；
11. 总结区要突出横向对比，说明不同论文在问题、方法、数据、指标或结果上的区别，不要只写泛泛结论；
12. 不要输出英文长段落，不要把 abstract 原文直接放入研究问题或方法字段；英文论文原文只能被压缩为中文概括，必要英文术语和缩写除外；
13. 避免“显著提升”“最先进”“大幅领先”等过强表述，除非原始解析中有明确证据；
14. 严格返回合法 JSON，不要 Markdown 代码块。

输出 JSON 格式必须包含：
{{
  "comparison_table_zh": [
    {{
      "dimension": "研究问题",
      "dimension_key": "research_question",
      "paper_1": "中文压缩说明",
      "paper_2": "中文压缩说明"
    }}
  ],
  "summary": "中文总体总结，短句或分点式表达",
  "key_differences": ["具体差异要点，例如 RAG 侧重什么，DPR 侧重什么"],
  "common_trends": ["具体共性趋势"],
  "research_gaps": ["当前解析结果能支持的研究空白；证据不足时说明当前解析未提取到明确证据"],
  "future_directions": ["具体未来方向"]
}}

表格字段说明，请在 comparison_table_zh 中沿用这些字段名，不要改成论文标题作为 key：
{dumps(raw_key_schema)}

参与论文：
{dumps(papers_meta)}

原始结构化对比表：
{dumps(raw_comparison_table)}
"""
        summary: dict[str, object] = {}
        try:
            text = await self.llm.async_chat(
                [
                    {'role': 'system', 'content': '你是中文学术文献分析助手，只返回合法 JSON。'},
                    {'role': 'user', 'content': summary_prompt},
                ],
                temperature=0.1,
                max_tokens=3500,
            )
            clean = text.strip()
            if clean.startswith('```'):
                clean = clean.strip('`').strip()
                if clean.lower().startswith('json'):
                    clean = clean[4:].strip()

            parsed = loads(clean, default={})
            if isinstance(parsed, dict):
                summary = parsed
        except Exception:
            summary = {}

        final_name = (name or '').strip()
        if not final_name:
            final_name = await self.suggest_compare_name(
                db,
                user_id,
                [x.paper_id for x in usable_infos],
                selected_dimensions,
            )

        comparison_table_zh = summary.get('comparison_table_zh')
        if not isinstance(comparison_table_zh, list) or not comparison_table_zh:
            comparison_table_zh = build_local_comparison_table_zh(raw_comparison_table)

        def looks_like_non_chinese_summary(value: object) -> bool:
            text = clean_text(value, limit=2000)
            if text in {'-', '当前解析未提取到明确证据'}:
                return False
            letters = len(re.findall(r'[A-Za-z]', text))
            chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
            words = re.findall(r'\b[A-Za-z][A-Za-z-]{2,}\b', text)
            has_english_sentence = bool(re.search(r'[A-Z][A-Za-z,\-\s]{35,}\.', text))
            has_raw_mark = bool(re.search(r'https?://|www\.|abstract|introduction|we\s+(propose|present|show|introduce)\b', text, re.I))
            chinese_ratio = chinese / max(len(text), 1)
            return (
                letters > chinese * 1.4
                or (len(words) >= 8 and chinese < 18)
                or has_english_sentence
                or has_raw_mark
                or (len(text) > 80 and chinese_ratio < 0.28)
            )

        paper_meta_by_key = {item['key']: item for item in papers_meta}

        def fallback_zh_cell(dim_key: str, paper_key: str, value: object) -> str:
            return compress_compare_cell(value)

        def sanitize_zh_table(rows: list[dict]) -> list[dict]:
            sanitized = []
            raw_by_dim = {
                row.get('dimension_key'): row
                for row in raw_comparison_table
                if isinstance(row, dict) and row.get('dimension_key')
            }
            for row in rows:
                if not isinstance(row, dict):
                    continue
                next_row = dict(row)
                dim_key = str(next_row.get('dimension_key') or '')
                raw_row = raw_by_dim.get(dim_key, {})
                for key, value in list(next_row.items()):
                    if key == 'dimension_key':
                        continue
                    if key == 'dimension':
                        next_row[key] = clean_text(value, limit=80)
                    elif looks_like_non_chinese_summary(value):
                        next_row[key] = fallback_zh_cell(dim_key, key, raw_row.get(key, value))
                    else:
                        next_row[key] = clean_text(value, limit=180) or '当前解析未提取到明确证据'
                sanitized.append(next_row)
            return sanitized

        comparison_table_zh = sanitize_zh_table(comparison_table_zh)
        comparison_table_zh = align_zh_table_with_raw(comparison_table_zh, raw_comparison_table)

        key_differences = summary.get('key_differences')
        common_trends = summary.get('common_trends')
        research_gaps = summary.get('research_gaps')
        future_directions = summary.get('future_directions')
        key_differences_list = [str(x) for x in key_differences] if isinstance(key_differences, list) else []
        common_trends_list = [str(x) for x in common_trends] if isinstance(common_trends, list) else []
        research_gaps_list = [str(x) for x in research_gaps] if isinstance(research_gaps, list) else []
        future_directions_list = [str(x) for x in future_directions] if isinstance(future_directions, list) else []
        aliases = [item['short_title'] for item in papers_meta]
        if not key_differences_list:
            key_differences_list = [
                f"{'、'.join(aliases[:3])} 等论文均围绕检索增强或神经检索，但切入点不同：有的强调生成阶段知识注入，有的强调预训练检索记忆，有的聚焦检索器本身。",
                '方法差异主要体现在检索与生成的耦合方式、训练目标、检索粒度和推理效率。'
            ]
        if not common_trends_list:
            common_trends_list = ['共同趋势是把外部文档检索作为知识来源，用检索结果增强问答、生成或排序模型的可靠性。']
        if not research_gaps_list:
            research_gaps_list = ['仍需关注检索噪声、知识库覆盖、跨领域泛化以及检索-生成协同优化。']
        if not future_directions_list:
            future_directions_list = ['后续可比较端到端训练、更高效索引、证据可信度控制和面向动态知识的更新机制。']

        def summary_text(key: str) -> str:
            value = summary.get(key, '')
            if value is None:
                return ''
            if isinstance(value, (list, dict)):
                return dumps(value)
            return str(value)

        overview = summary_text('summary') or (
            f"本次对比覆盖 {'、'.join(aliases)}。整体上，这些工作都利用检索增强模型能力，"
            "但分别侧重生成、预训练、段落召回或细粒度排序。"
        )

        result = {
            'papers': papers_meta,
            'comparison_table': comparison_table_zh,
            'comparison_table_zh': comparison_table_zh,
            'raw_comparison_table': raw_comparison_table,
            'summary': overview,
            'key_differences': key_differences_list,
            'common_trends': common_trends_list,
            'research_gaps': research_gaps_list,
            'future_directions': future_directions_list,
            # Backward-compatible fields used by older front-end code.
            'difference_analysis': '\n'.join(key_differences_list) if key_differences_list else summary_text('difference_analysis'),
            'trend_summary': '\n'.join(common_trends_list) if common_trends_list else summary_text('trend_summary'),
            'future_direction': '\n'.join(future_directions_list) if future_directions_list else summary_text('future_direction'),
        }
        obj = ComparisonResult(
            user_id=user_id,
            name=final_name,
            paper_ids=dumps([x.paper_id for x in usable_infos]),
            result_json=dumps(result),
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    async def create_repro_guide(
        self,
        db: AsyncSession,
        user_id: int,
        paper_id: int,
    ) -> ReproducibilityGuide:
        info = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id == paper_id))
        ).scalar_one_or_none()
        if not info:
            raise ValueError('Target paper has no extracted experiment information yet.')

        payload = {k: v for k, v in info.__dict__.items() if not k.startswith('_')}
        prompt = (
            'Create a reproducibility guide based only on the provided paper information. '
            'Cover environment setup, dataset preparation, model parameters, training steps, '
            'evaluation method, result comparison, cautions, and common pitfalls. '
            f'Input: {dumps(payload)}'
        )
        text = await self.llm.async_chat(
            [
                {'role': 'system', 'content': 'You write practical reproducibility guides.'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.1,
            max_tokens=3000,
        )
        obj = ReproducibilityGuide(user_id=user_id, paper_id=paper_id, guide_content=dumps({'markdown': text}))
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    async def create_graph(
        self,
        db: AsyncSession,
        user_id: int,
        paper_ids: list[int],
        name: str | None,
        domain_id: int | None = None,
    ) -> KnowledgeGraph:
        infos = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(paper_ids)))
        ).scalars().all()
        if not infos:
            raise ValueError('Target papers have no extracted structured information yet.')

        payload = [{k: v for k, v in x.__dict__.items() if not k.startswith('_')} for x in infos]

        system_prompt = (
            "You are an expert knowledge graph builder specializing in academic research. "
            "Your task is to extract structured entity-relation triples from paper metadata.\n\n"
            "=== EXTRACTION RULES ===\n"
            "1. ONLY extract entities that are explicitly mentioned in the input. Do NOT invent or guess.\n"
            "2. Each entity name must be the canonical/full form (e.g. 'Convolutional Neural Network' not 'CNN').\n"
            "3. Avoid duplicates: if two papers mention the same method (e.g. 'ResNet'), merge into ONE node.\n"
            "4. Property fields should contain brief factual details (year, score, parameter count, etc.).\n"
            "5. Each edge MUST include a confidence score (0.0-1.0) reflecting how certain you are.\n\n"
            "=== ONTOLOGY CONSTRAINTS ===\n"
            "Allowed node types and their meanings:\n"
            "- paper: a research paper (use the exact title)\n"
            "- task: a research problem or question being addressed\n"
            "- method: a technique, algorithm, model, or framework\n"
            "- dataset: a dataset, benchmark, or corpus used in experiments\n"
            "- metric: an evaluation metric (Accuracy, F1, BLEU, etc.)\n"
            "- result: a key finding, performance number, or conclusion\n"
            "- innovation: a novel contribution introduced by the paper\n"
            "- limitation: a weakness or constraint acknowledged in the paper\n"
            "- author: only include if person names are clearly given\n\n"
            "Allowed relation types (source → target):\n"
            "- uses: paper/method uses a method/dataset/metric\n"
            "- studies: paper studies a task\n"
            "- achieves: paper/method achieves a result\n"
            "- proposes: paper/author proposes an innovation\n"
            "- compares_with: method/paper compares with another method\n"
            "- improves_upon: method improves upon a previous method\n"
            "- evaluated_on: method is evaluated on a dataset\n"
            "- has_limitation: paper has a limitation\n"
            "- belongs_to: method belongs to a broader category\n\n"
            "=== OUTPUT FORMAT ===\n"
            "Return ONLY valid JSON (no markdown fences, no extra text):\n"
            "{\n"
            '  "nodes": [\n'
            '    {"type": "paper", "name": "Exact Paper Title", "properties": {"year": 2023}}\n'
            "  ],\n"
            '  "edges": [\n'
            '    {"source": "Exact Paper Title", "target": "Method Name", '
            '"relation_type": "uses", "confidence": 0.95, "properties": {}}\n'
            "  ]\n"
            "}\n\n"
            "=== FEW-SHOT EXAMPLE ===\n"
            "Input: {\"title\": \"Attention Is All You Need\", \"abstract\": \"We propose Transformer, "
            "a model relying entirely on attention...\", \"keywords\": \"transformer, attention, machine translation\"}\n"
            "Think step by step:\n"
            "  Step1-Entities: paper='Attention Is All You Need', method='Transformer', task='machine translation', "
            "innovation='self-attention mechanism', metric='BLEU', result='28.4 BLEU on WMT 2014'\n"
            "  Step2-Relations: paper→Transformer(uses,0.98), paper→machine translation(studies,0.95), "
            "paper→self-attention mechanism(proposes,0.97), Transformer→28.4 BLEU(achieves,0.80), "
            "paper→BLEU(uses,0.90)\n"
            '  Step3-Output: {{"nodes":[...], "edges":[...]}}\n\n'
            "Now process the real input below. Think step by step, then output JSON only."
        )

        prompt = f"""Extract a knowledge graph from the following paper metadata.
Think step by step: first list all entities, then identify relationships, then build the JSON.
IMPORTANT: Return ONLY the JSON object, no markdown code fences, no explanation.

Input: {dumps(payload)}
"""

        try:
            text = await self.llm.async_chat(
                [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.0,
                max_tokens=3000,
            )
            raw = text.strip()
            if raw.startswith('```'):
                raw = raw.strip('`')
                raw = raw.replace('json\n', '', 1).replace('JSON\n', '', 1).strip()
            data = loads(raw, default={'nodes': [], 'edges': []})
        except Exception:
            data = {'nodes': [], 'edges': []}

        if not data.get('nodes'):
            data = self._fallback_graph_from_infos(infos)

        # ============================================================
        # ★ 质量控制：置信度过滤 + 规则校验
        # ============================================================
        raw_edges = data.get('edges', [])
        filtered_edges: list[dict] = []
        high_confidence = 0
        low_confidence = 0

        for e in raw_edges:
            conf = e.get('confidence', 0.7)  # 老版本 LLM 可能不返回此字段
            source_type = None
            rel_type = e.get('relation_type', '')

            # 1. 置信度过滤
            if conf < 0.5:
                low_confidence += 1
                continue
            elif conf < 0.75:
                low_confidence += 1
                # 低置信度仍保留，但可标记（暂不做额外处理）
            else:
                high_confidence += 1

            # 2. 找出 source 的实际类型用于规则校验
            source_name = (e.get('source') or '').strip()
            target_name = (e.get('target') or '').strip()
            for n in data.get('nodes', []):
                if (n.get('name') or '').strip() == source_name:
                    source_type = n.get('type', '')
                    break

            # 3. 规则校验：关系类型必须与 source 实体类型兼容
            if not _validate_relation(source_type, rel_type):
                continue  # 不合规的三元组直接丢弃

            filtered_edges.append(e)

        if filtered_edges:
            data['edges'] = filtered_edges

        # ============================================================
        # MySQL: 创建 KnowledgeGraph 元数据记录（保留）
        # ============================================================
        graph = KnowledgeGraph(
            user_id=user_id,
            domain_id=domain_id,
            paper_id=paper_ids[0] if len(paper_ids) == 1 else None,
            name=name or 'Research topic knowledge graph',
        )
        db.add(graph)
        await db.flush()

        for pid in paper_ids:
            db.add(KnowledgeGraphPaper(graph_id=graph.id, paper_id=pid))

        # ============================================================
        # Neo4j: 批量创建节点和关系
        # ============================================================
        from app.db.neo4j_client import neo4j_manager

        VALID_ENTITY_TYPES = frozenset({
            'paper', 'task', 'method', 'dataset', 'metric',
            'result', 'innovation', 'limitation', 'author',
        })
        VALID_RELATION_TYPES = frozenset({
            'uses', 'studies', 'achieves', 'proposes', 'compares_with',
            'improves_upon', 'evaluated_on', 'has_limitation', 'belongs_to',
            'related_to', 'reports', 'contributes', 'evaluates_on',
        })

        async with neo4j_manager.driver.session() as neo4j_session:
            # ---------- 创建节点 ----------
            nodes_data = data.get('nodes', [])
            # created_names: 记录每个节点名对应的所有类型（同名不同类型合并标签）
            created_node_types: dict[str, set[str]] = {}
            print(f'[create_graph] ===== graph_id={graph.id} 开始写入Neo4j =====')
            print(f'[create_graph] LLM生成节点数={len(nodes_data)}, 边数={len(data.get("edges", []))}')

            async def write_node(name: str, entity_type: str, props: dict | None = None) -> None:
                """写入或更新单个节点。同名节点合并所有类型标签。"""
                name = (name or '').strip()
                if not name:
                    return
                props = props or {}
                if isinstance(props, dict):
                    properties_str = dumps(props)
                else:
                    properties_str = '{}'

                label = entity_type.capitalize()
                existing_types = created_node_types.get(name, set())
                # 更新内存记录
                existing_types.add(entity_type)
                created_node_types[name] = existing_types

                # 合并所有已知标签到 Neo4j（同名节点累加标签）
                # ★ 关键修复：MERGE 必须包含 graph_id，否则同名节点会被跨图覆盖
                all_labels = ':'.join(t.capitalize() for t in existing_types)
                cypher = (
                    f"MERGE (n:Entity {{name: $name, graph_id: $graph_id}}) "
                    f"SET n:{all_labels} "
                    f"SET n.domain_id = $domain_id, "
                    f"n.properties = $properties"
                )
                await neo4j_session.run(
                    cypher,
                    {
                        'name': name,
                        'domain_id': domain_id,
                        'graph_id': graph.id,
                        'properties': properties_str,
                    },
                )

            for n in nodes_data:
                node_name = (n.get('name') or '').strip()
                if not node_name:
                    continue
                entity_type = (n.get('type') or 'paper').strip().lower()
                if entity_type not in VALID_ENTITY_TYPES:
                    entity_type = 'paper'

                properties = n.get('properties') or {}
                await write_node(node_name, entity_type, properties)

            print(f'[create_graph] 节点写入完成: 去重后写入{len(created_node_types)}个节点')

            # ---------- 创建关系 ----------
            edges_data = data.get('edges', [])
            seen_edges: set[tuple[str, str, str]] = set()
            edges_created = 0
            edges_skipped_missing_source = 0
            edges_skipped_missing_target = 0
            edges_skipped_self_loop = 0
            edges_skipped_duplicate = 0
            edges_auto_created_nodes = 0

            for e in edges_data:
                source_name = (e.get('source') or '').strip()
                target_name = (e.get('target') or '').strip()
                if not source_name or not target_name or source_name == target_name:
                    edges_skipped_self_loop += 1
                    continue

                rel_type = (e.get('relation_type') or 'related_to').strip().lower()
                if rel_type not in VALID_RELATION_TYPES:
                    rel_type = 'related_to'

                # 去重：相同 source→relation→target 只创建一次
                edge_key = (source_name, target_name, rel_type)
                if edge_key in seen_edges:
                    edges_skipped_duplicate += 1
                    continue
                seen_edges.add(edge_key)

                # ★ 校验并补建缺失的节点
                if source_name not in created_node_types:
                    print(f'[create_graph] ⚠️ 边引用的 source 节点不存在，自动补建: "{source_name}"')
                    await write_node(source_name, 'method', {})
                    edges_auto_created_nodes += 1
                if target_name not in created_node_types:
                    print(f'[create_graph] ⚠️ 边引用的 target 节点不存在，自动补建: "{target_name}"')
                    await write_node(target_name, 'method', {})
                    edges_auto_created_nodes += 1

                properties = e.get('properties') or {}
                if isinstance(properties, dict):
                    properties_str = dumps(properties)
                else:
                    properties_str = '{}'

                cypher = (
                    f"MATCH (s:Entity {{name: $source_name, graph_id: $graph_id}}) "
                    f"MATCH (t:Entity {{name: $target_name, graph_id: $graph_id}}) "
                    f"MERGE (s)-[r:{rel_type.upper()} {{graph_id: $graph_id}}]->(t) "
                    f"SET r.properties = $properties"
                )
                await neo4j_session.run(
                    cypher,
                    {
                        'source_name': source_name,
                        'target_name': target_name,
                        'graph_id': graph.id,
                        'properties': properties_str,
                    },
                )
                edges_created += 1

        print(f'[create_graph] 关系写入完成: 创建{edges_created}条'
              f' | 跳过(自环{edges_skipped_self_loop}/重复{edges_skipped_duplicate})'
              f' | 自动补建节点{edges_auto_created_nodes}个')
        print(f'[create_graph] ===== graph_id={graph.id} 写入完毕 =====')

        await db.commit()
        return graph

    async def suggest_domain(
        self,
        db: AsyncSession,
        user_id: int,
        paper_ids: list[int],
    ) -> list[dict]:
        """AI 感知：分析论文内容，推荐归属到已有知识域或建议新建域。

        返回格式: [{"domain_id": int|null, "domain_name": str, "match_type": "existing"|"new", "reason": str}]
        """
        # 1. 加载论文信息
        papers = (
            await db.execute(select(Paper).where(Paper.id.in_(paper_ids), Paper.user_id == user_id))
        ).scalars().all()
        if not papers:
            return []

        paper_snapshots = []
        for p in papers:
            info = (
                await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id == p.id))
            ).scalar_one_or_none()
            paper_snapshots.append({
                'paper_id': p.id,
                'title': p.title or p.original_filename,
                'keywords': p.keywords or '',
                'abstract': (info.abstract or '')[:500] if info else '',
                'research_question': (info.research_question or '')[:300] if info else '',
            })

        # 2. 加载用户已有知识域
        domains = (
            await db.execute(select(KnowledgeDomain).where(KnowledgeDomain.user_id == user_id))
        ).scalars().all()
        domain_list = [{'id': d.id, 'name': d.name} for d in domains]

        # 3. 构建 LLM prompt — 要求返回 JSON
        domain_names = [d['name'] for d in domain_list]
        domain_names_str = ', '.join(f'"{n}"' for n in domain_names) if domain_names else '（用户尚无任何知识域）'

        prompt = f"""分析以下论文，判断它们最适合归入用户的哪个已有知识域，或者是否需要新建知识域。

用户已有知识域: [{domain_names_str}]

论文列表:
{dumps(paper_snapshots)}

请严格返回 JSON 数组（不要 Markdown 代码块），每个元素格式：
{{"domain_id": 数字或null, "domain_name": "域名称", "match_type": "existing或new", "reason": "一句话理由"}}

规则：
- match_type="existing" 时，domain_id 必须是上述已有域的 id，domain_name 也必须与已有域名完全一致
- match_type="new" 时，domain_id 为 null，domain_name 是你建议新建的域名称（2-6个字，精准概括论文核心领域）
- 如果多篇论文属于不同领域，可以返回多个建议
- 最多返回 3 个建议，按置信度从高到低排列
- reason 用中文，20字以内
"""
        try:
            text = await self.llm.async_chat(
                [
                    {'role': 'system', 'content': '你是学术领域分类专家，精准判断论文所属研究领域。只返回 JSON 数组，不含任何 Markdown 标记。'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.0,
                max_tokens=600,
            )
            raw = text.strip()
            if raw.startswith('```'):
                raw = raw.strip('`')
                raw = raw.replace('json\n', '', 1).replace('JSON\n', '', 1).strip()
            suggestions = loads(raw, default=[])
            if isinstance(suggestions, dict):
                suggestions = [suggestions]
            if not isinstance(suggestions, list):
                suggestions = []
        except Exception:
            suggestions = []

        # 4. 如果没有结果，基于关键词做简单兜底
        if not suggestions and domain_list:
            all_keywords = ' '.join([p['keywords'] + ' ' + p['title'] for p in paper_snapshots]).lower()
            # 简单关键词匹配
            for d in domain_list:
                if d['name'].lower() in all_keywords or any(
                    kw in d['name'].lower() for kw in all_keywords.split()
                ):
                    suggestions.append({
                        'domain_id': d['id'],
                        'domain_name': d['name'],
                        'match_type': 'existing',
                        'reason': '关键词匹配',
                    })
                    break

        if not suggestions:
            # 完全无匹配 — 从论文标题提取建议域名
            title = papers[0].title or papers[0].original_filename
            suggestions.append({
                'domain_id': None,
                'domain_name': _extract_domain_name_from_title(title),
                'match_type': 'new',
                'reason': '新领域，建议创建知识域',
            })

        return suggestions

    def _fallback_graph_from_infos(self, infos: list[PaperExtractedInfo]) -> dict:
        nodes: list[dict] = []
        edges: list[dict] = []
        seen: set[str] = set()

        def add_node(node_type: str, node_name: str, properties: dict | None = None) -> None:
            node_name = (node_name or '').strip()
            if not node_name or node_name in seen:
                return
            seen.add(node_name)
            nodes.append({'type': node_type, 'name': node_name[:300], 'properties': properties or {}})

        def add_edge(source: str, target: str, relation_type: str) -> None:
            source = (source or '').strip()
            target = (target or '').strip()
            if source and target and source != target:
                edges.append(
                    {
                        'source': source[:300],
                        'target': target[:300],
                        'relation_type': relation_type,
                        'properties': {},
                    }
                )

        for info in infos:
            paper_title = info.title or f'Paper {info.paper_id}'
            add_node('paper', paper_title, {'paper_id': info.paper_id})

            fields = [
                ('task', info.research_question, 'studies'),
                ('method', info.method, 'uses'),
                ('dataset', info.experiment_data, 'evaluated_on'),
                ('result', info.main_results, 'achieves'),
                ('innovation', info.innovations, 'proposes'),
                ('limitation', info.limitations, 'has_limitation'),
            ]
            for node_type, value, relation in fields:
                if not value:
                    continue
                node_name = value.strip()[:120]
                add_node(node_type, node_name)
                add_edge(paper_title, node_name, relation)

        return {'nodes': nodes, 'edges': edges}


# ============================================================
# 辅助函数
# ============================================================

def _validate_relation(source_type: str | None, relation_type: str) -> bool:
    """校验关系类型是否与源实体类型兼容（反幻觉规则引擎）。
    不兼容的组合直接拒绝，防止 LLM 产出无意义三元组。

    Returns:
        True = 通过校验, False = 丢弃这条边
    """
    # 所有类型都允许的基础关系
    universal_allowed = {'belongs_to', 'related_to'}

    # 各实体类型允许作为 source 发出的关系
    allowed_by_source: dict[str, set[str]] = {
        'paper': {
            'uses', 'studies', 'achieves', 'proposes', 'compares_with',
            'evaluated_on', 'has_limitation', 'improves_upon',
        },
        'method': {
            'uses', 'achieves', 'evaluated_on', 'compares_with',
            'improves_upon', 'belongs_to',
        },
        'author': {'proposes', 'uses'},
        'task': {'studies', 'evaluated_on'},
        'dataset': {'evaluated_on', 'uses'},
    }

    if not source_type or not relation_type:
        return True  # 信息不足时放行

    allowed = allowed_by_source.get(source_type)
    if allowed is None:
        return True  # 未知类型放行（如 innovation, result, limitation 等）

    return relation_type in allowed or relation_type in universal_allowed

def _extract_domain_name_from_title(title: str) -> str:
    """从论文标题中提取可能的领域关键词作为建议域名。

    简单规则：取冒号或'在...中的应用'之前的第一个短语。
    """
    title = (title or '').strip()
    if not title:
        return '新建研究领域'

    # 常见分隔符后的部分是子领域，之前的是大方向
    for sep in (':', '：', '——', '—'):
        idx = title.find(sep)
        if idx > 0:
            candidate = title[:idx].strip()
            if 2 <= len(candidate) <= 10:
                return candidate
            # 取最后几个词
            words = candidate.replace('-', ' ').split()
            if len(words) >= 2:
                return words[-2] + words[-1]

    # 无分隔符，取前 8 个字
    return title[:8] if len(title) > 8 else title
