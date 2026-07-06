from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.pipeline import (
    classify_intent_node,
    generate_node,
    persist_node,
    prepare_context_node,
    prepare_session_node,
    retrieve_node,
    rewrite_query_node,
    tool_has_error,
)
from app.agents.state import AgentIntent, AgentState
from app.agents.tool_nodes import (
    compare_papers_node,
    create_graph_node,
    create_report_node,
)
from app.core.config import get_settings

INTENT_TOOL_NODES: dict[AgentIntent, str] = {
    'compare': 'compare',
    'report': 'report',
    'graph': 'graph',
}


def route_after_intent(state: AgentState) -> str:
    intent: AgentIntent = state.get('intent') or 'literature_qa'
    if intent in ('general', 'summarize_history'):
        return 'prepare_context'
    return INTENT_TOOL_NODES.get(intent, 'retrieve')


def route_after_tool(state: AgentState) -> str:
    """工具失败且挂载了文献时，降级走向量检索再生成。"""
    if state.get('cancelled'):
        return 'generate'
    settings = get_settings()
    if settings.qa_tool_fallback_rag and tool_has_error(state) and state.get('paper_ids'):
        return 'retrieve'
    return 'generate'


def build_qa_workflow():
    """Notebook 问答主图：prepare → rewrite → classify → tool/retrieve → generate → persist。"""
    graph = StateGraph(AgentState)
    graph.add_node('prepare', prepare_session_node)
    graph.add_node('rewrite', rewrite_query_node)
    graph.add_node('classify', classify_intent_node)
    graph.add_node('retrieve', retrieve_node)
    graph.add_node('compare', compare_papers_node)
    graph.add_node('report', create_report_node)
    graph.add_node('graph', create_graph_node)
    graph.add_node('prepare_context', prepare_context_node)
    graph.add_node('generate', generate_node)
    graph.add_node('persist', persist_node)

    graph.add_edge(START, 'prepare')
    graph.add_edge('prepare', 'rewrite')
    graph.add_edge('rewrite', 'classify')
    graph.add_conditional_edges(
        'classify',
        route_after_intent,
        {
            'retrieve': 'retrieve',
            'compare': 'compare',
            'report': 'report',
            'graph': 'graph',
            'prepare_context': 'prepare_context',
        },
    )
    graph.add_edge('retrieve', 'generate')
    for tool_node in ('compare', 'report', 'graph'):
        graph.add_conditional_edges(
            tool_node,
            route_after_tool,
            {'retrieve': 'retrieve', 'generate': 'generate'},
        )
    graph.add_edge('prepare_context', 'generate')
    graph.add_edge('generate', 'persist')
    graph.add_edge('persist', END)
    return graph.compile()


@lru_cache
def get_qa_workflow():
    return build_qa_workflow()


get_qa_graph = get_qa_workflow
