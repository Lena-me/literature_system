from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.models import (
    ComparisonResult,
    GraphEdge,
    GraphNode,
    KnowledgeDomain,
    KnowledgeGraph,
    KnowledgeGraphPaper,
    Paper,
    PaperExtractedInfo,
    Report,
    ReproducibilityGuide,
)
from app.services.entity_merge_service import EntityMergeService
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

        node_map: dict[str, int] = {}
        nodes_to_encode: list[GraphNode] = []
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
            nodes_to_encode.append(node)

        # ============================================================
        # ★ 跨图谱实体融合（仅当在某个知识域下时执行）
        # ============================================================
        merged_count = 0
        if domain_id is not None and nodes_to_encode:
            merge_svc = EntityMergeService()
            # 为新节点批量编码并存储向量
            await merge_svc.ensure_node_vectors(
                db, [n.id for n in nodes_to_encode]
            )
            # 逐个检查是否与域内已有节点高度相似
            for node in nodes_to_encode:
                if node.id not in node_map.values():
                    continue  # 已被之前的合并操作删除
                similars = await merge_svc.find_similar_in_domain(
                    db, domain_id, node.name, exclude_node_id=node.id,
                )
                auto_match = next(
                    (s for s in similars if s['similarity'] >= EntityMergeService.AUTO_MERGE_THRESHOLD),
                    None,
                )
                if auto_match:
                    # 将 node_map 中该名称映射到已有节点
                    node_map[node.name] = auto_match['node_id']
                    await db.delete(node)
                    merged_count += 1

        if merged_count > 0:
            await db.flush()

        # 创建边（使用融合后的 node_map）
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


# ============================================================
# 辅助函数
# ============================================================
# 工具函数
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
