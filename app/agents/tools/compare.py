from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.generation_service import GenerationService
from app.utils.json_utils import loads


def format_comparison_context(result: dict[str, Any]) -> str:
    """将对比结果格式化为 LLM 可用的上下文文本。"""
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
    """调用 GenerationService.compare_papers，返回结构化结果 dict。"""
    obj = await GenerationService().compare_papers(
        db,
        user_id,
        paper_ids,
        dimensions=None,
        name=name,
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
