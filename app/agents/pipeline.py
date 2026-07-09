from __future__ import annotations

import json
import logging
import re

from langchain_core.runnables import RunnableConfig
from langgraph.types import StreamWriter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import get_deps, is_cancelled
from app.agents.state import AgentIntent, AgentState, ChatTurn, StreamStage
from app.core.config import get_settings
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.integrations.llm.runtime_config import get_llm_runtime_config
from app.models import QAMessage, QASession, QASessionPaper
from app.prompts.intent import (
    INTENT_CLASSIFY_SYSTEM,
    INTENT_LABELS,
    build_intent_user_prompt,
)
from app.prompts.qa import (
    COMPARE_ANSWER_HINT,
    EMPTY_CONTEXT,
    GRAPH_ANSWER_HINT,
    REPORT_ANSWER_HINT,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from app.services.source_enrichment import enrich_qa_sources
from app.services.external_reference_service import build_external_refs

logger = logging.getLogger(__name__)


# =============================================================================
# Runtime helpers
# =============================================================================

def emit_status(writer: StreamWriter, stage: StreamStage) -> None:
    writer({'type': 'status', 'stage': stage})


def tool_has_error(state: AgentState) -> bool:
    for value in (state.get('tool_results') or {}).values():
        if isinstance(value, dict) and value.get('error'):
            return True
    return False


# =============================================================================
# Prepare
# =============================================================================

def build_retrieval_query(question: str, history: list[ChatTurn]) -> str:
    if not history:
        return question
    recent = history[-4:]
    lines = [f"{m['role']}: {(m['content'] or '')[:400]}" for m in recent]
    return '对话背景：\n' + '\n'.join(lines) + f'\n\n当前问题：{question}'


async def load_chat_history(
    db: AsyncSession,
    session_id: int,
    *,
    limit: int = 20,
    exclude_last_user: bool = False,
) -> list[ChatTurn]:
    rows = (
        await db.execute(
            select(QAMessage)
            .where(QAMessage.session_id == session_id)
            .order_by(QAMessage.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    rows = list(reversed(rows))
    history: list[ChatTurn] = []
    for msg in rows:
        if msg.role not in ('user', 'assistant'):
            continue
        history.append({'role': msg.role, 'content': msg.content or ''})
    if exclude_last_user and history and history[-1]['role'] == 'user':
        history = history[:-1]
    return history


async def _resolve_paper_ids(
    db: AsyncSession,
    session_id: int,
    paper_ids: list[int] | None,
) -> list[int]:
    rows = (
        await db.execute(
            select(QASessionPaper.paper_id).where(QASessionPaper.session_id == session_id)
        )
    ).scalars().all()
    seen: set[int] = set()
    ordered: list[int] = []
    for pid in (paper_ids or []) + list(rows):
        if pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    return ordered


async def _get_or_create_session(
    db: AsyncSession,
    user_id: int,
    paper_ids: list[int] | None,
    session_id: int | None,
) -> QASession:
    if session_id:
        session = await db.get(QASession, session_id)
        if session and session.user_id == user_id:
            return session
    session = QASession(user_id=user_id, title='新对话')
    db.add(session)
    await db.flush()
    for pid in paper_ids or []:
        db.add(QASessionPaper(session_id=session.id, paper_id=pid))
    await db.flush()
    return session


async def prepare_session_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = get_deps(config)
    user_id = deps.user_id
    question = (state.get('question') or '').strip()
    paper_ids = state.get('paper_ids')
    session_id = state.get('session_id')
    regenerate = bool(state.get('regenerate'))
    history_limit = get_settings().qa_history_limit

    async with deps.db_session() as db:
        if regenerate:
            if not session_id:
                raise ValueError('重新生成需要指定 session_id')
            session = await db.get(QASession, session_id)
            if not session or session.user_id != user_id:
                raise ValueError('会话不存在或无权访问')
            last_user = (
                await db.execute(
                    select(QAMessage)
                    .where(QAMessage.session_id == session_id, QAMessage.role == 'user')
                    .order_by(QAMessage.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not last_user:
                raise ValueError('没有可重新生成的用户问题')
            question = last_user.content
            await deps.messages.delete_messages_after(db, session_id, last_user.created_at)
            await db.flush()
            history = await load_chat_history(db, session_id, limit=history_limit)
            resolved = await _resolve_paper_ids(db, session.id, paper_ids)
            await db.commit()
            return {
                'session_id': session.id,
                'question': question,
                'paper_ids': resolved,
                'chat_history': history,
                'retrieval_query': build_retrieval_query(question, history),
            }

        session = await _get_or_create_session(db, user_id, paper_ids, session_id)
        db.add(QAMessage(session_id=session.id, role='user', content=question))
        await db.flush()
        history = await load_chat_history(db, session.id, limit=history_limit, exclude_last_user=True)
        resolved = await _resolve_paper_ids(db, session.id, paper_ids)
        await db.commit()
        return {
            'session_id': session.id,
            'question': question,
            'paper_ids': resolved,
            'chat_history': history,
            'retrieval_query': build_retrieval_query(question, history),
        }


# =============================================================================
# Rewrite（原 rewrite.py）
# =============================================================================

def _format_history_for_rewrite(history: list[ChatTurn]) -> str:
    lines: list[str] = []
    for turn in history[-6:]:
        role = '用户' if turn.get('role') == 'user' else '助手'
        content = (turn.get('content') or '')[:800].strip()
        if content:
            lines.append(f'{role}：{content}')
    return '\n'.join(lines)


async def rewrite_query_node(
    state: AgentState,
    config: RunnableConfig,
    writer: StreamWriter,
) -> dict:
    settings = get_settings()
    if not settings.qa_use_llm_rewrite:
        return {}

    paper_ids = state.get('paper_ids') or []
    history: list[ChatTurn] = state.get('chat_history') or []
    question = (state.get('question') or '').strip()
    if not paper_ids or not history or not question:
        return {}

    deps = get_deps(config)
    llm: OpenAICompatibleLLM = deps.llm
    emit_status(writer, 'embedding')

    prompt = f"""你是文献检索 query 改写助手。根据对话历史，将用户的当前问题改写为可独立用于向量检索的完整问句。
要求：保留专业术语；消解「它/这篇/上述方法」等指代；与用户问题同语言；只输出改写后的问句，不要解释。

对话历史：
{_format_history_for_rewrite(history)}

当前问题：{question}

改写后的检索问句："""

    try:
        rewritten = await llm.async_chat(
            [
                {'role': 'system', 'content': '只输出改写后的检索问句，不要引号或多余说明。'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.1,
            max_tokens=256,
            content_only=True,
        )
        rewritten = (rewritten or '').strip()
        if rewritten and len(rewritten) >= 4:
            return {'retrieval_query': rewritten}
    except Exception:
        pass
    return {}


# =============================================================================
# Intent（原 intent.py）
# =============================================================================

_COMPARE_PATTERN = re.compile(
    r'对比|比较|异同|差异|区别|compare|comparison|versus|\bvs\.?\b', re.IGNORECASE,
)
_REPORT_PATTERN = re.compile(
    r'研读报告|阅读报告|文献报告|生成报告|写报告|出报告|帮我报告|report', re.IGNORECASE,
)
_GRAPH_PATTERN = re.compile(
    r'知识图谱|知识图|构建图谱|生成图谱|关系图谱|knowledge graph', re.IGNORECASE,
)
_SUMMARIZE_PATTERN = re.compile(
    r'总结|汇总|概括|梳理|回顾|归纳|summarize|summary|recap', re.IGNORECASE,
)


def _normalize_intent(raw: str | None) -> AgentIntent | None:
    value = (raw or '').strip().lower()
    if value in INTENT_LABELS:
        return value  # type: ignore[return-value]
    return None


def _apply_paper_constraints(intent: AgentIntent, paper_count: int) -> AgentIntent:
    if intent == 'compare' and paper_count < 2:
        return 'literature_qa' if paper_count >= 1 else 'general'
    if intent in ('report', 'graph') and paper_count < 1:
        return 'general'
    if intent == 'literature_qa' and paper_count < 1:
        return 'general'
    return intent


def classify_intent_rules(question: str, paper_ids: list[int] | None) -> AgentIntent:
    q = (question or '').strip()
    pids = paper_ids or []
    if _COMPARE_PATTERN.search(q) and len(pids) >= 2:
        return 'compare'
    if _REPORT_PATTERN.search(q) and len(pids) >= 1:
        return 'report'
    if _GRAPH_PATTERN.search(q) and len(pids) >= 1:
        return 'graph'
    if _SUMMARIZE_PATTERN.search(q) and ('对话' in q or '聊天' in q or '上文' in q or '刚才' in q):
        return 'summarize_history'
    if not pids:
        return 'general'
    return 'literature_qa'


def _history_snippet(history: list[ChatTurn], limit: int = 4) -> str:
    lines: list[str] = []
    for turn in history[-limit:]:
        role = '用户' if turn.get('role') == 'user' else '助手'
        text = (turn.get('content') or '')[:300].strip()
        if text:
            lines.append(f'{role}：{text}')
    return '\n'.join(lines)


async def classify_intent_llm(
    llm: OpenAICompatibleLLM,
    question: str,
    paper_ids: list[int] | None,
    history: list[ChatTurn] | None,
    *,
    rule_hint: AgentIntent | None = None,
) -> AgentIntent | None:
    paper_count = len(paper_ids or [])
    user_prompt = build_intent_user_prompt(
        question,
        paper_count,
        rule_hint=rule_hint,
        history_snippet=_history_snippet(history or []) if history else None,
    )
    try:
        raw = await llm.async_chat(
            [
                {'role': 'system', 'content': INTENT_CLASSIFY_SYSTEM},
                {'role': 'user', 'content': user_prompt},
            ],
            temperature=0.0,
            max_tokens=64,
            content_only=True,
        )
        text = (raw or '').strip()
        if text.startswith('```'):
            text = text.strip('`').replace('json', '', 1).strip()
        payload = json.loads(text)
        intent = _normalize_intent(payload.get('intent') if isinstance(payload, dict) else None)
        if intent:
            return _apply_paper_constraints(intent, paper_count)
    except Exception as exc:
        logger.debug('LLM intent classify failed: %s', exc)
    return None


async def classify_intent(
    question: str,
    paper_ids: list[int] | None,
    *,
    llm: OpenAICompatibleLLM | None = None,
    history: list[ChatTurn] | None = None,
    use_llm: bool = False,
) -> AgentIntent:
    rule_intent = classify_intent_rules(question, paper_ids)
    if not use_llm or not llm:
        return rule_intent
    if rule_intent in ('compare', 'report', 'graph', 'summarize_history'):
        return rule_intent
    llm_intent = await classify_intent_llm(llm, question, paper_ids, history, rule_hint=rule_intent)
    return llm_intent or rule_intent


async def classify_intent_node(
    state: AgentState,
    config: RunnableConfig,
    writer: StreamWriter,
) -> dict:
    emit_status(writer, 'classifying')
    deps = get_deps(config)
    settings = get_settings()
    intent = await classify_intent(
        state.get('question') or '',
        state.get('paper_ids') or [],
        llm=deps.llm,
        history=state.get('chat_history') or [],
        use_llm=settings.qa_use_llm_intent,
    )
    return {'intent': intent, 'tool_results': state.get('tool_results') or {}}


# =============================================================================
# Retrieve / Context（原 retrieve.py + context.py）
# =============================================================================

async def retrieve_node(state: AgentState, config: RunnableConfig, writer: StreamWriter) -> dict:
    deps = get_deps(config)
    if is_cancelled(deps, state):
        return {'ranked_chunks': [], 'context_text': EMPTY_CONTEXT, 'citable_ranked': []}

    query = state.get('retrieval_query') or state.get('question') or ''
    ranked: list[dict] | None = None

    async with deps.db_session() as db:
        async for item in deps.retrieval.retrieve_stream(
            db, query, state.get('paper_ids'), state.get('top_k'),
        ):
            if is_cancelled(deps, state):
                deps.cancel_ctrl['cancelled'] = True
                break
            if isinstance(item, str):
                writer({'type': 'status', 'stage': item})
            else:
                ranked = item

    context_text, citable_ranked = deps.retrieval.build_context(ranked or [])
    if tool_has_error(state) and ranked:
        context_text = f'（结构化工具未能完成，以下为向量检索补充上下文）\n\n{context_text}'

    return {
        'ranked_chunks': ranked or [],
        'context_text': context_text,
        'citable_ranked': citable_ranked,
    }


async def prepare_context_node(state: AgentState, config: RunnableConfig) -> dict:
    intent = state.get('intent') or 'general'
    history: list[ChatTurn] = state.get('chat_history') or []

    if intent == 'summarize_history' and history:
        lines = ['【对话历史摘要参考】']
        for turn in history[-12:]:
            role = '用户' if turn.get('role') == 'user' else '助手'
            content = (turn.get('content') or '')[:1500]
            if content.strip():
                lines.append(f'{role}：{content}')
        context_text = '\n\n'.join(lines)
    else:
        context_text = EMPTY_CONTEXT

    return {'context_text': context_text, 'citable_ranked': [], 'ranked_chunks': []}


# =============================================================================
# Generate / Persist（原 generate.py + persist.py）
# =============================================================================

def _build_llm_messages(state: AgentState) -> list[dict]:
    question = state.get('question') or ''
    context = state.get('context_text') or ''
    history: list[ChatTurn] = state.get('chat_history') or []
    user_content = USER_PROMPT_TEMPLATE.format(question=question, context=context)
    intent = state.get('intent')
    tool_results = state.get('tool_results') or {}

    if (intent == 'compare' or tool_results.get('compare')) and not (tool_results.get('compare') or {}).get('error'):
        user_content = f'{user_content}\n\n{COMPARE_ANSWER_HINT}'
    elif (intent == 'report' or tool_results.get('report')) and not (tool_results.get('report') or {}).get('error'):
        user_content = f'{user_content}\n\n{REPORT_ANSWER_HINT}'
    elif (intent == 'graph' or tool_results.get('graph')) and not (tool_results.get('graph') or {}).get('error'):
        user_content = f'{user_content}\n\n{GRAPH_ANSWER_HINT}'

    messages: list[dict] = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    for turn in history[-8:]:
        content = (turn.get('content') or '')[:2500]
        if content.strip():
            messages.append({'role': turn['role'], 'content': content})
    messages.append({'role': 'user', 'content': user_content})
    return messages


async def generate_node(state: AgentState, config: RunnableConfig, writer: StreamWriter) -> dict:
    deps = get_deps(config)
    if is_cancelled(deps, state):
        return {'answer': '', 'reasoning': '', 'cited_sources': [], 'cancelled': True}

    emit_status(writer, 'generating')

    reasoning_parts: list[str] = []
    answer_parts: list[str] = []
    try:
        async for channel, piece in deps.llm.stream_chat(
            _build_llm_messages(state), temperature=get_llm_runtime_config(scenario='qa').temperature,
        ):
            if is_cancelled(deps, state):
                deps.cancel_ctrl['cancelled'] = True
                break
            if channel == 'reasoning':
                reasoning_parts.append(piece)
                writer({'type': 'delta', 'channel': 'reasoning', 'content': piece})
            else:
                answer_parts.append(piece)
                writer({'type': 'delta', 'channel': 'content', 'content': piece})
    except Exception as exc:
        logger.error('generate_node stream failed: %s', exc, exc_info=True)
        raise

    answer = ''.join(answer_parts)
    reasoning = ''.join(reasoning_parts)
    # 推理模型可能只流式输出 reasoning 通道，正文为空
    if not answer.strip() and reasoning.strip():
        answer = reasoning
    if not answer.strip() and not reasoning.strip() and not is_cancelled(deps, state):
        msg = '模型未返回任何内容，请检查管理后台 LLM 配置与 API 连通性'
        writer({'type': 'error', 'error': msg})
        raise RuntimeError(msg)
    citable = state.get('citable_ranked') or []
    result = {
        'answer': answer,
        'reasoning': reasoning,
        'cited_sources': deps.retrieval.extract_cited_sources(answer, citable),
    }
    if is_cancelled(deps, state):
        result['cancelled'] = True
    return result


async def persist_node(state: AgentState, config: RunnableConfig, writer: StreamWriter) -> dict:
    deps = get_deps(config)
    session_id = state.get('session_id')
    if not session_id:
        raise ValueError('缺少 session_id')

    answer = (state.get('answer') or '').strip()
    reasoning = (state.get('reasoning') or '').strip()
    content_to_save = answer or reasoning

    if is_cancelled(deps, state) and not content_to_save:
        writer({'type': 'error', 'error': '问答连接中断，请检查网络后点击重新生成'})
        return {'message_id': None, 'cited_sources': [], 'cancelled': True}

    if not content_to_save:
        logger.warning('persist_node: empty answer and reasoning, session_id=%s', session_id)
        writer({'type': 'error', 'error': '模型未返回有效内容，请稍后重试'})
        return {'message_id': None, 'cited_sources': [], 'external_refs': []}

    cited_sources = list(state.get('cited_sources') or [])
    artifacts = list(state.get('artifacts') or [])

    async with deps.db_session() as db:
        if cited_sources:
            cited_sources = await enrich_qa_sources(db, cited_sources, answer_text=content_to_save)

        writer({'type': 'sources', 'sources': cited_sources})

        external_refs: list[dict] = []
        try:
            external_refs = await build_external_refs(
                db,
                content_to_save,
                paper_ids=state.get('paper_ids'),
                session_id=session_id,
                user_id=deps.user_id,
                user_question=state.get('question'),
            )
        except Exception as exc:
            logger.warning('build_external_refs failed in persist_node: %s', exc, exc_info=True)

        async def _commit_assistant(*, with_external_refs: bool) -> QAMessage:
            assistant_msg = QAMessage(
                session_id=session_id,
                role='assistant',
                content=content_to_save,
                reasoning_content=reasoning or None,
                tool_artifacts=artifacts or None,
            )
            if with_external_refs:
                assistant_msg.external_refs = external_refs or None
            db.add(assistant_msg)
            await db.flush()
            await deps.messages.attach_sources(db, assistant_msg.id, cited_sources)
            await db.commit()
            return assistant_msg

        try:
            assistant_msg = await _commit_assistant(with_external_refs=True)
        except Exception as exc:
            await db.rollback()
            err = str(exc).lower()
            if 'external_refs' in err and ('unknown column' in err or 'does not exist' in err or '1054' in err):
                logger.warning('external_refs column unavailable, saving without it: %s', exc)
                assistant_msg = await _commit_assistant(with_external_refs=False)
            else:
                logger.error('persist_node commit failed: %s', exc, exc_info=True)
                raise

        writer({
            'type': 'done',
            'session_id': session_id,
            'message_id': assistant_msg.id,
            'answer': content_to_save,
            'reasoning': reasoning,
            'sources': cited_sources,
            'artifacts': artifacts,
            'external_refs': external_refs,
        })
        return {
            'message_id': assistant_msg.id,
            'cited_sources': cited_sources,
            'external_refs': external_refs,
        }
