from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.integrations.embeddings.bge_embedding import BGEEmbedding
from app.integrations.embeddings.bge_reranker import BGEReranker
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.integrations.milvus.client import get_milvus_store
from app.models import Paper, PaperExtractedInfo, QAMessage, QAMessageSource, QASession, QASessionPaper, TextChunk
from app.services.source_enrichment import enrich_qa_sources
from app.services.external_reference_service import build_external_refs
from app.utils.chunk_quality import (
    is_compare_question,
    is_low_quality_chunk,
    normalize_chunk_text,
    normalize_page_number,
)

settings = get_settings()
logger = logging.getLogger(__name__)

_CITATION_INDEX_RE = re.compile(r'\[(\d+)\]')
_QUERY_KEYWORD_RE = re.compile(r'[A-Za-z][A-Za-z0-9_-]{2,}')
_KEYWORD_STOP = frozenset(
    {
        'the', 'and', 'for', 'how', 'what', 'why', 'when', 'where', 'with', 'from',
        'this', 'that', 'are', 'was', 'were', 'can', 'could', 'should', 'would',
    }
)

from app.prompts.qa import EMPTY_CONTEXT as _EMPTY_CONTEXT
from app.prompts.qa import SYSTEM_PROMPT as _SYSTEM_PROMPT
from app.prompts.qa import USER_PROMPT_TEMPLATE as _USER_PROMPT_TEMPLATE

_rag_service: 'RAGService | None' = None


def _configured_cuda_devices() -> list[str]:
    return [
        device
        for device in (settings.embedding_device, settings.reranker_device)
        if str(device).lower().startswith('cuda')
    ]


def warmup_rag_models() -> None:
    """进程启动时预加载向量模型 / reranker / Milvus，避免首问冷启动。"""
    try:
        from app.integrations.embeddings.bge_embedding import _load_model as load_embed
        from app.integrations.embeddings.bge_reranker import _load_model as load_rerank

        load_embed()
        if settings.rag_enable_reranker:
            load_rerank()
        get_milvus_store()
        cuda_devices = _configured_cuda_devices()
        cuda_ok = False
        gpu_name = ''
        if cuda_devices:
            import torch

            cuda_ok = torch.cuda.is_available()
            gpu_name = f', gpu={torch.cuda.get_device_name(0)}' if cuda_ok else ''
        logger.info(
            'RAG models warmed up (embedding=%s, reranker=%s, cuda=%s%s)',
            settings.embedding_device,
            settings.reranker_device,
            cuda_ok,
            gpu_name,
        )
    except Exception as exc:
        logger.warning('RAG warmup skipped: %s', exc)


def get_rag_service() -> 'RAGService':
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


class RAGService:
    def __init__(self) -> None:
        self.embedding = BGEEmbedding()
        self.reranker = BGEReranker()
        self.vdb = get_milvus_store()
        self.llm = OpenAICompatibleLLM()

    def _normalize_candidate(self, candidate: dict) -> dict:
        out = dict(candidate)
        out['page_number'] = normalize_page_number(out.get('page_number'))
        raw = normalize_chunk_text(out.get('text') or '')
        if raw:
            out['text'] = raw
        return out

    def _filter_ranked(self, ranked: list[dict]) -> list[dict]:
        filtered: list[dict] = []
        for item in ranked:
            if item.get('synthetic'):
                filtered.append(item)
                continue
            text = item.get('text') or item.get('snippet') or ''
            section = item.get('section_title')
            if is_low_quality_chunk(text, section):
                continue
            filtered.append(item)
        return filtered

    async def _paper_summary_chunks(
        self,
        db: AsyncSession,
        paper_ids: list[int] | None,
    ) -> list[dict]:
        if not paper_ids:
            return []
        rows = (
            await db.execute(
                select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(paper_ids))
            )
        ).scalars().all()
        summaries: list[dict] = []
        for info in rows:
            parts: list[str] = []
            if info.title:
                parts.append(f'标题：{info.title}')
            for label, field in (
                ('摘要', 'abstract'),
                ('研究问题', 'research_question'),
                ('方法', 'method'),
                ('主要结果', 'main_results'),
                ('创新点', 'innovations'),
            ):
                val = getattr(info, field, None)
                if val:
                    parts.append(f'{label}：{str(val)[:800]}')
            if not parts:
                continue
            summaries.append(
                {
                    'chunk_id': None,
                    'paper_id': info.paper_id,
                    'page_number': None,
                    'section_title': '摘要概要',
                    'text': '\n'.join(parts),
                    'snippet': '\n'.join(parts)[:1000],
                    'score': 1.0,
                    'rerank_score': 1.0,
                    'synthetic': True,
                }
            )
        return summaries

    def _top_chunks_per_paper(self, candidates: list[dict], paper_ids: list[int], per_paper: int) -> list[dict]:
        grouped: dict[int, list[dict]] = {int(pid): [] for pid in paper_ids}
        for item in sorted(candidates, key=lambda x: x.get('score', 0), reverse=True):
            pid = int(item.get('paper_id') or 0)
            if pid not in grouped or len(grouped[pid]) >= per_paper:
                continue
            grouped[pid].append(item)
        merged: list[dict] = []
        for pid in paper_ids:
            merged.extend(grouped.get(int(pid), []))
        return merged

    @staticmethod
    def _extract_query_keywords(question: str) -> list[str]:
        seen: set[str] = set()
        keywords: list[str] = []
        for match in _QUERY_KEYWORD_RE.finditer(question or ''):
            word = match.group(0)
            if len(word) < 3 or word.lower() in _KEYWORD_STOP:
                continue
            key = word.lower()
            if key in seen:
                continue
            seen.add(key)
            keywords.append(word)
        return keywords[:8]

    async def _fetch_keyword_chunks(
        self,
        db: AsyncSession,
        paper_ids: list[int] | None,
        question: str,
        limit: int = 6,
    ) -> list[dict]:
        """专有名词/模型名等关键词直查正文块，弥补纯向量检索漏召回。"""
        keywords = self._extract_query_keywords(question)
        # 中文术语：连续 2~8 个汉字（排除过短虚词）
        for term in re.findall(r'[\u4e00-\u9fff]{2,8}', question or ''):
            if term in {'怎么', '如何', '什么', '为什么', '详细', '步骤', '实现', '算法', '方法', '论文', '文献'}:
                continue
            key = term.lower()
            if key not in {k.lower() for k in keywords}:
                keywords.append(term)
        keywords = keywords[:10]
        if not keywords or not paper_ids:
            return []

        clauses = [TextChunk.chunk_text.ilike(f'%{kw}%') for kw in keywords]
        rows = (
            await db.execute(
                select(TextChunk)
                .where(TextChunk.paper_id.in_(paper_ids), or_(*clauses))
                .limit(limit * 3)
            )
        ).scalars().all()

        hits: list[dict] = []
        for chunk in rows:
            text = normalize_chunk_text(chunk.chunk_text or '')
            if not text or is_low_quality_chunk(text, None):
                continue
            hits.append(
                {
                    'chunk_id': chunk.id,
                    'paper_id': chunk.paper_id,
                    'page_number': normalize_page_number(chunk.page_number),
                    'section_title': '',
                    'text': text,
                    'score': 0.99,
                    'rerank_score': 0.99,
                    'keyword_hit': True,
                }
            )
            if len(hits) >= limit:
                break
        return hits

    def _merge_keyword_hits(self, ranked: list[dict], keyword_hits: list[dict], limit: int) -> list[dict]:
        if not keyword_hits:
            return ranked[:limit]
        seen: set[int] = set()
        merged: list[dict] = []
        for item in keyword_hits + ranked:
            cid = item.get('chunk_id')
            if cid is not None:
                if int(cid) in seen:
                    continue
                seen.add(int(cid))
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged

    async def _retrieve_ranked(
        self,
        db: AsyncSession,
        question: str,
        paper_ids: list[int] | None,
        top_k: int | None,
    ) -> list[dict]:
        ranked: list[dict] | None = None
        async for item in self._retrieve_ranked_stream(db, question, paper_ids, top_k):
            if isinstance(item, list):
                ranked = item
        return ranked or []

    async def _retrieve_ranked_stream(
        self,
        db: AsyncSession,
        question: str,
        paper_ids: list[int] | None,
        top_k: int | None,
    ):
        """yield 阶段名 (str)，最后 yield ranked (list[dict])。"""
        limit = settings.rerank_top_n
        multi_paper = len(paper_ids or []) > 1
        compare = is_compare_question(question)

        yield 'embedding'
        summaries = await self._paper_summary_chunks(db, paper_ids)
        keyword_hits = await self._fetch_keyword_chunks(db, paper_ids, question)

        if settings.rag_fast_multi_paper and compare and summaries:
            ranked = list(summaries)[:limit]
            ranked = self._filter_ranked(ranked)
            ranked = await enrich_qa_sources(db, ranked[:limit])
            yield ranked[:limit]
            return

        if not paper_ids:
            ranked = self._filter_ranked(list(keyword_hits)[:limit] if keyword_hits else list(summaries)[:limit])
            if not ranked and summaries:
                ranked = summaries[:limit]
            ranked = await enrich_qa_sources(db, ranked[:limit])
            yield ranked[:limit]
            return

        search_limit = min(
            32,
            max((top_k or settings.top_k) * settings.rag_search_multiplier, limit * 2),
        )
        rerank_pool = min(settings.rag_rerank_pool_max, search_limit)

        query_vector = await asyncio.to_thread(self.embedding.encode_query, question)

        yield 'searching'
        raw_hits = await asyncio.to_thread(
            self.vdb.search, query_vector, paper_ids, search_limit
        )
        candidates = [self._normalize_candidate(c) for c in raw_hits]

        if settings.rag_enable_reranker and candidates:
            yield 'reranking'
            try:
                ranked = await asyncio.to_thread(self.reranker.rerank, question, candidates, rerank_pool)
            except Exception as exc:
                logger.warning('Reranker failed, falling back to vector scores: %s', exc)
                ranked = sorted(candidates, key=lambda x: x.get('score', 0), reverse=True)[:rerank_pool]
        else:
            ranked = sorted(candidates, key=lambda x: x.get('score', 0), reverse=True)[:rerank_pool]

        ranked = self._merge_keyword_hits(ranked, keyword_hits, rerank_pool)
        filtered = self._filter_ranked(ranked)

        if compare or multi_paper:
            per_paper = max(1, (limit - len(summaries)) // max(len(paper_ids or [1]), 1))
            extras: list[dict] = []
            if paper_ids:
                extras = self._top_chunks_per_paper(filtered, paper_ids, per_paper)
            # 正文 chunk 优先，摘要仅作背景
            ranked = self._merge_keyword_hits(extras + summaries, keyword_hits, limit)
            ranked = ranked[:limit]
        elif len(filtered) >= max(2, limit // 2):
            ranked = self._merge_keyword_hits(filtered, keyword_hits, limit)[:limit]
        elif filtered:
            ranked = self._merge_keyword_hits(filtered + summaries, keyword_hits, limit)[:limit]
        elif keyword_hits:
            ranked = self._merge_keyword_hits(keyword_hits, [], limit)[:limit]
        elif summaries:
            ranked = summaries[:limit]
        else:
            ranked = []

        ranked = self._filter_ranked(ranked)
        if not ranked and summaries:
            ranked = summaries[:limit]
        ranked = await enrich_qa_sources(db, ranked[:limit])
        yield ranked[:limit]

    # ---------- 公开 API（供 QA Agent / 适配器调用，避免直接访问 _ 前缀方法） ----------

    async def retrieve_ranked_stream(
        self,
        db: AsyncSession,
        question: str,
        paper_ids: list[int] | None,
        top_k: int | None,
    ):
        async for item in self._retrieve_ranked_stream(db, question, paper_ids, top_k):
            yield item

    def build_retrieval_context(self, ranked: list[dict]) -> tuple[str, list[dict]]:
        return self._build_context(ranked)

    def extract_cited_sources(self, answer: str, ranked: list[dict]) -> list[dict]:
        return self._sources_cited_in_answer(answer, ranked)

    async def attach_message_sources(
        self, db: AsyncSession, message_id: int, ranked: list[dict],
    ) -> None:
        await self._add_message_sources(db, message_id, ranked)

    async def delete_messages_after(
        self, db: AsyncSession, session_id: int, after_created_at,
    ) -> None:
        await self._delete_messages_after(db, session_id, after_created_at)

    @staticmethod
    def _extract_citation_indices(answer: str, max_index: int) -> list[int]:
        indices: list[int] = []
        for match in _CITATION_INDEX_RE.findall(answer or ''):
            try:
                idx = int(match)
            except ValueError:
                continue
            if 1 <= idx <= max_index:
                indices.append(idx)
        return sorted(set(indices))

    def _sources_cited_in_answer(self, answer: str, ranked: list[dict]) -> list[dict]:
        if not ranked:
            return []
        cited = self._extract_citation_indices(answer, len(ranked))
        if not cited:
            return []

        selected: list[dict] = []
        for idx in cited:
            item = dict(ranked[idx - 1])
            item['ref_index'] = idx - 1
            item['ref_label'] = f'[{idx}]'
            selected.append(item)
        return selected

    def _build_context(self, ranked: list[dict]) -> tuple[str, list[dict]]:
        """构建 LLM 上下文；返回 (prompt 文本, 可引用来源列表)。"""
        if not ranked:
            return _EMPTY_CONTEXT, []

        citable = [c for c in ranked if not c.get('synthetic')]
        background = [c for c in ranked if c.get('synthetic')]
        max_chars = settings.rag_chunk_context_max_chars
        blocks: list[str] = []

        for i, chunk in enumerate(citable):
            page = chunk.get('page_number')
            section = chunk.get('section_title') or ''
            header = f"[来源{i + 1} | paper_id={chunk['paper_id']}"
            if page:
                header += f' | page={page}'
            if section:
                header += f' | section={section[:80]}'
            header += ']'
            body = (chunk.get('text') or '')[:max_chars]
            blocks.append(f'{header}\n{body}')

        if background:
            bg_parts: list[str] = []
            for chunk in background:
                title = chunk.get('section_title') or '文献概要'
                body = (chunk.get('text') or '')[:max_chars]
                bg_parts.append(f'— paper_id={chunk["paper_id"]} | {title}\n{body}')
            blocks.append(
                '【文献背景参考（结构化摘要/方法概述，请勿在此段标注 [1][2] 引用）】\n'
                + '\n\n'.join(bg_parts)
            )

        if not citable and not background:
            return _EMPTY_CONTEXT, []

        return '\n\n'.join(blocks), citable

    async def _add_message_sources(self, db: AsyncSession, message_id: int, ranked: list[dict]) -> None:
        chunk_ids = {c.get('chunk_id') for c in ranked if c.get('chunk_id')}
        valid_ids: set[int] = set()
        if chunk_ids:
            result = await db.execute(select(TextChunk.id).where(TextChunk.id.in_(chunk_ids)))
            valid_ids = {row[0] for row in result.fetchall()}
        for c in ranked:
            cid = c.get('chunk_id')
            display_text = (c.get('text') or c.get('snippet') or '')[:1000]
            db.add(
                QAMessageSource(
                    message_id=message_id,
                    chunk_id=cid if cid in valid_ids else None,
                    paper_id=c.get('paper_id'),
                    section_title=c.get('section_title'),
                    page_number=c.get('page_number'),
                    snippet=display_text,
                    similarity_score=float(c.get('rerank_score', c.get('score', 0))),
                )
            )

    async def ask(
        self,
        db: AsyncSession,
        user_id: int,
        question: str,
        paper_ids: list[int] | None,
        session_id: int | None,
        top_k: int | None,
    ) -> dict:
        session = await self._get_or_create_session(db, user_id, question, paper_ids, session_id)
        user_msg = QAMessage(session_id=session.id, role='user', content=question)
        db.add(user_msg)
        await db.flush()

        ranked = await self._retrieve_ranked(db, question, paper_ids, top_k)
        context, citable_ranked = self._build_context(ranked)
        prompt = _USER_PROMPT_TEMPLATE.format(question=question, context=context)
        answer = await self.llm.async_chat(
            [{'role': 'system', 'content': _SYSTEM_PROMPT}, {'role': 'user', 'content': prompt}],
            temperature=0.35,
        )
        cited_sources = self._sources_cited_in_answer(answer, citable_ranked)
        if cited_sources:
            cited_sources = await enrich_qa_sources(db, cited_sources, answer_text=answer)
        assistant_msg = QAMessage(session_id=session.id, role='assistant', content=answer)
        db.add(assistant_msg)
        await db.flush()
        await self._add_message_sources(db, assistant_msg.id, cited_sources)
        await db.commit()
        return {'session_id': session.id, 'answer': answer, 'sources': cited_sources}

    async def ask_stream(
        self,
        db: AsyncSession,
        user_id: int,
        question: str,
        paper_ids: list[int] | None,
        session_id: int | None,
        top_k: int | None,
        *,
        regenerate: bool = False,
    ):
        try:
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
                await self._delete_messages_after(db, session_id, last_user.created_at)
                await db.flush()
            else:
                session = await self._get_or_create_session(db, user_id, question, paper_ids, session_id)
                user_msg = QAMessage(session_id=session.id, role='user', content=question)
                db.add(user_msg)
                await db.flush()

            yield {'type': 'session', 'session_id': session.id}

            ranked: list[dict] | None = None
            async for item in self._retrieve_ranked_stream(db, question, paper_ids, top_k):
                if isinstance(item, str):
                    yield {'type': 'status', 'stage': item}
                else:
                    ranked = item

            yield {'type': 'status', 'stage': 'generating'}
            context, citable_ranked = self._build_context(ranked or [])
            prompt = _USER_PROMPT_TEMPLATE.format(question=question, context=context)
            reasoning_parts: list[str] = []
            answer_parts: list[str] = []
            async for channel, piece in self.llm.stream_chat(
                [{'role': 'system', 'content': _SYSTEM_PROMPT}, {'role': 'user', 'content': prompt}],
                temperature=0.35,
            ):
                if channel == 'reasoning':
                    reasoning_parts.append(piece)
                    yield {'type': 'delta', 'channel': 'reasoning', 'content': piece}
                else:
                    answer_parts.append(piece)
                    yield {'type': 'delta', 'channel': 'content', 'content': piece}
            answer = ''.join(answer_parts)
            reasoning = ''.join(reasoning_parts)
            if not answer.strip() and reasoning.strip():
                answer = reasoning
            cited_sources = self._sources_cited_in_answer(answer, citable_ranked)
            if cited_sources:
                cited_sources = await enrich_qa_sources(db, cited_sources, answer_text=answer)

            yield {'type': 'sources', 'sources': cited_sources}

            assistant_msg = QAMessage(
                session_id=session.id,
                role='assistant',
                content=answer.strip() or reasoning.strip(),
                reasoning_content=reasoning or None,
            )
            db.add(assistant_msg)
            await db.flush()
            await self._add_message_sources(db, assistant_msg.id, cited_sources)
            external_refs: list[dict] = []
            try:
                external_refs = await build_external_refs(
                    db,
                    answer,
                    paper_ids=paper_ids,
                    session_id=session.id,
                    user_id=user_id,
                    user_question=question,
                )
            except Exception as exc:
                logger.warning('build_external_refs failed in ask_stream: %s', exc, exc_info=True)
            assistant_msg.external_refs = external_refs or None
            await db.commit()
            yield {
                'type': 'done',
                'session_id': session.id,
                'message_id': assistant_msg.id,
                'external_refs': external_refs,
            }
        except Exception as exc:
            logger.error('ask_stream failed: %s', exc, exc_info=True)
            yield {'type': 'error', 'error': str(exc)}

    async def delete_messages_from(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        message_id: int,
        *,
        inclusive: bool = True,
    ) -> int:
        session = await db.get(QASession, session_id)
        if not session or session.user_id != user_id:
            raise ValueError('会话不存在或无权访问')
        anchor = await db.get(QAMessage, message_id)
        if not anchor or anchor.session_id != session_id:
            raise ValueError('消息不存在')

        if inclusive:
            clause = QAMessage.created_at >= anchor.created_at
        else:
            clause = QAMessage.created_at > anchor.created_at

        ids = list(
            (
                await db.execute(
                    select(QAMessage.id).where(QAMessage.session_id == session_id, clause)
                )
            ).scalars().all()
        )
        if not ids:
            return 0
        await self._delete_message_ids(db, ids)
        await db.commit()
        return len(ids)

    async def _delete_messages_after(
        self,
        db: AsyncSession,
        session_id: int,
        after_created_at,
    ) -> None:
        ids = list(
            (
                await db.execute(
                    select(QAMessage.id).where(
                        QAMessage.session_id == session_id,
                        QAMessage.created_at > after_created_at,
                    )
                )
            ).scalars().all()
        )
        if ids:
            await self._delete_message_ids(db, ids)

    async def _delete_message_ids(self, db: AsyncSession, message_ids: list[int]) -> None:
        await db.execute(delete(QAMessageSource).where(QAMessageSource.message_id.in_(message_ids)))
        await db.execute(delete(QAMessage).where(QAMessage.id.in_(message_ids)))
        await db.flush()


    async def suggest_questions(self, db: AsyncSession, session_id: int) -> dict:
        pids = list(
            (await db.execute(select(QASessionPaper.paper_id).where(QASessionPaper.session_id == session_id)))
            .scalars()
            .all()
        )
        if not pids:
            return {'questions': ['请先上传文献，我将为您生成推荐问题'], 'session_id': session_id}

        papers = (await db.execute(select(Paper).where(Paper.id.in_(pids)))).scalars().all()
        infos = (
            await db.execute(select(PaperExtractedInfo).where(PaperExtractedInfo.paper_id.in_(pids)))
        ).scalars().all()
        info_map = {info.paper_id: info for info in infos}

        titles: list[str] = []
        snippets: list[str] = []
        for paper in papers:
            info = info_map.get(paper.id)
            title = (info.title if info and info.title else None) or paper.title or paper.original_filename or f'Paper {paper.id}'
            titles.append(title)
            parts: list[str] = []
            if info:
                for field, label in (
                    ('abstract', '摘要'),
                    ('research_question', '研究问题'),
                    ('method', '方法'),
                    ('main_results', '主要结果'),
                ):
                    val = getattr(info, field, None)
                    if val:
                        parts.append(f'{label}: {str(val)[:300]}')
            if not parts and paper.keywords:
                parts.append(f'关键词: {str(paper.keywords)[:200]}')
            snippets.append(' '.join(parts) or '（暂无结构化摘要，请结合标题与研究领域生成具体问题）')

        fallback = self._fallback_suggested_questions(titles)
        joined = '\n'.join([f'— 《{t}》: {s}' for t, s in zip(titles, snippets)])[:3000]
        prompt = (
            '根据以下文献信息，生成 4 个有深度、与文献内容紧密相关的研究问题，供研究者深入探索。'
            '问题应具体、可回答，避免空泛套话。仅输出 JSON 数组，格式：["问题1","问题2","问题3","问题4"]\n\n'
            f'文献信息：\n{joined}'
        )
        try:
            text = await self.llm.async_chat(
                [
                    {'role': 'system', 'content': '你为研究者生成引导性问题。只输出 JSON 字符串数组，不要 Markdown 或解释。'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.5,
                max_tokens=600,
            )
            questions = self._parse_suggested_questions(text)
            if questions:
                return {'questions': questions[:4], 'session_id': session_id}
        except Exception as exc:
            logger.warning('[suggest_questions] LLM 生成失败 session_id=%s: %s', session_id, exc)

        return {'questions': fallback, 'session_id': session_id}

    @staticmethod
    def _parse_suggested_questions(text: str) -> list[str]:
        from app.utils.json_utils import loads

        raw = (text or '').strip()
        if not raw:
            return []
        match = re.search(r'\[[\s\S]*?\]', raw)
        if not match:
            return []
        parsed = loads(match.group(0), default=None)
        if not isinstance(parsed, list):
            return []
        out: list[str] = []
        for item in parsed:
            if isinstance(item, str):
                q = item.strip()
                if q:
                    out.append(q)
        return out

    @staticmethod
    def _fallback_suggested_questions(titles: list[str]) -> list[str]:
        clean = [t.strip() for t in titles if t and t.strip()]
        if not clean:
            return [
                '这篇文献的核心创新点是什么？',
                '论文采用了什么方法或模型？',
                '实验结果与结论有哪些？',
                '该方法存在哪些局限？',
            ]
        if len(clean) == 1:
            short = clean[0][:28]
            return [
                f'《{short}》的核心创新点是什么？',
                '这篇论文的方法/模型架构是怎样的？',
                '实验设置与主要结果有哪些？',
                '与同类方法相比优势与不足是什么？',
            ]
        joined = '、'.join(clean[:2][:18])
        if len(clean) > 2:
            joined += f' 等 {len(clean)} 篇'
        return [
            f'{joined} 的核心贡献分别是什么？',
            '这些文献在方法上有何异同？',
            '各自的实验结论是否可复现？',
            '综合这些文献，未来有哪些研究方向？',
        ]

    async def _get_or_create_session(
        self,
        db: AsyncSession,
        user_id: int,
        question: str,
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
