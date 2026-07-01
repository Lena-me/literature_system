from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import (
    ExplorationTask,
    KnowledgeDomain,
    KnowledgeGraph,
    KnowledgeGraphPaper,
    User,
)
from app.schemas import (
    CoverageInfo,
    DomainCreateIn,
    DomainOut,
    DomainOverviewOut,
    DomainSuggestIn,
    DomainSuggestOut,
    DomainUpdateIn,
    ExploreRequestIn,
    ExploreResultOut,
    GraphCreateIn,
    OverviewOutV2,
    MergeRequestIn,
    MergeResultOut,
    MergeSuggestionOut,
    RecommendationItem,
    RecommendationOut,
)
from app.services.generation_service import GenerationService
from app.services.recommendation_service import RecommendationService
from app.utils.json_utils import loads

router = APIRouter(prefix='/knowledge-graphs', tags=['知识图谱'])

# ==================== 知识域 ====================

@router.post('/domains', response_model=DomainOut)
async def create_domain(
    data: DomainCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    domain = KnowledgeDomain(
        user_id=user.id,
        name=data.name,
        description=data.description,
        icon=data.icon,
        parent_domain_id=data.parent_domain_id,
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return DomainOut(
        id=domain.id, name=domain.name, description=domain.description,
        icon=domain.icon, parent_domain_id=domain.parent_domain_id,
        graph_count=0, paper_count=0,
        created_at=domain.created_at, updated_at=domain.updated_at,
    )

@router.get('/domains', response_model=list[DomainOut])
async def list_domains(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    domains = (
        await db.execute(
            select(KnowledgeDomain).where(KnowledgeDomain.user_id == user.id)
        )
    ).scalars().all()

    results = []
    for d in domains:
        graph_count = (
            await db.scalar(
                select(func.count(KnowledgeGraph.id)).where(KnowledgeGraph.domain_id == d.id)
            )
        ) or 0
        # count distinct papers across all graphs in this domain
        paper_count = (
            await db.scalar(
                select(func.count(func.distinct(KnowledgeGraphPaper.paper_id)))
                .select_from(KnowledgeGraphPaper)
                .join(KnowledgeGraph, KnowledgeGraph.id == KnowledgeGraphPaper.graph_id)
                .where(KnowledgeGraph.domain_id == d.id)
            )
        ) or 0
        results.append(DomainOut(
            id=d.id, name=d.name, description=d.description,
            icon=d.icon, parent_domain_id=d.parent_domain_id,
            graph_count=graph_count, paper_count=paper_count,
            created_at=d.created_at, updated_at=d.updated_at,
        ))
    return results

@router.get('/domains/{domain_id}', response_model=DomainOut)
async def get_domain(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')

    graph_count = (
        await db.scalar(
            select(func.count(KnowledgeGraph.id)).where(KnowledgeGraph.domain_id == domain_id)
        )
    ) or 0
    paper_count = (
        await db.scalar(
            select(func.count(func.distinct(KnowledgeGraphPaper.paper_id)))
            .select_from(KnowledgeGraphPaper)
            .join(KnowledgeGraph, KnowledgeGraph.id == KnowledgeGraphPaper.graph_id)
            .where(KnowledgeGraph.domain_id == domain_id)
        )
    ) or 0
    return DomainOut(
        id=domain.id, name=domain.name, description=domain.description,
        icon=domain.icon, parent_domain_id=domain.parent_domain_id,
        graph_count=graph_count, paper_count=paper_count,
        created_at=domain.created_at, updated_at=domain.updated_at,
    )

@router.put('/domains/{domain_id}', response_model=DomainOut)
async def update_domain(
    domain_id: int,
    data: DomainUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')

    if data.name is not None:
        domain.name = data.name
    if data.description is not None:
        domain.description = data.description
    if data.icon is not None:
        domain.icon = data.icon
    await db.commit()
    await db.refresh(domain)
    return await get_domain(domain_id, db, user)

@router.delete('/domains/{domain_id}')
async def delete_domain(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')
    await db.delete(domain)
    await db.commit()
    return {'message': '知识域已删除'}

@router.post('/domains/suggest', response_model=DomainSuggestOut)
async def suggest_domain(
    data: DomainSuggestIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI 感知：根据论文内容，推荐归属到已有知识域或建议新建域。"""
    suggestions = await GenerationService().suggest_domain(db, user.id, data.paper_ids)
    return DomainSuggestOut(
        suggestions=[
            {
                'domain_id': s.get('domain_id'),
                'domain_name': s.get('domain_name', ''),
                'match_type': s.get('match_type', 'new'),
                'reason': s.get('reason', ''),
                'paper_count_in_domain': s.get('paper_count_in_domain', 0),
            }
            for s in suggestions
        ]
    )

@router.get('/domains/{domain_id}/overview', response_model=DomainOverviewOut)
async def get_domain_overview(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')

    graphs = (
        await db.execute(
            select(KnowledgeGraph)
            .where(KnowledgeGraph.domain_id == domain_id)
            .order_by(KnowledgeGraph.created_at.desc())
        )
    ).scalars().all()

    graph_summaries = [
        {'id': g.id, 'name': g.name, 'created_at': g.created_at}
        for g in graphs
    ]

    graph_ids = [g.id for g in graphs]
    graph_count = len(graphs)

    # 论文数
    paper_count = (
        await db.scalar(
            select(func.count(func.distinct(KnowledgeGraphPaper.paper_id)))
            .select_from(KnowledgeGraphPaper)
            .join(KnowledgeGraph, KnowledgeGraph.id == KnowledgeGraphPaper.graph_id)
            .where(KnowledgeGraph.domain_id == domain_id)
        )
    ) or 0

    # ★ 节点/边数 + 实体类型分布 — 从 Neo4j 单次会话统计
    node_count = 0
    edge_count = 0
    type_dist: dict[str, int] = {}
    if graph_ids:
        from app.db.neo4j_client import neo4j_manager

        async with neo4j_manager.driver.session() as neo4j_session:
            nc_result = await neo4j_session.run(
                "MATCH (n:Entity) WHERE n.graph_id IN $graph_ids RETURN count(n) AS cnt",
                {'graph_ids': graph_ids},
            )
            node_count = (await nc_result.single())['cnt']

            ec_result = await neo4j_session.run(
                "MATCH (:Entity)-[r]->(:Entity) WHERE r.graph_id IN $graph_ids RETURN count(r) AS cnt",
                {'graph_ids': graph_ids},
            )
            edge_count = (await ec_result.single())['cnt']

            td_result = await neo4j_session.run(
                "MATCH (n:Entity) WHERE n.graph_id IN $graph_ids "
                "UNWIND labels(n) AS label "
                "WITH label WHERE label <> 'Entity' "
                "RETURN label, count(*) AS cnt ORDER BY cnt DESC",
                {'graph_ids': graph_ids},
            )
            type_dist = {r['label'].lower(): r['cnt'] async for r in td_result}

    # ★ 覆盖率（基于实体类型多样性）：覆盖率 = 去重实体类型数 / (去重类型数 + 基准期望数)
    unique_types = len(type_dist)
    expected_baseline = max(5, unique_types)  # 至少5种类型的基准
    coverage_rate = round(min(1.0, unique_types / expected_baseline) * 100, 1)

    coverage = CoverageInfo(
        coverage_rate=coverage_rate,
        covered_count=unique_types,
        suggested_count=expected_baseline,
        core_concepts=sorted(type_dist.keys()),
        missing_concepts=[],  # 留空，由前端通过 /recommendations 填充
    )

    # ★ 推荐/探索数（仍从 MySQL 统计）
    recommendation_count = (await db.scalar(
        select(func.count(ExplorationTask.id)).where(ExplorationTask.domain_id == domain_id)
    )) or 0

    return OverviewOutV2(
        domain=DomainOut(
            id=domain.id, name=domain.name, description=domain.description,
            icon=domain.icon, parent_domain_id=domain.parent_domain_id,
            graph_count=graph_count, paper_count=paper_count,
            created_at=domain.created_at, updated_at=domain.updated_at,
        ),
        graphs=graph_summaries,
        coverage=coverage,
        recommendation_count=recommendation_count,
    )

# ==================== 实体融合 ====================
#   NOTE: Neo4j MERGE 已实现全局实体去重，MySQL GraphNode-based 融合路由暂时跳过。
#         如需恢复旧的 MySQL 融合逻辑，请确认 GraphNode 表仍在写入数据。

@router.get('/domains/{domain_id}/merge-suggestions', response_model=MergeSuggestionOut)
async def get_merge_suggestions(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """已迁移至 Neo4j，当前版本不再需要此功能。"""
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')
    return MergeSuggestionOut(suggestions=[])

@router.post('/domains/{domain_id}/merge', response_model=MergeResultOut)
async def merge_entities(
    domain_id: int,
    data: MergeRequestIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """已迁移至 Neo4j，当前版本不再需要此功能。"""
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')
    return MergeResultOut(merged_edges=0, deleted_duplicates=0)

# ==================== 知识推荐 ====================

@router.get('/domains/{domain_id}/recommendations', response_model=RecommendationOut)
async def get_recommendations(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取知识域推荐：关系推理 + LLM 推理双引擎合并结果。"""
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')

    svc = RecommendationService()

    # 策略A：关系推理（确定性）
    relation_recs = await svc.relation_based_recommend(db, domain_id, top_k=3)

    # 策略B：LLM 推理（探索性）
    llm_recs = await svc.llm_based_recommend(db, domain_id, top_k=5)

    # 去重合并（LLM 结果排后面）
    seen_names = {r['concept'] for r in relation_recs}
    for r in llm_recs:
        if r['concept'] not in seen_names:
            relation_recs.append(r)
            seen_names.add(r['concept'])

    return RecommendationOut(
        domain_id=domain_id,
        domain_name=domain.name,
        recommendations=[RecommendationItem(**r) for r in relation_recs],
        source='hybrid',
    )

@router.post('/domains/{domain_id}/explore', response_model=ExploreResultOut)
async def explore_concept(
    domain_id: int,
    data: ExploreRequestIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """记录用户对推荐概念的探索点击。"""
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')

    task = ExplorationTask(
        user_id=user.id,
        domain_id=domain_id,
        concept=data.concept[:300],
        source=data.source,
        status='clicked',
    )
    db.add(task)
    await db.commit()
    return ExploreResultOut()

# ==================== 知识图谱 ====================

@router.post('')
async def create_graph(
    data: GraphCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.domain_id is not None:
        domain = await db.get(KnowledgeDomain, data.domain_id)
        if not domain or domain.user_id != user.id:
            raise HTTPException(status_code=404, detail='知识域不存在')

    graph = await GenerationService().create_graph(
        db, user.id, data.paper_ids, data.name, domain_id=data.domain_id,
    )
    return await get_graph(graph.id, db, user)

@router.get('/graph/{graph_id}')
async def get_graph(
    graph_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询知识图谱详情 — 元数据从 MySQL，节点/边从 Neo4j。"""
    graph = await db.get(KnowledgeGraph, graph_id)
    if not graph or graph.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识图谱不存在')

    from app.db.neo4j_client import neo4j_manager

    async with neo4j_manager.driver.session() as neo4j_session:
        # ---------- 查询节点 ----------
        nodes_result = await neo4j_session.run(
            "MATCH (n:Entity) WHERE n.graph_id = $graph_id "
            "RETURN elementId(n) AS id, labels(n) AS labels, "
            "n.name AS name, n.properties AS properties, "
            "n.domain_id AS domain_id",
            {'graph_id': graph_id},
        )
        node_records = [r.data() async for r in nodes_result]

        # 从 labels 中提取 entity_type（排除 'Entity' label）
        nodes = []
        for rec in node_records:
            raw_labels: list[str] = rec['labels']
            entity_type = 'paper'
            for lbl in raw_labels:
                if lbl != 'Entity':
                    entity_type = lbl.lower()
                    break
            nodes.append({
                'id': rec['id'],
                'type': entity_type,
                'name': rec['name'],
                'properties': loads(rec['properties'], {}),
            })

        # ---------- 查询关系 ----------
        edges_result = await neo4j_session.run(
            "MATCH (s:Entity)-[r]->(t:Entity) "
            "WHERE r.graph_id = $graph_id "
            "RETURN elementId(r) AS id, elementId(s) AS source, elementId(t) AS target, "
            "type(r) AS relation_type, r.properties AS properties",
            {'graph_id': graph_id},
        )
        edge_records = [r.data() async for r in edges_result]

        edges = [
            {
                'id': rec['id'],
                'source': rec['source'],
                'target': rec['target'],
                'relation_type': rec['relation_type'],
                'properties': loads(rec['properties'], {}),
            }
            for rec in edge_records
        ]

        # ★ 补偿查询：边引用了但节点查询漏掉的节点（通常是因为n.graph_id ≠ r.graph_id 的数据不一致）
        existing_node_ids = {n['id'] for n in nodes}
        referenced_node_ids: set[str] = set()
        for rec in edge_records:
            referenced_node_ids.add(rec['source'])
            referenced_node_ids.add(rec['target'])
        missing_node_ids = referenced_node_ids - existing_node_ids
        if missing_node_ids:
            logging.getLogger(__name__).warning(
                f'[get_graph] graph_id={graph_id} 发现{len(missing_node_ids)}个孤儿节点引用，正在补偿查询...'
            )
            missing_result = await neo4j_session.run(
                "MATCH (n:Entity) WHERE elementId(n) IN $ids "
                "RETURN elementId(n) AS id, labels(n) AS labels, "
                "n.name AS name, n.properties AS properties, "
                "n.domain_id AS domain_id",
                {'ids': list(missing_node_ids)},
            )
            async for rec in missing_result:
                raw_labels: list[str] = list(rec['labels'])
                entity_type = 'paper'
                for lbl in raw_labels:
                    if lbl != 'Entity':
                        entity_type = lbl.lower()
                        break
                nodes.append({
                    'id': rec['id'],
                    'type': entity_type,
                    'name': rec['name'],
                    'properties': loads(rec['properties'], {}),
                })

    print(f'[get_graph] graph_id={graph_id} | Neo4j节点数={len(nodes)} | Neo4j边数={len(edges)}')
    if nodes:
        print(f'[get_graph] 第1个节点: id={nodes[0]["id"][:8]} type={nodes[0]["type"]} name={nodes[0]["name"][:30]}')
    if edges:
        print(f'[get_graph] 第1个边: id={edges[0]["id"][:8]} source={edges[0]["source"][:8]} target={edges[0]["target"][:8]} type={edges[0]["relation_type"]}')
    else:
        print(f'[get_graph] ⚠️ 无边数据! nodes={len(nodes)}')

    return {
        'id': graph.id,
        'name': graph.name,
        'domain_id': graph.domain_id,
        'nodes': nodes,
        'edges': edges,
    }
