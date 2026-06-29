from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.mysql import get_db
from app.models import GraphEdge, GraphNode, KnowledgeGraph, User
from app.schemas import GraphCreateIn
from app.services.generation_service import GenerationService
from app.utils.json_utils import loads
router = APIRouter(prefix='/knowledge-graphs', tags=['知识图谱'])

@router.post('')
async def create_graph(data: GraphCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    graph = await GenerationService().create_graph(db, user.id, data.paper_ids, data.name)
    return await get_graph(graph.id, db, user)

@router.get('/{graph_id}')
async def get_graph(graph_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    graph = await db.get(KnowledgeGraph, graph_id)
    nodes = (await db.execute(select(GraphNode).where(GraphNode.graph_id == graph_id))).scalars().all()
    edges = (await db.execute(select(GraphEdge).where(GraphEdge.graph_id == graph_id))).scalars().all()
    return {'id': graph.id, 'name': graph.name, 'nodes': [{'id': n.id, 'type': n.entity_type, 'name': n.name, 'properties': loads(n.properties,{})} for n in nodes], 'edges': [{'id': e.id, 'source': e.source_node_id, 'target': e.target_node_id, 'relation_type': e.relation_type, 'properties': loads(e.properties,{})} for e in edges]}
