from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GraphEdge,
    GraphNode,
    KnowledgeDomain,
    KnowledgeGraph,
    KnowledgeGraphPaper,
    Paper,
    PaperExtractedInfo,
)
from app.utils.json_utils import dumps, loads


@dataclass
class PaperBundle:
    paper: Paper
    info: PaperExtractedInfo | None


class LiteratureGraphService:
    """Builds a local paper-to-paper literature graph.

    One node represents one uploaded paper. One edge represents the relationship
    between two papers inside the user's own library. The implementation is
    deterministic and does not depend on external paper databases, which keeps
    the demo stable.
    """

    STOPWORDS = {
        'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'about', 'using',
        'based', 'paper', 'papers', 'method', 'methods', 'model', 'models', 'approach',
        'study', 'studies', 'task', 'tasks', 'result', 'results', 'analysis', 'propose',
        'proposed', 'show', 'shows', 'via', 'are', 'was', 'were', 'has', 'have', 'had',
        '研究', '方法', '模型', '论文', '系统', '结果', '实验', '基于', '提出', '本文',
        '通过', '进行', '一种', '分析', '实现', '利用', '采用', '问题', '任务', '数据',
    }

    @staticmethod
    def _clean(value: Any, limit: int = 4000) -> str:
        if value is None:
            return ''
        if isinstance(value, (list, tuple, set)):
            text = '、'.join(str(x).strip() for x in value if str(x).strip())
        elif isinstance(value, dict):
            text = '；'.join(f'{k}：{v}' for k, v in value.items() if str(v).strip())
        else:
            text = str(value).strip()
            if text.startswith(('[', '{')):
                parsed = loads(text, default=None)
                if parsed is not None:
                    return LiteratureGraphService._clean(parsed, limit)
        text = ' '.join(text.split())
        if text.lower() in {'none', 'null', 'nan', '[]', '{}'}:
            return ''
        return text[:limit]

    @classmethod
    def _tokens(cls, text: Any) -> set[str]:
        raw = cls._clean(text, 12000).lower()
        if not raw:
            return set()
        words = set(re.findall(r'[a-z][a-z0-9_+\-.]{2,}', raw))
        # Chinese segments: keep short terms and bigrams for rough similarity.
        for chunk in re.findall(r'[\u4e00-\u9fff]{2,}', raw):
            if len(chunk) <= 6:
                words.add(chunk)
            else:
                for i in range(0, min(len(chunk) - 1, 30)):
                    words.add(chunk[i:i + 2])
        return {w for w in words if w not in cls.STOPWORDS and len(w) >= 2}

    @classmethod
    def _jaccard(cls, a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / max(1, len(a | b))

    @classmethod
    def _parse_terms(cls, value: Any, limit: int = 12) -> list[str]:
        text = cls._clean(value, 2000)
        if not text:
            return []
        parsed = loads(text, default=None) if text.startswith(('[', '{')) else None
        if isinstance(parsed, list):
            candidates = [cls._clean(x, 80) for x in parsed]
        else:
            candidates = re.split(r'[;,，；、\n]+', text)
        seen: set[str] = set()
        terms: list[str] = []
        for item in candidates:
            term = cls._clean(item, 80).strip(' .;；,，、')
            key = term.lower()
            if not term or key in seen:
                continue
            seen.add(key)
            terms.append(term)
            if len(terms) >= limit:
                break
        return terms

    @classmethod
    def _paper_title(cls, paper: Paper, info: PaperExtractedInfo | None) -> str:
        return cls._clean((info.title if info else None) or paper.title or paper.original_filename, 300)

    @classmethod
    def _authors_text(cls, paper: Paper, info: PaperExtractedInfo | None) -> str:
        return cls._clean((info.authors if info else None) or paper.authors, 500)

    @classmethod
    def _first_author_label(cls, authors: str, fallback_title: str) -> str:
        if authors:
            parts = re.split(r'[;,，；、]|\band\b', authors)
            first = cls._clean(parts[0], 40)
            if first:
                # English names: keep last token. Chinese names: keep full short name.
                if re.search(r'[A-Za-z]', first):
                    tokens = first.replace('.', ' ').split()
                    return tokens[-1] if tokens else first
                return first[:6]
        title_token = cls._clean(fallback_title, 40)
        return title_token[:10] or 'Unknown'

    @classmethod
    def _bundle_to_snapshot(cls, bundle: PaperBundle) -> dict[str, Any]:
        paper, info = bundle.paper, bundle.info
        title = cls._paper_title(paper, info)
        authors = cls._authors_text(paper, info)
        year = paper.publication_year
        keywords = cls._parse_terms((info.keywords if info else None) or paper.keywords)
        abstract = cls._clean(info.abstract if info else '', 3000)
        research_question = cls._clean(info.research_question if info else '', 2000)
        method = cls._clean(info.method if info else '', 2000)
        main_results = cls._clean(info.main_results if info else '', 1600)
        innovations = cls._clean(info.innovations if info else '', 1600)
        label = f"{cls._first_author_label(authors, title)}, {year or 'Unknown'}"
        text_all = ' '.join([title, abstract, ' '.join(keywords), research_question, method, main_results, innovations])
        return {
            'paper_id': paper.id,
            'title': title,
            'name': title,
            'label': label,
            'authors': authors,
            'year': year,
            'journal_conf': cls._clean(paper.journal_conf, 200),
            'doi': cls._clean(paper.doi, 120),
            'keywords': keywords,
            'abstract': abstract,
            'research_question': research_question,
            'method': method,
            'main_results': main_results,
            'innovations': innovations,
            'parse_status': paper.parse_status,
            'tokens_all': cls._tokens(text_all),
            'tokens_title': cls._tokens(title),
            'tokens_keywords': {k.lower() for k in keywords},
            'tokens_method': cls._tokens(method),
        }

    @classmethod
    def _score_pair(cls, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        title_score = cls._jaccard(a['tokens_title'], b['tokens_title'])
        content_score = cls._jaccard(a['tokens_all'], b['tokens_all'])
        keyword_overlap = sorted(a['tokens_keywords'] & b['tokens_keywords'])
        keyword_base = max(1, min(len(a['tokens_keywords']), len(b['tokens_keywords'])))
        keyword_score = min(1.0, len(keyword_overlap) / keyword_base)
        method_score = cls._jaccard(a['tokens_method'], b['tokens_method'])

        year_a, year_b = a.get('year'), b.get('year')
        if year_a and year_b:
            year_gap = abs(int(year_a) - int(year_b))
            year_score = max(0.0, 1 - year_gap / 8)
        else:
            year_gap = None
            year_score = 0.0

        score = (
            0.45 * content_score +
            0.25 * keyword_score +
            0.18 * method_score +
            0.07 * title_score +
            0.05 * year_score
        )

        # If two papers share explicit keywords, keep the edge visible even when
        # abstracts are short or missing.
        if keyword_overlap:
            score = max(score, min(0.72, 0.26 + 0.10 * len(keyword_overlap)))
        if content_score > 0.08:
            score = max(score, 0.22 + content_score)
        score = round(min(score, 1.0), 3)

        if score >= 0.60:
            strength = 'strong'
        elif score >= 0.35:
            strength = 'medium'
        else:
            strength = 'weak'

        relation_types: list[str] = []
        if content_score >= 0.06:
            relation_types.append('语义相似')
        if keyword_overlap:
            relation_types.append('关键词重合')
        if method_score >= 0.05:
            relation_types.append('方法相近')
        if year_score >= 0.75 and score >= 0.20:
            relation_types.append('时间邻近')
        if not relation_types:
            relation_types.append('弱相关')

        if '关键词重合' in relation_types:
            relation_type = 'keyword_overlap'
        elif '方法相近' in relation_types:
            relation_type = 'method_similarity'
        elif '语义相似' in relation_types:
            relation_type = 'semantic_similarity'
        else:
            relation_type = 'weak_relation'

        shared_terms = sorted((a['tokens_all'] & b['tokens_all']) - set(keyword_overlap), key=lambda x: (-len(x), x))[:8]
        readable_keywords = [kw for kw in a['keywords'] if kw.lower() in set(keyword_overlap)]
        if not readable_keywords:
            readable_keywords = keyword_overlap[:6]

        if strength == 'strong':
            level_text = '强关联'
        elif strength == 'medium':
            level_text = '中等关联'
        else:
            level_text = '弱关联'

        basis = '、'.join(relation_types)
        shared = '、'.join(readable_keywords[:6] or shared_terms[:6])
        if shared:
            explanation = f'两篇论文形成{level_text}，主要依据为{basis}；共同线索包括：{shared}。'
        else:
            explanation = f'两篇论文形成{level_text}，主要依据为{basis}。由于可用摘要或关键词较少，该关系建议作为弱线索参考。'

        return {
            'score': score,
            'strength': strength,
            'relation_type': relation_type,
            'relation_types': relation_types,
            'shared_keywords': readable_keywords[:8],
            'shared_terms': shared_terms,
            'year_gap': year_gap,
            'explanation': explanation,
            'difference': cls._build_difference(a, b),
            'raw_scores': {
                'title': round(title_score, 3),
                'content': round(content_score, 3),
                'keyword': round(keyword_score, 3),
                'method': round(method_score, 3),
                'year': round(year_score, 3),
            },
        }

    @classmethod
    def _build_difference(cls, a: dict[str, Any], b: dict[str, Any]) -> str:
        ma = cls._clean(a.get('method'), 180)
        mb = cls._clean(b.get('method'), 180)
        if ma and mb and ma != mb:
            return f'差异上，前者的方法侧重于“{ma[:70]}”，后者的方法侧重于“{mb[:70]}”。'
        ya, yb = a.get('year'), b.get('year')
        if ya and yb and ya != yb:
            earlier = a if ya < yb else b
            later = b if ya < yb else a
            return f'时间上，{earlier["label"]} 更早，{later["label"]} 更新，可作为研究演化线索查看。'
        return '两篇论文的差异需要结合原文方法、实验设置和研究问题进一步阅读。'

    async def _load_bundles(self, db: AsyncSession, user_id: int, paper_ids: list[int]) -> list[PaperBundle]:
        unique_ids = list(dict.fromkeys(int(x) for x in paper_ids))
        papers = (
            await db.execute(
                select(Paper).where(Paper.user_id == user_id, Paper.is_deleted == False, Paper.id.in_(unique_ids))
            )
        ).scalars().all()
        paper_map = {p.id: p for p in papers}
        infos = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(unique_ids)))
        ).scalars().all()
        info_map = {i.paper_id: i for i in infos}
        return [PaperBundle(paper_map[pid], info_map.get(pid)) for pid in unique_ids if pid in paper_map]

    @classmethod
    def _select_edges(cls, snapshots: list[dict[str, Any]], include_weak: bool) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for a, b in combinations(snapshots, 2):
            meta = cls._score_pair(a, b)
            scored.append({'source_paper_id': a['paper_id'], 'target_paper_id': b['paper_id'], **meta})
        scored.sort(key=lambda x: x['score'], reverse=True)

        n = len(snapshots)
        threshold = 0.08 if n <= 4 and include_weak else 0.20 if n <= 4 else 0.18 if include_weak else 0.35
        max_edges = min(len(scored), max(n + 2, n * 3, 18)) if n > 4 else len(scored)

        selected_by_pair: dict[tuple[int, int], dict[str, Any]] = {}

        def add_edge(edge: dict[str, Any], force_weak: bool = False) -> None:
            a = int(edge['source_paper_id'])
            b = int(edge['target_paper_id'])
            key = (min(a, b), max(a, b))
            if force_weak:
                edge['_backbone'] = True
                edge['strength'] = 'weak'
                if '弱相关' not in edge['relation_types']:
                    edge['relation_types'].append('弱相关')
                if not edge.get('explanation') or '弱' not in edge['explanation']:
                    edge['explanation'] = f"{edge.get('explanation', '')} 该关系为低置信度弱连接，用于避免本地文献数量较少时图谱断裂。".strip()
            selected_by_pair[key] = edge

        for edge in scored:
            if edge['score'] >= threshold:
                add_edge(edge)
            if len(selected_by_pair) >= max_edges:
                break

        # 本地文献库数量通常较少。即使没有强关系，也为每篇论文保留一条最佳弱连接，
        # 避免页面出现孤立节点或空白图，同时在摘要和边解释中提示关系较弱。
        covered: set[int] = set()
        for edge in selected_by_pair.values():
            covered.add(int(edge['source_paper_id']))
            covered.add(int(edge['target_paper_id']))
        for snapshot in snapshots:
            pid = int(snapshot['paper_id'])
            if pid in covered:
                continue
            best = next((edge for edge in scored if pid in {int(edge['source_paper_id']), int(edge['target_paper_id'])}), None)
            if best:
                add_edge(best, force_weak=True)
                covered.add(int(best['source_paper_id']))
                covered.add(int(best['target_paper_id']))

        if not selected_by_pair and scored:
            for edge in scored[:max(1, min(n - 1, len(scored)))]:
                add_edge(edge, force_weak=True)

        rows = list(selected_by_pair.values())
        backbone = [edge for edge in rows if edge.pop('_backbone', False)]
        regular = [edge for edge in rows if edge not in backbone]
        regular.sort(key=lambda x: x['score'], reverse=True)
        return (backbone + regular)[:max_edges]

    @classmethod
    def _build_summary(cls, graph: KnowledgeGraph, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
        strong = sum(1 for e in edges if e.get('strength') == 'strong')
        weak = sum(1 for e in edges if e.get('strength') == 'weak')
        years = [n.get('year') for n in nodes if n.get('year')]
        keyword_counter: Counter[str] = Counter()
        for n in nodes:
            for kw in n.get('keywords') or []:
                keyword_counter[kw] += 1
        themes = [k for k, _ in keyword_counter.most_common(6)]
        core = sorted(nodes, key=lambda n: n.get('centrality', 0), reverse=True)[:3]
        if len(nodes) < 2:
            status_hint = '当前图谱至少需要 2 篇论文才能形成论文间关系。'
        elif not edges:
            status_hint = '未发现可展示的论文关系，建议增加同主题论文或使用弱关联模式重新生成。'
        elif strong == 0:
            status_hint = '未发现强关联关系，已按弱连接展示。这些论文可能分属不同研究方向，可作为拆分主题或补充文献的参考。'
        elif len(nodes) <= 4:
            status_hint = '当前文献数量较少，已生成紧凑关系图，建议重点查看右侧关系解释。'
        else:
            status_hint = '图谱已根据本地文献库生成论文关系网络，可通过节点和边查看研究脉络。'
        return {
            'paper_count': len(nodes),
            'relation_count': len(edges),
            'strong_count': strong,
            'weak_count': weak,
            'topic_count': min(3, max(1, len(themes))) if nodes else 0,
            'themes': themes,
            'core_papers': [{'paper_id': n.get('paper_id'), 'title': n.get('title'), 'label': n.get('label')} for n in core],
            'year_range': [min(years), max(years)] if years else None,
            'status_hint': status_hint,
            'description': '节点代表论文，节点大小表示本地图谱中心性，节点颜色表示发表年份，边表示论文之间的语义、关键词和方法关联。',
        }

    async def create_graph(
        self,
        db: AsyncSession,
        user_id: int,
        paper_ids: list[int],
        name: str | None,
        domain_id: int | None = None,
        build_mode: str = 'fast',
        include_weak: bool = True,
    ) -> KnowledgeGraph:
        bundles = await self._load_bundles(db, user_id, paper_ids)
        if len(bundles) < 2:
            raise ValueError('至少选择 2 篇文献才能生成文献关系图谱。')
        if domain_id is not None:
            domain = await db.get(KnowledgeDomain, domain_id)
            if not domain or domain.user_id != user_id:
                raise ValueError('研究主题不存在。')

        snapshots = [self._bundle_to_snapshot(b) for b in bundles]
        edges_data = self._select_edges(snapshots, include_weak=include_weak)

        centrality: dict[int, float] = {s['paper_id']: 0.0 for s in snapshots}
        degree: dict[int, int] = {s['paper_id']: 0 for s in snapshots}
        for edge in edges_data:
            centrality[edge['source_paper_id']] += edge['score']
            centrality[edge['target_paper_id']] += edge['score']
            degree[edge['source_paper_id']] += 1
            degree[edge['target_paper_id']] += 1
        max_centrality = max(centrality.values() or [1.0]) or 1.0

        for s in snapshots:
            c = centrality.get(s['paper_id'], 0.0) / max_centrality
            s['centrality'] = round(c, 3)
            s['degree'] = degree.get(s['paper_id'], 0)
            s['size'] = round(26 + 30 * math.sqrt(c), 1)
            for internal_key in ['tokens_all', 'tokens_title', 'tokens_keywords', 'tokens_method']:
                s.pop(internal_key, None)

        graph = KnowledgeGraph(
            user_id=user_id,
            domain_id=domain_id,
            paper_id=None,
            name=name or '未命名文献关系图谱',
        )
        db.add(graph)
        await db.flush()

        for snapshot in snapshots:
            db.add(KnowledgeGraphPaper(graph_id=graph.id, paper_id=snapshot['paper_id']))

        node_rows: dict[int, GraphNode] = {}
        for snapshot in snapshots:
            row = GraphNode(
                graph_id=graph.id,
                entity_type='paper',
                name=snapshot['title'],
                properties=dumps({**snapshot, 'build_mode': build_mode}),
                embedding_vector=None,
            )
            db.add(row)
            await db.flush()
            node_rows[snapshot['paper_id']] = row

        for edge in edges_data:
            source = node_rows.get(edge['source_paper_id'])
            target = node_rows.get(edge['target_paper_id'])
            if not source or not target:
                continue
            props = {k: v for k, v in edge.items() if k not in {'source_paper_id', 'target_paper_id', 'relation_type'}}
            db.add(GraphEdge(
                graph_id=graph.id,
                source_node_id=source.id,
                target_node_id=target.id,
                relation_type=edge['relation_type'],
                properties=dumps(props),
            ))

        await db.commit()
        await db.refresh(graph)
        return graph

    async def regenerate_graph(
        self,
        db: AsyncSession,
        user_id: int,
        graph_id: int,
        build_mode: str = 'fast',
        include_weak: bool = True,
    ) -> KnowledgeGraph:
        graph = await db.get(KnowledgeGraph, graph_id)
        if not graph or graph.user_id != user_id:
            raise ValueError('文献图谱不存在。')

        paper_ids = (
            await db.execute(
                select(KnowledgeGraphPaper.paper_id).where(KnowledgeGraphPaper.graph_id == graph_id)
            )
        ).scalars().all()
        if len(paper_ids) < 2:
            raise ValueError('图谱内论文不足，无法重新生成。')

        bundles = await self._load_bundles(db, user_id, list(paper_ids))
        if len(bundles) < 2:
            raise ValueError('原始论文不足或已被删除，无法重新生成。')

        snapshots = [self._bundle_to_snapshot(b) for b in bundles]
        edges_data = self._select_edges(snapshots, include_weak=include_weak)

        centrality: dict[int, float] = {s['paper_id']: 0.0 for s in snapshots}
        degree: dict[int, int] = {s['paper_id']: 0 for s in snapshots}
        for edge in edges_data:
            centrality[edge['source_paper_id']] += edge['score']
            centrality[edge['target_paper_id']] += edge['score']
            degree[edge['source_paper_id']] += 1
            degree[edge['target_paper_id']] += 1
        max_centrality = max(centrality.values() or [1.0]) or 1.0

        for s in snapshots:
            c = centrality.get(s['paper_id'], 0.0) / max_centrality
            s['centrality'] = round(c, 3)
            s['degree'] = degree.get(s['paper_id'], 0)
            s['size'] = round(26 + 30 * math.sqrt(c), 1)
            for internal_key in ['tokens_all', 'tokens_title', 'tokens_keywords', 'tokens_method']:
                s.pop(internal_key, None)

        await db.execute(delete(GraphEdge).where(GraphEdge.graph_id == graph_id))
        await db.execute(delete(GraphNode).where(GraphNode.graph_id == graph_id))
        await db.execute(delete(KnowledgeGraphPaper).where(KnowledgeGraphPaper.graph_id == graph_id))

        for snapshot in snapshots:
            db.add(KnowledgeGraphPaper(graph_id=graph.id, paper_id=snapshot['paper_id']))

        node_rows: dict[int, GraphNode] = {}
        for snapshot in snapshots:
            row = GraphNode(
                graph_id=graph.id,
                entity_type='paper',
                name=snapshot['title'],
                properties=dumps({**snapshot, 'build_mode': build_mode}),
                embedding_vector=None,
            )
            db.add(row)
            await db.flush()
            node_rows[snapshot['paper_id']] = row

        for edge in edges_data:
            source = node_rows.get(edge['source_paper_id'])
            target = node_rows.get(edge['target_paper_id'])
            if not source or not target:
                continue
            props = {k: v for k, v in edge.items() if k not in {'source_paper_id', 'target_paper_id', 'relation_type'}}
            db.add(GraphEdge(
                graph_id=graph.id,
                source_node_id=source.id,
                target_node_id=target.id,
                relation_type=edge['relation_type'],
                properties=dumps(props),
            ))

        await db.commit()
        await db.refresh(graph)
        return graph

    async def get_graph(self, db: AsyncSession, user_id: int, graph_id: int) -> dict[str, Any]:
        graph = await db.get(KnowledgeGraph, graph_id)
        if not graph or graph.user_id != user_id:
            raise ValueError('文献图谱不存在。')

        node_rows = (
            await db.execute(select(GraphNode).where(GraphNode.graph_id == graph_id).order_by(GraphNode.id.asc()))
        ).scalars().all()
        edge_rows = (
            await db.execute(select(GraphEdge).where(GraphEdge.graph_id == graph_id).order_by(GraphEdge.id.asc()))
        ).scalars().all()

        nodes: list[dict[str, Any]] = []
        for row in node_rows:
            props = loads(row.properties, {})
            if not isinstance(props, dict):
                props = {}
            score_centrality = props.get('centrality', 0)
            nodes.append({
                'id': str(row.id),
                'db_id': row.id,
                'type': 'paper',
                'entity_type': 'paper',
                'name': row.name,
                'paper_id': props.get('paper_id'),
                'title': props.get('title') or row.name,
                'label': props.get('label') or props.get('title') or row.name,
                'authors': props.get('authors') or None,
                'year': props.get('year'),
                'journal_conf': props.get('journal_conf') or None,
                'source': props.get('journal_conf') or None,
                'doi': props.get('doi') or None,
                'keywords': props.get('keywords') or [],
                'abstract': props.get('abstract') or None,
                'research_question': props.get('research_question') or None,
                'method': props.get('method') or None,
                'main_results': props.get('main_results') or None,
                'centrality': score_centrality or 0,
                **props,
                'properties': props,
            })

        node_ids = {str(n['db_id']) for n in nodes}
        edges: list[dict[str, Any]] = []
        for row in edge_rows:
            source = str(row.source_node_id)
            target = str(row.target_node_id)
            if source not in node_ids or target not in node_ids:
                continue
            props = loads(row.properties, {})
            if not isinstance(props, dict):
                props = {}
            score = float(props.get('score') or 0)
            strength = props.get('strength')
            if strength not in {'strong', 'medium', 'weak'}:
                strength = 'strong' if score >= 0.60 else 'medium' if score >= 0.35 else 'weak'
            relation_types = props.get('relation_types') or []
            shared_keywords = props.get('shared_keywords') or []
            explanation = props.get('explanation')
            if not explanation:
                if shared_keywords:
                    explanation = '两篇论文存在共同关键词，可作为本地图谱中的关联线索。'
                else:
                    explanation = '两篇论文存在弱关联，建议结合标题、摘要和方法进一步核对。'
            edges.append({
                'id': str(row.id),
                'db_id': row.id,
                'source': source,
                'target': target,
                'source_node_id': source,
                'target_node_id': target,
                'relation_type': row.relation_type,
                'score': score,
                'strength': strength,
                'relation_types': relation_types,
                'shared_keywords': shared_keywords,
                'shared_terms': props.get('shared_terms') or [],
                'explanation': explanation,
                'difference': props.get('difference') or '两篇论文的差异需要结合原文进一步阅读。',
                'properties': props,
            })

        domain_name = None
        if graph.domain_id:
            domain = await db.get(KnowledgeDomain, graph.domain_id)
            domain_name = domain.name if domain else None

        return {
            'id': graph.id,
            'name': graph.name,
            'domain_id': graph.domain_id,
            'domain_name': domain_name,
            'created_at': graph.created_at.isoformat() if graph.created_at else None,
            'updated_at': graph.created_at.isoformat() if graph.created_at else None,
            'nodes': nodes,
            'edges': edges,
            'summary': self._build_summary(graph, nodes, edges),
        }

    async def list_graphs(self, db: AsyncSession, user_id: int, domain_id: int | None = None) -> list[dict[str, Any]]:
        stmt = select(KnowledgeGraph).where(KnowledgeGraph.user_id == user_id)
        if domain_id is not None:
            stmt = stmt.where(KnowledgeGraph.domain_id == domain_id)
        stmt = stmt.order_by(KnowledgeGraph.created_at.desc())
        graphs = (await db.execute(stmt)).scalars().all()

        results: list[dict[str, Any]] = []
        for graph in graphs:
            paper_count = await db.scalar(select(func.count(KnowledgeGraphPaper.id)).where(KnowledgeGraphPaper.graph_id == graph.id)) or 0
            node_count = await db.scalar(select(func.count(GraphNode.id)).where(GraphNode.graph_id == graph.id)) or 0
            edge_count = await db.scalar(select(func.count(GraphEdge.id)).where(GraphEdge.graph_id == graph.id)) or 0
            domain_name = None
            if graph.domain_id:
                domain = await db.get(KnowledgeDomain, graph.domain_id)
                domain_name = domain.name if domain else None
            results.append({
                'id': graph.id,
                'name': graph.name,
                'domain_id': graph.domain_id,
                'domain_name': domain_name,
                'paper_count': paper_count,
                'node_count': node_count,
                'edge_count': edge_count,
                'relation_count': edge_count,
                'created_at': graph.created_at.isoformat() if graph.created_at else None,
                'status': 'completed',
            })
        return results

    async def delete_graph(self, db: AsyncSession, user_id: int, graph_id: int) -> None:
        graph = await db.get(KnowledgeGraph, graph_id)
        if not graph or graph.user_id != user_id:
            raise ValueError('文献图谱不存在。')
        await db.execute(delete(GraphEdge).where(GraphEdge.graph_id == graph_id))
        await db.execute(delete(GraphNode).where(GraphNode.graph_id == graph_id))
        await db.execute(delete(KnowledgeGraphPaper).where(KnowledgeGraphPaper.graph_id == graph_id))
        await db.delete(graph)
        await db.commit()
