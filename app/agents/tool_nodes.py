from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from langchain_core.runnables import RunnableConfig
from langgraph.types import StreamWriter
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import get_deps, is_cancelled
from app.agents.pipeline import emit_status
from app.agents.state import AgentState, StreamStage
from app.agents.tools.actions import run_compare_papers, run_create_graph, run_create_report

T = TypeVar('T')


async def _run_with_heartbeat(
    coro_factory: Callable[[], Awaitable[T]],
    on_ping: Callable[[], None],
    should_cancel: Callable[[], bool],
    *,
    interval_seconds: float = 12.0,
) -> T | None:
    stop = asyncio.Event()

    async def _pinger() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                if should_cancel():
                    stop.set()
                    return
                on_ping()

    task = asyncio.create_task(_pinger())
    try:
        if should_cancel():
            return None
        return await coro_factory()
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _emit_artifact(writer: StreamWriter, artifact: dict[str, Any]) -> None:
    writer({'type': 'artifact', **artifact})


@dataclass(frozen=True)
class _ToolSpec:
    tool_key: str
    stage: StreamStage
    label: str
    run: Callable[[AsyncSession, int, list[int]], Awaitable[dict[str, Any]]]
    build_artifact: Callable[[dict[str, Any], list[int]], dict[str, Any]]
    default_error: str = '执行失败'


def _compare_artifact(out: dict[str, Any], paper_ids: list[int]) -> dict[str, Any]:
    return {
        'artifact_type': 'comparison',
        'comparison_id': out.get('comparison_id'),
        'name': out.get('name'),
        'paper_ids': out.get('paper_ids') or paper_ids,
    }


def _report_artifact(out: dict[str, Any], _paper_ids: list[int]) -> dict[str, Any]:
    return {
        'artifact_type': 'report',
        'report_id': out.get('report_id'),
        'paper_id': out.get('paper_id'),
        'title': out.get('title'),
    }


def _graph_artifact(out: dict[str, Any], paper_ids: list[int]) -> dict[str, Any]:
    return {
        'artifact_type': 'graph',
        'graph_id': out.get('graph_id'),
        'name': out.get('name'),
        'paper_ids': out.get('paper_ids') or paper_ids,
    }


_SPECS: dict[str, _ToolSpec] = {
    'compare': _ToolSpec('compare', 'comparing', '对比', run_compare_papers, _compare_artifact, '对比失败'),
    'report': _ToolSpec('report', 'reporting', '报告', run_create_report, _report_artifact, '报告生成失败'),
    'graph': _ToolSpec('graph', 'graphing', '知识图谱', run_create_graph, _graph_artifact, '知识图谱构建失败'),
}


def _tool_error_context(spec: _ToolSpec, msg: str, *, has_papers: bool) -> str:
    paper_hint = '当前会话已挂载文献，' if has_papers else ''
    extra = ''
    if spec.tool_key == 'report' and has_papers:
        extra = '，勿称「未检测到挂载文献」'
    elif spec.tool_key == 'graph' and has_papers:
        extra = '，勿输出与挂载状态矛盾的表述'
    return f'（{paper_hint}{spec.label}工具未能完成：{msg}。请向用户说明原因并给出可操作建议{extra}。）'


async def _execute_tool(
    state: AgentState,
    config: RunnableConfig,
    writer: StreamWriter,
    spec: _ToolSpec,
) -> dict:
    deps = get_deps(config)
    if is_cancelled(deps, state):
        return {'cancelled': True, 'citable_ranked': [], 'ranked_chunks': []}

    user_id = deps.user_id
    paper_ids = list(state.get('paper_ids') or [])

    emit_status(writer, spec.stage)

    msg: str | None = None
    tool_out: dict[str, Any] | None = None

    try:
        async def _run():
            async with deps.db_session() as tool_db:
                return await spec.run(tool_db, user_id, paper_ids)

        tool_out = await _run_with_heartbeat(
            _run,
            lambda: writer({'type': 'ping'}),
            lambda: is_cancelled(deps, state),
        )
        if tool_out is None or is_cancelled(deps, state):
            deps.cancel_ctrl['cancelled'] = True
            return {'cancelled': True, 'citable_ranked': [], 'ranked_chunks': []}
    except ValueError as exc:
        msg = str(exc)
    except Exception as exc:
        msg = str(exc) or spec.default_error

    if msg is None and tool_out is not None:
        artifact = spec.build_artifact(tool_out, paper_ids)
        _emit_artifact(writer, artifact)
        tool_results = dict(state.get('tool_results') or {})
        tool_results[spec.tool_key] = tool_out
        artifacts = list(state.get('artifacts') or [])
        artifacts.append(artifact)
        return {
            'context_text': tool_out.get('context_text') or '',
            'citable_ranked': [],
            'ranked_chunks': [],
            'tool_results': tool_results,
            'artifacts': artifacts,
        }

    return {
        'error': msg,
        'context_text': _tool_error_context(spec, msg or spec.default_error, has_papers=bool(paper_ids)),
        'citable_ranked': [],
        'ranked_chunks': [],
        'tool_results': {**(state.get('tool_results') or {}), spec.tool_key: {'error': msg}},
    }


async def compare_papers_node(
    state: AgentState, config: RunnableConfig, writer: StreamWriter,
) -> dict:
    return await _execute_tool(state, config, writer, _SPECS['compare'])


async def create_report_node(
    state: AgentState, config: RunnableConfig, writer: StreamWriter,
) -> dict:
    return await _execute_tool(state, config, writer, _SPECS['report'])


async def create_graph_node(
    state: AgentState, config: RunnableConfig, writer: StreamWriter,
) -> dict:
    return await _execute_tool(state, config, writer, _SPECS['graph'])
