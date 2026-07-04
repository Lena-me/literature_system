from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.compare import compare_papers_node
from app.agents.nodes.context import prepare_context_node
from app.agents.nodes.generate import generate_node
from app.agents.nodes.intent import classify_intent_node
from app.agents.nodes.persist import persist_node
from app.agents.nodes.retrieve import retrieve_node
from app.agents.nodes.session import prepare_session_node
from app.agents.state import AgentIntent, AgentState


def _route_after_intent(state: AgentState) -> str:
    intent: AgentIntent = state.get('intent') or 'literature_qa'
    if intent == 'compare':
        return 'compare'
    if intent in ('general', 'summarize_history'):
        return 'prepare_context'
    return 'retrieve'


def build_qa_graph():
    """Notebook 问答主图：prepare → classify → (retrieve|compare|context) → generate → persist。"""
    graph = StateGraph(AgentState)
    graph.add_node('prepare', prepare_session_node)
    graph.add_node('classify', classify_intent_node)
    graph.add_node('retrieve', retrieve_node)
    graph.add_node('compare', compare_papers_node)
    graph.add_node('prepare_context', prepare_context_node)
    graph.add_node('generate', generate_node)
    graph.add_node('persist', persist_node)

    graph.add_edge(START, 'prepare')
    graph.add_edge('prepare', 'classify')
    graph.add_conditional_edges(
        'classify',
        _route_after_intent,
        {
            'retrieve': 'retrieve',
            'compare': 'compare',
            'prepare_context': 'prepare_context',
        },
    )
    graph.add_edge('retrieve', 'generate')
    graph.add_edge('compare', 'generate')
    graph.add_edge('prepare_context', 'generate')
    graph.add_edge('generate', 'persist')
    graph.add_edge('persist', END)
    return graph.compile()


@lru_cache
def get_qa_graph():
    return build_qa_graph()
