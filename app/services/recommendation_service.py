"""
知识推荐服务 — 两种策略互补

策略A - 关系推理（确定性）：
  在图结构中找"桥接概念"：如果用户有节点 A 和 B，两者都通过边连向同一个节点 C，
  且 C 不在用户已覆盖的节点中 → 推荐 C。
  优点：可解释性强，不需要 LLM

策略B - LLM 推理（探索性）：
  将用户已有实体列表发给 LLM，让 LLM 推荐该领域用户可能缺失的核心概念。
  优点：覆盖面广，可以发现图结构未体现的关联
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.models import GraphEdge, GraphNode, KnowledgeDomain, KnowledgeGraph
from app.utils.json_utils import loads


class RecommendationService:
    """知识推荐服务"""

    # ================================================================
    # 策略A — 关系推理：桥接概念
    # ================================================================

    async def relation_based_recommend(
        self, db: AsyncSession, domain_id: int, top_k: int = 5,
    ) -> list[dict]:
        """基于图关系推理的确定性推荐。

        算法：两两检查用户已有节点，找到它们共同连接的"中间节点"。
        如果该中间节点不在用户已有集合中 → 推荐。

        Returns:
            [{'concept': str, 'entity_type': str, 'bridge_nodes': [str], 'reason': str}]
        """
        # 1. 获取域下所有节点和边
        graph_ids_result = await db.execute(
            select(KnowledgeGraph.id).where(KnowledgeGraph.domain_id == domain_id)
        )
        graph_ids = list(graph_ids_result.scalars().all())
        if not graph_ids:
            return []

        nodes = (await db.execute(
            select(GraphNode).where(GraphNode.graph_id.in_(graph_ids))
        )).scalars().all()

        if len(nodes) < 3:
            return []  # 至少需要3个节点才能产生桥接

        # node_id → GraphNode 映射
        node_by_id: dict[int, GraphNode] = {n.id: n for n in nodes}
        all_node_ids = set(node_by_id.keys())

        # 2. 加载所有边，构建邻接关系
        edges = (await db.execute(
            select(GraphEdge).where(GraphEdge.graph_id.in_(graph_ids))
        )).scalars().all()

        # adj_in[node_id] = 哪些节点通过边指向 node_id
        adj_in: dict[int, set[int]] = defaultdict(set)
        # adj_out[node_id] = node_id 通过边指向哪些节点
        adj_out: dict[int, set[int]] = defaultdict(set)

        for e in edges:
            adj_out[e.source_node_id].add(e.target_node_id)
            adj_in[e.target_node_id].add(e.source_node_id)

        # 3. 找桥接节点：被至少2个已有节点共同指向，且自身不在已有集合中
        #    注意：这里"已有节点"就是 all_node_ids（域内所有节点都是用户的）
        bridge_candidates: list[dict] = []
        scored: dict[int, float] = {}

        for node_id, incoming in adj_in.items():
            if node_id not in all_node_ids:
                continue
            # 已有节点指向的节点（即邻接）
            for target_id in adj_out.get(node_id, set()):
                if target_id not in all_node_ids:
                    continue
                # 找同时指向 target_id 的其他节点
                other_sources = adj_in.get(target_id, set()) & all_node_ids
                if len(other_sources) >= 2 and node_id in other_sources:
                    other_sources.discard(node_id)
                    # node_id 和其他源节点共享 target_id 这个"共同邻居"
                    for other_id in other_sources:
                        # 找出 node_id 和 other_id 共同连接的目标
                        common_targets = (
                            adj_out.get(node_id, set())
                            & adj_out.get(other_id, set())
                        )
                        for ct in common_targets:
                            if ct in all_node_ids and ct != node_id and ct != other_id:
                                # 这个 ct 是 node_id 和 other_id 都连接的"桥接概念"
                                # 如果 ct 作为桥节点出现频次高，推荐优先级高
                                scored[ct] = scored.get(ct, 0) + 1.0

        # 按得分排序
        sorted_candidates = sorted(
            scored.items(), key=lambda x: x[1], reverse=True
        )

        results: list[dict] = []
        seen_names: set[str] = set()
        for node_id, score in sorted_candidates[:top_k]:
            node = node_by_id.get(node_id)
            if not node or node.name in seen_names:
                continue
            seen_names.add(node.name)

            # 找是哪两个节点通过它连接
            sources = list(adj_in.get(node_id, set()) & all_node_ids)[:2]
            bridge_names = [node_by_id[s].name for s in sources if s in node_by_id]

            results.append({
                'node_id': node_id,
                'concept': node.name,
                'entity_type': node.entity_type,
                'score': round(score, 1),
                'bridge_nodes': bridge_names,
                'reason': f'你已覆盖{"和".join(bridge_names[:2])}，它们都与"{node.name}"相关',
                'source': 'relation',
            })

        return results

    # ================================================================
    # 策略B — LLM 推理：探索性推荐
    # ================================================================

    async def llm_based_recommend(
        self, db: AsyncSession, domain_id: int, top_k: int = 5,
    ) -> list[dict]:
        """基于 LLM 的探索性推荐。

        将用户已覆盖的实体列表发给 LLM，让 LLM 推荐缺失的核心概念。
        """
        # 获取域信息和已有实体
        domain = await db.get(KnowledgeDomain, domain_id)
        graph_ids_result = await db.execute(
            select(KnowledgeGraph.id).where(KnowledgeGraph.domain_id == domain_id)
        )
        graph_ids = list(graph_ids_result.scalars().all())
        if not graph_ids:
            return []

        nodes = (await db.execute(
            select(GraphNode).where(GraphNode.graph_id.in_(graph_ids))
        )).scalars().all()
        if not nodes:
            return []

        # 按类型分组
        entity_list: list[str] = []
        for n in nodes:
            label = n.name
            if n.entity_type and n.entity_type != 'concept':
                label += f'({n.entity_type})'
            entity_list.append(label)

        # 构建 prompt
        domain_name = domain.name if domain else '当前领域'
        prompt = f"""用户正在构建"{domain_name}"领域的个人知识图谱。

目前已覆盖的实体：
{chr(10).join(f'- {e}' for e in entity_list[:50])}

请基于以上实体，推荐 {top_k} 个该领域用户可能缺失的**核心概念或方法**。
要求：
1. 推荐的概念应当与已有实体有逻辑关联，帮助用户拓展知识边界
2. 优先推荐该领域的重要基础概念（如深度学习领域的Backpropagation、Gradient Descent等）
3. 对每个推荐给出简短理由（为什么这个很重要）

请严格按JSON格式返回：
[{{"concept": "概念名", "entity_type": "concept/method/model/algorithm", "reason": "推荐理由"}}]"""

        try:
            llm = OpenAICompatibleLLM()
            raw = await llm.async_chat([
                {'role': 'user', 'content': prompt},
            ], temperature=0.5, max_tokens=800)

            # 解析 JSON
            import re
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                items = loads(match.group(0))
                if isinstance(items, list):
                    return [{'source': 'llm', **it} for it in items[:top_k]]
        except Exception:
            pass

        return []
