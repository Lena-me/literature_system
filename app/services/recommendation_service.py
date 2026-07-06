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

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.models import KnowledgeDomain, KnowledgeGraph
from app.utils.json_utils import loads


class RecommendationService:
    """知识推荐服务"""

    # ================================================================
    # 策略A — 关系推理：桥接概念
    # ================================================================

    async def relation_based_recommend(
        self, db: AsyncSession, domain_id: int, top_k: int = 5,
    ) -> list[dict]:
        """基于图关系推理的确定性推荐，从 Neo4j 查询桥接概念。

        算法：找到域内被至少2个已有节点指向的中间节点，
        该中间节点即为"桥接概念"。

        Returns:
            [{'concept': str, 'entity_type': str, 'bridge_nodes': [str], 'reason': str}]
        """
        # 1. 获取域下所有图谱ID
        graph_ids_result = await db.execute(
            select(KnowledgeGraph.id).where(KnowledgeGraph.domain_id == domain_id)
        )
        graph_ids = list(graph_ids_result.scalars().all())
        if not graph_ids:
            return []

        from app.db.neo4j_client import neo4j_manager

        async with neo4j_manager.driver.session() as neo4j_session:
            # 2. 加载域内所有节点名和类型
            nodes_result = await neo4j_session.run(
                "MATCH (n:Entity) WHERE n.graph_id IN $graph_ids "
                "RETURN n.name AS name, labels(n) AS labels",
                {'graph_ids': graph_ids},
            )
            node_records = [r.data() async for r in nodes_result]
            if len(node_records) < 3:
                return []

            domain_entity_names: set[str] = set()
            node_info: dict[str, str] = {}  # name → entity_type
            for rec in node_records:
                name = rec['name']
                domain_entity_names.add(name)
                # 提取 entity_type
                for lbl in rec['labels']:
                    if lbl != 'Entity':
                        node_info[name] = lbl.lower()
                        break
                if name not in node_info:
                    node_info[name] = 'paper'

            # 3. 查找桥接概念：被 ≥2 个域内节点共同连接的中间节点
            #    MATCH (a:Entity)-[:USES|STUDIES|...]->(bridge:Entity)<-[:USES|STUDIES|...]-(b:Entity)
            #    WHERE a.graph_id IN $graph_ids AND b.graph_id IN $graph_ids
            bridges_result = await neo4j_session.run(
                "MATCH (a:Entity)-[r1]->(bridge:Entity)<-[r2]-(b:Entity) "
                "WHERE a.graph_id IN $graph_ids AND b.graph_id IN $graph_ids "
                "  AND a.name <> b.name "
                "  AND r1.graph_id IN $graph_ids "
                "  AND r2.graph_id IN $graph_ids "
                "RETURN bridge.name AS concept, labels(bridge) AS labels, "
                "  a.name AS source_a, b.name AS source_b, "
                "  count(*) AS score "
                "ORDER BY score DESC LIMIT $top_k",
                {'graph_ids': graph_ids, 'top_k': top_k},
            )
            bridge_records = [r.data() async for r in bridges_result]

        results: list[dict] = []
        seen_names: set[str] = set()
        for rec in bridge_records:
            concept = rec['concept']
            if concept in seen_names:
                continue
            seen_names.add(concept)

            entity_type = 'paper'
            for lbl in rec['labels']:
                if lbl != 'Entity':
                    entity_type = lbl.lower()
                    break

            results.append({
                'concept': concept,
                'entity_type': entity_type,
                'score': rec['score'],
                'bridge_nodes': [rec['source_a'], rec['source_b']],
                'reason': f'你已覆盖"{rec["source_a"]}"和"{rec["source_b"]}"，它们都与"{concept}"相关',
                'source': 'relation',
            })

        return results

    # ================================================================
    # 策略B — LLM 推理：探索性推荐
    # ================================================================

    async def llm_based_recommend(
        self, db: AsyncSession, domain_id: int, top_k: int = 5,
    ) -> list[dict]:
        """基于 LLM 的探索性推荐，从 Neo4j 获取域内实体列表。"""
        # 获取域信息和已有实体
        domain = await db.get(KnowledgeDomain, domain_id)
        graph_ids_result = await db.execute(
            select(KnowledgeGraph.id).where(KnowledgeGraph.domain_id == domain_id)
        )
        graph_ids = list(graph_ids_result.scalars().all())
        if not graph_ids:
            return []

        from app.db.neo4j_client import neo4j_manager

        async with neo4j_manager.driver.session() as neo4j_session:
            nodes_result = await neo4j_session.run(
                "MATCH (n:Entity) WHERE n.graph_id IN $graph_ids "
                "RETURN n.name AS name, labels(n) AS labels "
                "LIMIT 50",
                {'graph_ids': graph_ids},
            )
            node_records = [r.data() async for r in nodes_result]

        if not node_records:
            return []

        # 按类型分组构建实体列表
        entity_list: list[str] = []
        for rec in node_records:
            label = rec['name']
            for lbl in rec['labels']:
                if lbl != 'Entity' and lbl.lower() != 'concept':
                    label += f'({lbl.lower()})'
                    break
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
            llm = OpenAICompatibleLLM(scenario='tagging')
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
