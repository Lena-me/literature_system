from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.models import (
    ComparisonResult,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    PaperExtractedInfo,
    Report,
    ReproducibilityGuide,
)
from app.utils.json_utils import dumps, loads


class GenerationService:
    def __init__(self) -> None:
        self.llm = OpenAICompatibleLLM()

    async def create_report(
        self,
        db: AsyncSession,
        user_id: int,
        paper_id: int,
        modules: list[str] | None,
        title: str | None,
    ) -> Report:
        info = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id == paper_id))
        ).scalar_one_or_none()
        if not info:
            raise ValueError('Target paper has no extracted structured information yet.')

        data = {k: v for k, v in info.__dict__.items() if not k.startswith('_')}
        prompt = (
            'Generate a structured research paper reading report. Include basic paper info, '
            'background, research question, method, experiment design, main results, '
            'innovations, limitations, reproducibility notes, and future work. '
            f'Requested modules: {modules or "all"}. Input: {dumps(data)}'
        )
        content = await self.llm.async_chat(
            [
                {'role': 'system', 'content': 'You generate research paper reading reports.'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.2,
            max_tokens=3500,
        )
        report = Report(
            user_id=user_id,
            paper_id=paper_id,
            title=title or f'{info.title or paper_id} reading report',
            content=dumps({'markdown': content, 'modules': modules or []}),
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return report

    async def compare_papers(
        self,
        db: AsyncSession,
        user_id: int,
        paper_ids: list[int],
        dimensions: list[str] | None,
        name: str | None,
    ) -> ComparisonResult:
        infos = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(paper_ids)))
        ).scalars().all()
        payload = [{k: v for k, v in x.__dict__.items() if not k.startswith('_')} for x in infos]
        prompt = (
            'Compare multiple papers horizontally. Return JSON only with fields: '
            'comparison_table, difference_analysis, trend_summary, future_direction. '
            f'Dimensions: {dimensions or ["research question", "method", "dataset", "metrics", "conclusion"]}. '
            f'Input: {dumps(payload)}'
        )
        text = await self.llm.async_chat(
            [
                {'role': 'system', 'content': 'You compare research papers and return JSON only.'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.1,
            max_tokens=3500,
        )
        result = loads(text, default={'raw': text})
        obj = ComparisonResult(
            user_id=user_id,
            name=name or 'Multi-paper comparison',
            paper_ids=dumps(paper_ids),
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
    ) -> KnowledgeGraph:
        infos = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(paper_ids)))
        ).scalars().all()
        if not infos:
            raise ValueError('Target papers have no extracted structured information yet.')

        payload = [{k: v for k, v in x.__dict__.items() if not k.startswith('_')} for x in infos]
        prompt = f"""Extract a knowledge graph from the structured paper information.
Return JSON only, without Markdown fences.
JSON schema:
{{
  "nodes": [
    {{"type": "paper", "name": "paper title", "properties": {{}}}},
    {{"type": "task", "name": "research question", "properties": {{}}}},
    {{"type": "method", "name": "method name", "properties": {{}}}},
    {{"type": "dataset", "name": "dataset or experiment object", "properties": {{}}}},
    {{"type": "result", "name": "main finding", "properties": {{}}}}
  ],
  "edges": [
    {{"source": "paper title", "target": "method name", "relation_type": "uses", "properties": {{}}}},
    {{"source": "paper title", "target": "research question", "relation_type": "studies", "properties": {{}}}}
  ]
}}
Allowed node types: paper, task, method, dataset, metric, result, innovation, limitation, author.
Input: {dumps(payload)}
"""

        try:
            text = await self.llm.async_chat(
                [
                    {'role': 'system', 'content': 'You build knowledge graphs and return parseable JSON only.'},
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

        graph = KnowledgeGraph(
            user_id=user_id,
            paper_id=paper_ids[0] if len(paper_ids) == 1 else None,
            name=name or 'Research topic knowledge graph',
        )
        db.add(graph)
        await db.flush()

        node_map: dict[str, int] = {}
        for n in data.get('nodes', []):
            node_name = (n.get('name') or '').strip()
            if not node_name or node_name in node_map:
                continue

            node = GraphNode(
                graph_id=graph.id,
                entity_type=n.get('type', 'paper'),
                name=node_name[:300],
                properties=dumps(n.get('properties') or {}),
            )
            db.add(node)
            await db.flush()
            node_map[node.name] = node.id

        for e in data.get('edges', []):
            source_name = (e.get('source') or '').strip()
            target_name = (e.get('target') or '').strip()
            s, t = node_map.get(source_name), node_map.get(target_name)
            if s and t and s != t:
                db.add(
                    GraphEdge(
                        graph_id=graph.id,
                        source_node_id=s,
                        target_node_id=t,
                        relation_type=e.get('relation_type', 'related_to'),
                        properties=dumps(e.get('properties') or {}),
                    )
                )

        await db.commit()
        await db.refresh(graph)
        return graph

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
                ('dataset', info.experiment_data, 'evaluates_on'),
                ('result', info.main_results, 'reports'),
                ('innovation', info.innovations, 'contributes'),
                ('limitation', info.limitations, 'has_limitation'),
            ]
            for node_type, value, relation in fields:
                if not value:
                    continue
                node_name = value.strip()[:120]
                add_node(node_type, node_name)
                add_edge(paper_title, node_name, relation)

        return {'nodes': nodes, 'edges': edges}
