from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import (
    ExplorationTask,
    GraphEdge,
    GraphNode,
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
from app.services.entity_merge_service import EntityMergeService
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

    # ★ 节点/边数
    node_count = 0
    edge_count = 0
    if graph_ids:
        node_count = (await db.scalar(
            select(func.count(GraphNode.id)).where(GraphNode.graph_id.in_(graph_ids))
        )) or 0
        edge_count = (await db.scalar(
            select(func.count(GraphEdge.id)).where(GraphEdge.graph_id.in_(graph_ids))
        )) or 0

    # ★ 推荐/探索数
    recommendation_count = (await db.scalar(
        select(func.count(ExplorationTask.id)).where(ExplorationTask.domain_id == domain_id)
    )) or 0

    # ★ 实体类型分布（用于树形知识地图）
    type_rows = [] if not graph_ids else (
        await db.execute(
            select(GraphNode.entity_type, func.count(GraphNode.id))
            .where(GraphNode.graph_id.in_(graph_ids))
            .group_by(GraphNode.entity_type)
        )
    ).all()
    type_dist: dict[str, int] = {row[0]: row[1] for row in type_rows}

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

@router.get('/domains/{domain_id}/merge-suggestions', response_model=MergeSuggestionOut)
async def get_merge_suggestions(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取域内所有待确认的模糊匹配（相似度 0.65~0.85 的节点对）。"""
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')

    svc = EntityMergeService()
    pairs = await svc.get_pending_merge_suggestions(db, domain_id)
    return MergeSuggestionOut(suggestions=pairs)

@router.post('/domains/{domain_id}/merge', response_model=MergeResultOut)
async def merge_entities(
    domain_id: int,
    data: MergeRequestIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动将 source 节点合并到 target 节点。"""
    domain = await db.get(KnowledgeDomain, domain_id)
    if not domain or domain.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识域不存在')

    source = await db.get(GraphNode, data.source_node_id)
    target = await db.get(GraphNode, data.target_node_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail='节点不存在')

    # 确认两个节点都在该域下
    if source.graph_id and target.graph_id:
        sg = await db.get(KnowledgeGraph, source.graph_id)
        tg = await db.get(KnowledgeGraph, target.graph_id)
        if not sg or not tg or sg.domain_id != domain_id or tg.domain_id != domain_id:
            raise HTTPException(status_code=400, detail='节点不属于此知识域')

    svc = EntityMergeService()
    result = await svc.merge_entities(db, data.source_node_id, data.target_node_id)
    return MergeResultOut(
        merged_edges=result['merged_edges'],
        deleted_duplicates=result['deleted_duplicates'],
    )

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
    graph = await db.get(KnowledgeGraph, graph_id)
    if not graph or graph.user_id != user.id:
        raise HTTPException(status_code=404, detail='知识图谱不存在')

    nodes = (
        await db.execute(select(GraphNode).where(GraphNode.graph_id == graph_id))
    ).scalars().all()
    edges = (
        await db.execute(select(GraphEdge).where(GraphEdge.graph_id == graph_id))
    ).scalars().all()
    return {
        'id': graph.id,
        'name': graph.name,
        'domain_id': graph.domain_id,
        'nodes': [
            {
                'id': n.id,
                'type': n.entity_type,
                'name': n.name,
                'properties': loads(n.properties, {}),
            }
            for n in nodes
        ],
        'edges': [
            {
                'id': e.id,
                'source': e.source_node_id,
                'target': e.target_node_id,
                'relation_type': e.relation_type,
                'properties': loads(e.properties, {}),
            }
            for e in edges
        ],
    }
