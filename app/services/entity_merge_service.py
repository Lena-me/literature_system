"""
实体融合服务 — 跨图谱实体对齐与合并

策略：
  - L1 自动合并: 余弦相似度 > 0.85 → 自动合并为同一节点
  - L2 用户确认: 余弦相似度 0.65-0.85 → 提示用户确认
  - 使用 BGE 向量编码实体名称
"""
from __future__ import annotations

import math
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.embeddings.bge_embedding import BGEEmbedding
from app.models import GraphEdge, GraphNode, KnowledgeGraph, KnowledgeGraphPaper
from app.utils.json_utils import dumps, loads


class EntityMergeService:
    """实体融合服务"""

    # 阈值配置
    AUTO_MERGE_THRESHOLD = 0.85    # 高于此值自动合并
    SUGGEST_THRESHOLD = 0.65       # 高于此值提示用户确认

    def __init__(self) -> None:
        self._embedder: BGEEmbedding | None = None

    @property
    def embedder(self) -> BGEEmbedding:
        if self._embedder is None:
            self._embedder = BGEEmbedding()
        return self._embedder

    # ================================================================
    # 向量编码
    # ================================================================

    def encode_entity_name(self, name: str) -> list[float]:
        """对实体名称编码为归一化向量"""
        vectors = self.embedder.encode_documents([name])
        return vectors[0]

    async def ensure_node_vectors(
        self, db: AsyncSession, node_ids: list[int]
    ) -> None:
        """为尚未编码的节点生成并存储向量"""
        nodes = (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.id.in_(node_ids),
                    GraphNode.embedding_vector.is_(None),
                )
            )
        ).scalars().all()

        if not nodes:
            return

        names = [n.name for n in nodes]
        try:
            vectors = self.embedder.encode_documents(names)
        except RuntimeError:
            return  # BGE 模型未加载，跳过高开销操作

        for node, vec in zip(nodes, vectors):
            node.embedding_vector = dumps(vec)

        await db.commit()

    # ================================================================
    # 相似实体检索
    # ================================================================

    async def find_similar_in_domain(
        self,
        db: AsyncSession,
        domain_id: int,
        entity_name: str,
        exclude_node_id: int | None = None,
    ) -> list[dict]:
        """在指定知识域内查找与给定实体名相似的已有节点。

        Returns:
            [{node_id, name, entity_type, similarity, graph_id}], 按相似度降序
        """
        # 1. 获取域下所有图谱ID
        graph_ids_result = (
            await db.execute(
                select(KnowledgeGraph.id).where(KnowledgeGraph.domain_id == domain_id)
            )
        ).scalars().all()
        if not graph_ids_result:
            return []

        graph_ids = list(graph_ids_result)

        # 2. 获取已有向量化的节点
        existing = (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.graph_id.in_(graph_ids),
                    GraphNode.embedding_vector.isnot(None),
                )
            )
        ).scalars().all()

        if not existing:
            return []

        # 3. 编码查询实体
        try:
            query_vec = self.encode_entity_name(entity_name)
        except RuntimeError:
            return []

        # 4. 计算余弦相似度
        results: list[dict] = []
        for node in existing:
            if exclude_node_id and node.id == exclude_node_id:
                continue
            node_vec = loads(node.embedding_vector, default=[])
            if not node_vec:
                continue
            sim = _cosine_similarity(query_vec, node_vec)
            if sim >= self.SUGGEST_THRESHOLD:
                results.append({
                    'node_id': node.id,
                    'name': node.name,
                    'entity_type': node.entity_type,
                    'similarity': round(sim, 4),
                    'graph_id': node.graph_id,
                })

        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:5]

    # ================================================================
    # 实体合并
    # ================================================================

    async def merge_entities(
        self, db: AsyncSession, source_id: int, target_id: int
    ) -> dict:
        """将 source 节点合并到 target 节点。
        - source 的所有入边/出边重定向到 target
        - 删除重复边（同 source→target 去重）
        - 删除 source 节点

        Returns:
            {'merged_edges': int, 'deleted_duplicates': int}
        """
        if source_id == target_id:
            raise ValueError('不能将节点合并到自身')

        source = await db.get(GraphNode, source_id)
        target = await db.get(GraphNode, target_id)
        if not source or not target:
            raise ValueError('节点不存在')

        merged_edges = 0
        deleted_dups = 0

        # 1. 重定向 source 的出边
        out_edges = (
            await db.execute(
                select(GraphEdge).where(GraphEdge.source_node_id == source_id)
            )
        ).scalars().all()

        for edge in out_edges:
            # 检查是否已存在 target→edge.target 的边
            existing = await db.execute(
                select(GraphEdge).where(
                    GraphEdge.source_node_id == target_id,
                    GraphEdge.target_node_id == edge.target_node_id,
                    GraphEdge.relation_type == edge.relation_type,
                )
            )
            if existing.scalar_one_or_none():
                deleted_dups += 1
                await db.delete(edge)
            else:
                edge.source_node_id = target_id
                merged_edges += 1

        # 2. 重定向 source 的入边
        in_edges = (
            await db.execute(
                select(GraphEdge).where(GraphEdge.target_node_id == source_id)
            )
        ).scalars().all()

        for edge in in_edges:
            existing = await db.execute(
                select(GraphEdge).where(
                    GraphEdge.source_node_id == edge.source_node_id,
                    GraphEdge.target_node_id == target_id,
                    GraphEdge.relation_type == edge.relation_type,
                )
            )
            if existing.scalar_one_or_none():
                deleted_dups += 1
                await db.delete(edge)
            else:
                edge.target_node_id = target_id
                merged_edges += 1

        # 3. 删除 source 节点
        await db.delete(source)
        await db.commit()

        return {'merged_edges': merged_edges, 'deleted_duplicates': deleted_dups}

    # ================================================================
    # 模糊匹配获取（需用户确认的）
    # ================================================================

    async def get_pending_merge_suggestions(
        self, db: AsyncSession, domain_id: int
    ) -> list[dict]:
        """获取域内所有待确认的模糊匹配（相似度 0.65~0.85 的节点对）。

        Returns:
            [{'node_a': {id, name, type}, 'node_b': {id, name, type}, 'similarity': float}]
        """
        graph_ids_result = (
            await db.execute(
                select(KnowledgeGraph.id).where(KnowledgeGraph.domain_id == domain_id)
            )
        ).scalars().all()
        if not graph_ids_result:
            return []

        graph_ids = list(graph_ids_result)
        nodes = (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.graph_id.in_(graph_ids),
                    GraphNode.embedding_vector.isnot(None),
                )
            )
        ).scalars().all()

        if len(nodes) < 2:
            return []

        # 两两比较
        pairs: list[dict] = []
        for i in range(len(nodes)):
            vi = loads(nodes[i].embedding_vector, default=[])
            if not vi:
                continue
            for j in range(i + 1, len(nodes)):
                vj = loads(nodes[j].embedding_vector, default=[])
                if not vj:
                    continue
                sim = _cosine_similarity(vi, vj)
                if self.SUGGEST_THRESHOLD <= sim < self.AUTO_MERGE_THRESHOLD:
                    pairs.append({
                        'node_a': {
                            'id': nodes[i].id,
                            'name': nodes[i].name,
                            'type': nodes[i].entity_type,
                        },
                        'node_b': {
                            'id': nodes[j].id,
                            'name': nodes[j].name,
                            'type': nodes[j].entity_type,
                        },
                        'similarity': round(sim, 4),
                    })

        pairs.sort(key=lambda x: x['similarity'], reverse=True)
        return pairs[:20]


# ================================================================
# 工具函数
# ================================================================

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个归一化向量的余弦相似度"""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
