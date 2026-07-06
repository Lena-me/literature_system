from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.generation_service import GenerationService
from app.utils.json_utils import loads


# ---------- Compare ----------

def format_comparison_context(result: dict[str, Any]) -> str:
    papers = result.get('papers') or []
    table = result.get('comparison_table') or []
    lines: list[str] = ['【多篇文献结构化对比结果】', '']

    if papers:
        lines.append('参与对比的文献：')
        for p in papers:
            title = p.get('title') or f"Paper {p.get('paper_id')}"
            lines.append(f"- {title} (id={p.get('paper_id')})")
        lines.append('')

    if table:
        lines.append('对比维度表：')
        for row in table:
            dim = row.get('dimension') or row.get('dimension_key') or '维度'
            lines.append(f'\n## {dim}')
            for p in papers:
                key = p.get('key')
                if not key:
                    continue
                cell = row.get(key) or '-'
                title = p.get('title') or key
                lines.append(f'**{title}**：{cell}')

    for label, field in (
        ('差异分析', 'difference_analysis'),
        ('趋势总结', 'trend_summary'),
        ('未来方向', 'future_direction'),
    ):
        text = (result.get(field) or '').strip()
        if text:
            lines.extend(['', f'【{label}】', text])

    return '\n'.join(lines).strip()


async def run_compare_papers(
    db: AsyncSession,
    user_id: int,
    paper_ids: list[int],
    *,
    name: str | None = None,
) -> dict[str, Any]:
    obj = await GenerationService().compare_papers(
        db, user_id, paper_ids, dimensions=None, name=name,
    )
    payload = loads(obj.result_json, {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        'comparison_id': obj.id,
        'name': obj.name,
        'paper_ids': loads(obj.paper_ids, []),
        'result': payload,
        'context_text': format_comparison_context(payload),
    }


# ---------- Report ----------

def format_report_context(result: dict[str, Any], *, max_chars: int = 14000) -> str:
    title = result.get('title') or '文献研读报告'
    markdown = (result.get('markdown') or '').strip()
    modules = result.get('modules') or []

    lines = [f'【文献研读报告：{title}】', '']
    if modules:
        lines.append(f'报告模块：{", ".join(str(m) for m in modules)}')
        lines.append('')

    if len(markdown) > max_chars:
        markdown = markdown[:max_chars] + '\n\n...（报告正文已截断，完整版已保存至报告库）'
    lines.append(markdown)
    return '\n'.join(lines).strip()


async def run_create_report(
    db: AsyncSession,
    user_id: int,
    paper_ids: list[int],
    *,
    modules: list[str] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    if not paper_ids:
        raise ValueError('生成报告需要至少挂载一篇文献')

    paper_id = paper_ids[0]
    report = await GenerationService().create_report(
        db, user_id, paper_id, modules, title,
    )
    payload = loads(report.content, {})
    if not isinstance(payload, dict):
        payload = {}

    markdown = payload.get('markdown') or ''
    result = {
        'report_id': report.id,
        'paper_id': report.paper_id,
        'title': report.title,
        'markdown': markdown,
        'modules': payload.get('modules') or [],
    }
    return {**result, 'context_text': format_report_context(result)}


# ---------- Graph ----------

def format_graph_context(result: dict[str, Any]) -> str:
    name = result.get('name') or '知识图谱'
    nodes = result.get('nodes') or []
    edges = result.get('edges') or []

    lines = [
        f'【知识图谱：{name}】',
        f'graph_id={result.get("graph_id")}，节点 {len(nodes)} 个，关系 {len(edges)} 条',
        '',
        '核心实体：',
    ]

    for node in nodes[:35]:
        entity_type = node.get('entity_type') or node.get('type') or 'entity'
        node_name = node.get('name') or node.get('id') or '?'
        lines.append(f'- [{entity_type}] {node_name}')

    if edges:
        lines.extend(['', '关系示例：'])
        for edge in edges[:25]:
            rel = edge.get('relation_type') or edge.get('type') or 'related'
            src = edge.get('source_name') or edge.get('source') or '?'
            tgt = edge.get('target_name') or edge.get('target') or '?'
            lines.append(f'- {src} --{rel}--> {tgt}')

    return '\n'.join(lines).strip()


async def _load_graph_summary(graph_id: int) -> tuple[list[dict], list[dict]]:
    from app.db.neo4j_client import neo4j_manager

    nodes: list[dict] = []
    edges: list[dict] = []

    async with neo4j_manager.driver.session() as session:
        node_rows = await session.run(
            'MATCH (n:Entity) WHERE n.graph_id = $graph_id '
            'RETURN n.name AS name, labels(n) AS labels LIMIT 80',
            {'graph_id': graph_id},
        )
        async for record in node_rows:
            data = record.data()
            labels = [x for x in (data.get('labels') or []) if x != 'Entity']
            nodes.append({
                'name': data.get('name'),
                'entity_type': (labels[0] if labels else 'entity').lower(),
            })

        edge_rows = await session.run(
            'MATCH (a:Entity)-[r]->(b:Entity) WHERE r.graph_id = $graph_id '
            'RETURN a.name AS source, b.name AS target, type(r) AS relation_type LIMIT 60',
            {'graph_id': graph_id},
        )
        async for record in edge_rows:
            data = record.data()
            edges.append({
                'source_name': data.get('source'),
                'target_name': data.get('target'),
                'relation_type': data.get('relation_type'),
            })

    return nodes, edges


async def run_create_graph(
    db: AsyncSession,
    user_id: int,
    paper_ids: list[int],
    *,
    name: str | None = None,
    domain_id: int | None = None,
) -> dict[str, Any]:
    if not paper_ids:
        raise ValueError('构建知识图谱需要至少挂载一篇文献')

    graph = await GenerationService().create_graph(
        db, user_id, paper_ids, name, domain_id=domain_id,
    )

    nodes, edges = await _load_graph_summary(graph.id)
    result = {
        'graph_id': graph.id,
        'name': graph.name,
        'paper_ids': paper_ids,
        'nodes': nodes,
        'edges': edges,
    }
    return {**result, 'context_text': format_graph_context(result)}
