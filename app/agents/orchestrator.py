from __future__ import annotations



import asyncio

import logging

from typing import Any, AsyncIterator



from langchain_core.runnables import RunnableConfig



from app.agents.workflow import get_qa_workflow

from app.agents.deps import build_agent_deps

from app.agents.state import AgentState

from app.integrations.llm.openai_compatible import OpenAICompatibleLLM



logger = logging.getLogger(__name__)



_orchestrator: 'QAOrchestrator | None' = None





class QAOrchestrator:

    """LangGraph 编排入口：将图执行事件适配为现有 SSE 协议。"""



    def __init__(self) -> None:

        self.graph = get_qa_workflow()

        self.llm = OpenAICompatibleLLM()



    def _build_config(self, user_id: int) -> tuple[RunnableConfig, dict[str, bool]]:

        cancel_ctrl: dict[str, bool] = {'cancelled': False}

        deps = build_agent_deps(user_id, self.llm, cancel_ctrl)

        config: RunnableConfig = {

            'configurable': {

                'deps': deps,

                'cancel_ctrl': cancel_ctrl,

            },

        }

        return config, cancel_ctrl



    async def ask_stream(

        self,

        user_id: int,

        question: str,

        paper_ids: list[int] | None,

        session_id: int | None,

        top_k: int | None,

        *,

        regenerate: bool = False,

    ) -> AsyncIterator[dict[str, Any]]:

        initial: AgentState = {

            'user_id': user_id,

            'session_id': session_id,

            'question': question,

            'paper_ids': paper_ids,

            'top_k': top_k,

            'regenerate': regenerate,

        }

        config, cancel_ctrl = self._build_config(user_id)



        session_emitted = False



        try:

            async for mode, chunk in self.graph.astream(

                initial,

                config=config,

                stream_mode=['custom', 'updates'],

            ):

                if cancel_ctrl.get('cancelled'):

                    break



                if mode == 'custom':

                    event = chunk

                    if isinstance(event, dict):

                        if event.get('type') == 'session':

                            session_emitted = True

                        yield event

                    continue



                if mode != 'updates' or not isinstance(chunk, dict):

                    continue



                for node_name, update in chunk.items():

                    if node_name == 'prepare' and isinstance(update, dict):

                        sid = update.get('session_id')

                        if sid and not session_emitted:

                            session_emitted = True

                            yield {'type': 'session', 'session_id': sid}



        except asyncio.CancelledError:

            cancel_ctrl['cancelled'] = True

            yield {'type': 'done', 'cancelled': True, 'session_id': session_id}

            return



        except Exception as exc:

            logger.error('QAOrchestrator.ask_stream failed: %s', exc, exc_info=True)

            yield {'type': 'error', 'error': str(exc)}



    async def ask(

        self,

        user_id: int,

        question: str,

        paper_ids: list[int] | None,

        session_id: int | None,

        top_k: int | None,

        *,

        regenerate: bool = False,

    ) -> dict[str, Any]:

        """非流式问答：消费图事件并返回最终 payload。"""

        result: dict[str, Any] = {}

        async for event in self.ask_stream(

            user_id,

            question,

            paper_ids,

            session_id,

            top_k,

            regenerate=regenerate,

        ):

            if event.get('type') == 'done':

                result = event

            elif event.get('type') == 'error':

                raise RuntimeError(event.get('error') or '问答失败')

        if not result:

            raise RuntimeError('问答未返回结果')

        return {

            'session_id': result.get('session_id'),

            'answer': result.get('answer') or '',

            'reasoning': result.get('reasoning') or '',

            'sources': result.get('sources') or [],

            'message_id': result.get('message_id'),

            'artifacts': result.get('artifacts') or [],

        }





def get_qa_orchestrator() -> QAOrchestrator:

    global _orchestrator

    if _orchestrator is None:

        _orchestrator = QAOrchestrator()

    return _orchestrator


