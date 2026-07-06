import { defineStore } from 'pinia'
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { qaApi } from '@/api/qa'
import type { ChatMessage, KnowledgeDomain, QAToolArtifact, SessionDetail, SessionPaper, SessionSummary, Source, StreamFlow, StreamStage } from '@/types/domain'
import { inferStreamFlow } from '@/utils/streamStages'
import { featuresApi } from '@/api/features'
async function recordLearningEvent(eventType: string, paperId?: number, eventData?: Record<string, unknown>) {
  try {
    await featuresApi.record({ paper_id: paperId, event_type: eventType, event_data: eventData })
  } catch {
    // 学习记录失败不影响主流程
  }
}
export const useNotebookStore = defineStore('notebook', () => {
  const router = useRouter()

  // ========== 数据层 ==========
  const domains = ref<KnowledgeDomain[]>([])
  const sessions = ref<SessionSummary[]>([])
  const activeSessionId = ref<number | null>(null)
  const activeSessionDetail = ref<SessionDetail | null>(null)
  const activeSources = ref<SessionPaper[]>([])
  const activeMessages = ref<ChatMessage[]>([])

  // ========== UI 交互层 ==========
  const isSidebarOpen = ref(true)
  const isReadingDrawerOpen = ref(false)
  const currentReadingPaperId = ref<number | null>(null)
  const currentReadingPage = ref(1)
  const currentReadingHighlight = ref('')
  const streamingSessionIds = ref(new Set<number>())
  /** 当前活跃会话是否正在流式生成 */
  const isStreaming = computed(() => {
    const sid = activeSessionId.value
    return sid != null && streamingSessionIds.value.has(sid)
  })
  const isSwitchingSession = ref(false) // ★ loading 指示器
  const draftInput = ref('')
  const scrollTick = ref(0)
  const editingMessageId = ref<number | null>(null)

  // ========== 缓存 + 请求取消 ==========
  const messageCache = new Map<number, ChatMessage[]>()
  /** 工具产物按 message_id 缓存（兼容迁移前或未持久化的消息） */
  const messageArtifactsCache = new Map<number, QAToolArtifact[]>()

  function artifactKey(item: QAToolArtifact): string {
    return `${item.artifact_type}-${item.report_id ?? item.graph_id ?? item.comparison_id ?? ''}`
  }

  function mergeArtifacts(prev: QAToolArtifact[] | undefined, incoming: QAToolArtifact): QAToolArtifact[] {
    const list = [...(prev || [])]
    if (list.some(x => artifactKey(x) === artifactKey(incoming))) return list
    return [...list, incoming]
  }

  function attachArtifactsToMessages(msgs: ChatMessage[]): ChatMessage[] {
    return msgs.map(m => {
      if (m.artifacts?.length) return m
      if (!m.id || !messageArtifactsCache.has(m.id)) return m
      const cached = messageArtifactsCache.get(m.id)!
      if (!cached.length) return m
      return { ...m, artifacts: cached }
    })
  }

  function rememberMessageArtifacts(messageId: number | undefined, artifacts: QAToolArtifact[] | undefined) {
    if (!messageId || !artifacts?.length) return
    messageArtifactsCache.set(messageId, artifacts)
  }
  const detailCache = new Map<number, SessionDetail>()
  let switchAbortController: AbortController | null = null
  const streamAbortControllers = new Map<number, AbortController>()

  function isSessionStreaming(sessionId: number | null | undefined): boolean {
    return sessionId != null && streamingSessionIds.value.has(sessionId)
  }

  function markSessionStreaming(sessionId: number, streaming: boolean) {
    const next = new Set(streamingSessionIds.value)
    if (streaming) next.add(sessionId)
    else next.delete(sessionId)
    streamingSessionIds.value = next
  }

  function syncMessagesToCache(sessionId: number, messages: ChatMessage[]) {
    messageCache.set(sessionId, messages)
  }

  function applyMessagesForSession(sessionId: number, messages: ChatMessage[]) {
    syncMessagesToCache(sessionId, messages)
    if (activeSessionId.value === sessionId) {
      activeMessages.value = messages
      bumpScroll()
    }
  }

  function resolveSessionPaperIds(mentionedIds?: number[] | null): number[] | null {
    if (mentionedIds && mentionedIds.length > 0) return mentionedIds

    const fromSources = activeSources.value.map(p => p.id).filter(id => Number.isFinite(id))
    if (fromSources.length > 0) return fromSources

    const sid = activeSessionId.value
    if (sid) {
      const cached = detailCache.get(sid)
      const fromCache = (cached?.papers || []).map(p => p.id).filter(id => Number.isFinite(id))
      if (fromCache.length > 0) return fromCache
    }

    const fromDetail = (activeSessionDetail.value?.papers || []).map(p => p.id).filter(id => Number.isFinite(id))
    return fromDetail.length > 0 ? fromDetail : null
  }

  function pickFresherSessionDetail(sessionId: number, fetched: SessionDetail): SessionDetail {
    const cached = detailCache.get(sessionId)
    if (!cached) return fetched
    const fetchedCount = fetched.papers?.length ?? 0
    const cachedCount = cached.papers?.length ?? 0
    if (cachedCount > fetchedCount) return cached
    if (cachedCount === fetchedCount && cached.updated_at && fetched.updated_at) {
      return cached.updated_at >= fetched.updated_at ? cached : fetched
    }
    return fetched
  }

  function bumpScroll() {
    scrollTick.value += 1
  }

  // ========== 计算属性 ==========
  const isColdStart = () => activeSources.value.length === 0

  // ========== 会话管理 ==========

  async function loadSessions() {
    sessions.value = await qaApi.sessions()
  }

  async function createSession(title?: string, paperIds?: number[]) {
    const detail = await qaApi.createSession({ title, paper_ids: paperIds })
    await loadSessions()
    await switchSession(detail.id)
    // 标题生成统一在 sendMessage 首条消息后触发，不在此处提前生成
    return detail
  }

  async function switchSession(sessionId: number) {
    recordLearningEvent('session_switch', undefined, { session_id: sessionId })
    // 流式进行中切走：先把当前 UI 消息写入缓存，后台继续更新缓存
    const prevSessionId = activeSessionId.value
    if (prevSessionId && prevSessionId !== sessionId && isSessionStreaming(prevSessionId)) {
      syncMessagesToCache(prevSessionId, [...activeMessages.value])
    }

    // ★ 如果不在 /notebook 页面，先跳转，确保 NotebookView 挂载
    if (router.currentRoute.value.path !== '/notebook') {
      router.push('/notebook')
    }

    // ★ 取消上一次未完成的请求
    if (switchAbortController) {
      switchAbortController.abort()
    }
    switchAbortController = new AbortController()
    const signal = switchAbortController.signal

    activeSessionId.value = sessionId
    isReadingDrawerOpen.value = false

    // ★ 命中缓存：直接展示，0ms 响应
    const cachedDetail = detailCache.get(sessionId)
    const cachedMsgs = messageCache.get(sessionId)
    if (cachedDetail && cachedMsgs) {
      activeSessionDetail.value = cachedDetail
      activeSources.value = cachedDetail.papers || []
      activeMessages.value = attachArtifactsToMessages(cachedMsgs)
      isSwitchingSession.value = false
      bumpScroll()
      return
    }

    // ★ 未命中缓存：显示 loading，但保留旧内容不闪白
    isSwitchingSession.value = true
    // 注意：不清空 activeMessages（stale-while-revalidate）

    try {
      const [fetchedDetail, msgs] = await Promise.all([
        qaApi.getSession(sessionId, signal),
        qaApi.messages(sessionId, 100, signal),
      ])

      // 已被新请求取消，丢弃旧结果
      if (signal.aborted) return

      const detail = pickFresherSessionDetail(sessionId, fetchedDetail)
      activeSessionDetail.value = detail
      activeSources.value = detail.papers || []
      activeMessages.value = attachArtifactsToMessages(msgs)

      detailCache.set(sessionId, detail)
      messageCache.set(sessionId, attachArtifactsToMessages(msgs))
      bumpScroll()
    } catch (e: any) {
      if (e?.name === 'AbortError' || e?.code === 'ERR_CANCELED' || signal.aborted) return
      // 请求出错且仍是当前活跃 session
      if (activeSessionId.value === sessionId) {
        activeSessionDetail.value = null
        activeSources.value = []
        activeMessages.value = []
      }
    } finally {
      if (activeSessionId.value === sessionId) {
        isSwitchingSession.value = false
      }
    }
  }

  async function renameSession(sessionId: number, title: string) {
    await qaApi.updateSession(sessionId, { title })
    await loadSessions()
    if (activeSessionId.value === sessionId && activeSessionDetail.value) {
      activeSessionDetail.value.title = title
    }
  }

  async function deleteSession(sessionId: number) {
    await qaApi.deleteSession(sessionId)
    detailCache.delete(sessionId)
    messageCache.delete(sessionId)
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = null
      activeSessionDetail.value = null
      activeSources.value = []
      activeMessages.value = []
    }
    await loadSessions()
  }

  // ========== 文献管理 ==========

  async function addSources(paperIds: number[], forceSessionId?: number | null) {
    const sid = forceSessionId ?? activeSessionId.value
    if (!sid) return
    const detail = await qaApi.updateSession(sid, { add_paper_ids: paperIds })
    // 仅当仍在同一会话时更新 UI 状态（防止上传完成前用户已切走）
    if (activeSessionId.value === sid || forceSessionId == null) {
      activeSources.value = detail.papers || []
      activeSessionDetail.value = detail
    }
    detailCache.set(sid, detail) // ★ 同步更新缓存，避免切回时覆写
    await loadSessions()
    // 标题生成统一在 sendMessage 首条消息后触发，不在此处提前生成
  }

  async function removeSource(paperId: number) {
    if (!activeSessionId.value) return
    const detail = await qaApi.updateSession(activeSessionId.value, { remove_paper_ids: [paperId] })
    activeSources.value = detail.papers || []
    activeSessionDetail.value = detail
    detailCache.set(activeSessionId.value, detail) // ★ 同步更新缓存，避免切回时覆写
    await loadSessions()
  }

  // ========== 对话 ==========

  function stopStreaming() {
    const sid = activeSessionId.value
    if (sid) streamAbortControllers.get(sid)?.abort()
  }

  function mergeStreamWithRemote(
    local: ChatMessage[],
    remote: ChatMessage[],
    assistantIndex: number,
  ): ChatMessage[] {
    if (!remote.length) return local
    const localAssistant = local[assistantIndex]
    const lastRemote = remote[remote.length - 1]
    const hasRemoteAssistant = lastRemote?.role === 'assistant'
    const localText = `${localAssistant?.content || ''}\n${localAssistant?.reasoning || ''}`.trim()

    if (!hasRemoteAssistant && localAssistant?.role === 'assistant' && localText) {
      return [...remote, { ...localAssistant }]
    }

    if (hasRemoteAssistant && localAssistant?.role === 'assistant') {
      const merged = [...remote]
      const ri = merged.length - 1
      const rm = merged[ri]
      merged[ri] = {
        ...rm,
        content: rm.content || localAssistant.content || '',
        reasoning: rm.reasoning || localAssistant.reasoning || '',
        sources: rm.sources?.length ? rm.sources : localAssistant.sources,
        artifacts: rm.artifacts?.length ? rm.artifacts : localAssistant.artifacts,
        external_refs: rm.external_refs?.length ? rm.external_refs : localAssistant.external_refs,
      }
      return merged
    }

    return remote
  }

  async function syncMessagesFromApi(
    targetSessionId: number,
    localSnapshot: ChatMessage[],
    assistantIndex: number,
  ) {
    try {
      const remote = attachArtifactsToMessages(await qaApi.messages(targetSessionId, 100))
      const merged = mergeStreamWithRemote(localSnapshot, remote, assistantIndex)
      applyMessagesForSession(targetSessionId, merged)
    } catch (e) {
      console.warn('[notebook] sync messages failed, keep local stream', e)
      applyMessagesForSession(targetSessionId, localSnapshot)
    }
  }

  async function reloadMessages() {
    const sessionId = activeSessionId.value
    if (!sessionId) return
    try {
      const msgs = attachArtifactsToMessages(await qaApi.messages(sessionId, 100))
      if (activeSessionId.value === sessionId) {
        activeMessages.value = msgs
        messageCache.set(sessionId, msgs)
        bumpScroll()
      }
    } catch {
      // ignore
    }
  }

  async function editMessage(messageId: number, newText: string) {
    const sessionId = activeSessionId.value
    if (!sessionId || isSessionStreaming(sessionId) || !newText.trim()) return
    await qaApi.deleteMessageTail(sessionId, messageId)
    messageCache.delete(sessionId)
    editingMessageId.value = null
    await reloadMessages()
    await sendMessage(newText.trim())
  }

  function startEditMessage(messageId: number, content: string) {
    editingMessageId.value = messageId
    draftInput.value = content
  }

  function cancelEditMessage() {
    editingMessageId.value = null
    draftInput.value = ''
  }

  async function regenerateLastResponse() {
    if (isSessionStreaming(activeSessionId.value) || !activeSessionId.value) return
    const lastUser = [...activeMessages.value].reverse().find(m => m.role === 'user')
    if (!lastUser) return

    // 移除本地最后一条 assistant（含停止/失败但未入库的消息）
    const lastIdx = activeMessages.value.length - 1
    if (lastIdx >= 0 && activeMessages.value[lastIdx].role === 'assistant') {
      activeMessages.value = activeMessages.value.slice(0, lastIdx)
    }

    messageCache.delete(activeSessionId.value)

    await runAskStream({
      question: lastUser.content || '.',
      regenerate: true,
      appendUserMessage: false,
      isFirstMessage: false,
    })
  }

  async function runAskStream(opts: {
    question: string
    mentionedIds?: number[] | null
    regenerate?: boolean
    appendUserMessage?: boolean
    isFirstMessage?: boolean
  }) {
    const sessionId = activeSessionId.value
    if (!sessionId) return

    const {
      question,
      mentionedIds = null,
      regenerate = false,
      appendUserMessage = true,
      isFirstMessage = false,
    } = opts

    if (appendUserMessage) {
      activeMessages.value.push({ role: 'user', content: question })
      bumpScroll()
    }

    markSessionStreaming(sessionId, true)
    const abortController = new AbortController()
    streamAbortControllers.set(sessionId, abortController)

    const assistantIndex = activeMessages.value.length
    activeMessages.value.push({
      role: 'assistant',
      content: '',
      reasoning: '',
      sources: [],
      streamStage: 'classifying',
      streamFlow: undefined,
      reasoningExpanded: true,
    })
    syncMessagesToCache(sessionId, [...activeMessages.value])
    bumpScroll()

    const getStreamMessages = (): ChatMessage[] =>
      messageCache.get(sessionId) || (activeSessionId.value === sessionId ? activeMessages.value : [])

    const patchAssistant = (patch: Partial<ChatMessage>) => {
      const msgs = [...getStreamMessages()]
      const current = msgs[assistantIndex]
      if (!current || current.role !== 'assistant') return
      msgs[assistantIndex] = { ...current, ...patch }
      applyMessagesForSession(sessionId, msgs)
    }

    let aborted = false
    let receivedDone = false
    let streamInterrupted = false
    let streamSessionId = sessionId
    let pendingStreamArtifacts: QAToolArtifact[] = []

    try {
      const paperIds = resolveSessionPaperIds(mentionedIds)

      const streamResult = await qaApi.askStream(
        {
          question,
          paper_ids: paperIds as any,
          session_id: sessionId,
          regenerate,
        },
        async (event) => {
          if (event.type === 'session' && event.session_id) {
            streamSessionId = event.session_id
            if (activeSessionId.value === sessionId) {
              activeSessionId.value = event.session_id
            }
          }
          if (event.type === 'sources') {
            patchAssistant({ sources: event.sources })
          }
          if (event.type === 'status' && event.stage) {
            const msgs = getStreamMessages()
            const current = msgs[assistantIndex]
            const stage = event.stage as StreamStage
            const streamFlow: StreamFlow | undefined = inferStreamFlow(
              stage,
              current?.streamFlow,
            )
            patchAssistant({ streamStage: stage, streamFlow })
          }
          if (event.type === 'delta' && event.content) {
            const msgs = getStreamMessages()
            const current = msgs[assistantIndex]
            const channel = event.channel || 'content'
            if (channel === 'reasoning') {
              patchAssistant({
                reasoning: (current?.reasoning || '') + event.content,
                reasoningExpanded: true,
              })
            } else {
              patchAssistant({
                streamStage: undefined,
                streamFlow: undefined,
                content: (current?.content || '') + event.content,
                reasoningExpanded: false,
              })
            }
          }
          if (event.type === 'artifact') {
            const artifact = { ...event } as QAToolArtifact & { type?: string }
            delete artifact.type
            pendingStreamArtifacts = mergeArtifacts(pendingStreamArtifacts, artifact)
          }
          if (event.type === 'done') {
            receivedDone = true
            if (event.cancelled) {
              patchAssistant({ streamStage: undefined, streamFlow: undefined, reasoningExpanded: false })
              return
            }
            const msgs = getStreamMessages()
            const current = msgs[assistantIndex]
            const finalArtifacts = event.artifacts?.length
              ? event.artifacts
              : pendingStreamArtifacts.length
                ? pendingStreamArtifacts
                : current?.artifacts
            patchAssistant({
              streamStage: undefined,
              streamFlow: undefined,
              reasoningExpanded: false,
              id: event.message_id ?? current?.id,
              content: event.answer || current?.content || '',
              reasoning: event.reasoning ?? current?.reasoning ?? '',
              sources: event.sources?.length ? event.sources : current?.sources,
              artifacts: finalArtifacts,
              external_refs: event.external_refs != null ? event.external_refs : current?.external_refs,
            })
            rememberMessageArtifacts(event.message_id ?? current?.id, finalArtifacts)
          }
          if (event.type === 'stream_interrupted') {
            streamInterrupted = true
            patchAssistant({ streamStage: undefined, streamFlow: undefined, reasoningExpanded: false })
          }
          if (event.type === 'error') {
            patchAssistant({
              streamStage: undefined,
              streamFlow: undefined,
              reasoningExpanded: false,
              content: `❌ 对话失败：${event.error}`,
            })
          }
          await nextTick()
        },
        { signal: abortController.signal },
      )
      receivedDone = receivedDone || streamResult.receivedDone
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        aborted = true
        const msgs = getStreamMessages()
        const current = msgs[assistantIndex]
        const partial = (current?.content || '').trim()
        patchAssistant({
          streamStage: undefined,
          streamFlow: undefined,
          reasoningExpanded: false,
          cancelled: true,
          artifacts: pendingStreamArtifacts.length ? pendingStreamArtifacts : current?.artifacts,
          content: partial
            ? `${partial}\n\n（已停止生成）`
            : '（已停止生成）',
        })
        messageCache.delete(sessionId)
        detailCache.delete(sessionId)
      } else {
        patchAssistant({
          streamStage: undefined,
          streamFlow: undefined,
          content: `❌ 对话失败：${e?.message || '未知错误'}`,
        })
      }
    } finally {
      streamAbortControllers.delete(sessionId)
      markSessionStreaming(sessionId, false)

      const cachedMsgs = getStreamMessages()
      const finalMsg = cachedMsgs[assistantIndex]
      if (finalMsg?.role === 'assistant' && finalMsg.streamStage) {
        patchAssistant({ streamStage: undefined, streamFlow: undefined, reasoningExpanded: false })
      }

      const refreshedMsgs = getStreamMessages()

      if (!aborted) {
        await syncMessagesFromApi(streamSessionId, refreshedMsgs, assistantIndex)
      } else {
        syncMessagesToCache(sessionId, refreshedMsgs)
      }

      bumpScroll()
      await loadSessions()

      if (isFirstMessage && sessionId && !aborted) {
        const listed = sessions.value.find(s => s.id === sessionId)
        const currentTitle = listed?.title || activeSessionDetail.value?.title || ''
        if (isDefaultTitle(currentTitle)) {
          await autoGenerateTitle(sessionId, question)
        }
      }
    }
  }

  async function sendMessage(text: string, mentionedIds?: number[] | null) {
    if (!text.trim() || !activeSessionId.value) return
    if (isSessionStreaming(activeSessionId.value)) return

    const question = text.trim()
    const isFirstMessage = activeMessages.value.length === 0

    // 若正在编辑某条用户消息，先删 tail 再发送
    if (editingMessageId.value) {
      await editMessage(editingMessageId.value, question)
      return
    }

    await runAskStream({
      question,
      mentionedIds,
      isFirstMessage,
      appendUserMessage: true,
    })
  }

  /** 判断标题是否为默认/空（需要自动生成） */
  function isDefaultTitle(title?: string): boolean {
    if (!title || !title.trim()) return true
    const t = title.trim()
    return t === '新会话' || t === '新对话' || t === '新建会话'
        || t === '未命名' || t === 'New Chat' || t === 'New Session'
        || t === '新研究'
  }

  async function autoGenerateTitle(sessionId: number, message: string) {
    try {
      console.log('[auto-title] 请求后端生成标题...')
      const res = await qaApi.generateSessionTitle(sessionId, message)
      console.log('[auto-title] 后端返回标题:', res.title)
      if (res.title) {
        updateSessionTitle(sessionId, res.title)
        detailCache.delete(sessionId)
        if (activeSessionId.value === sessionId) {
          try {
            const detail = await qaApi.getSession(sessionId)
            activeSessionDetail.value = detail
            detailCache.set(sessionId, detail)
          } catch {
            // 列表标题已更新，详情刷新失败可忽略
          }
        }
      }
    } catch (e: any) {
      console.warn('[auto-title] 生成失败（静默）:', e?.message || e)
    }
  }

  function updateSessionTitle(sessionId: number, title: string) {
    // 更新侧边栏列表
    const idx = sessions.value.findIndex(s => s.id === sessionId)
    if (idx >= 0) sessions.value[idx] = { ...sessions.value[idx], title }
    // 更新当前详情
    if (activeSessionDetail.value && activeSessionDetail.value.id === sessionId) {
      activeSessionDetail.value.title = title
    }
  }

  function clearMessages() {
    activeMessages.value = []
  }

  // ========== 阅读面板 ==========

  function openReadingDrawer(paperId: number, page?: number, highlight?: string) {
    currentReadingPaperId.value = paperId
    currentReadingPage.value = page || 1
    currentReadingHighlight.value = highlight || ''
    isReadingDrawerOpen.value = true
  }

  function closeReadingDrawer() {
    isReadingDrawerOpen.value = false
    currentReadingPaperId.value = null
  }

  // ========== 知识域 ==========

  async function loadDomains() {
    // 预留：后续知识域功能实现时对接后端
    domains.value = []
  }

  function toggleSidebar() {
    isSidebarOpen.value = !isSidebarOpen.value
  }

  // ========== 输入草稿 ==========

  function saveDraft(text: string) {
    draftInput.value = text
  }

  return {
    // 数据层
    domains,
    sessions,
    activeSessionId,
    activeSessionDetail,
    activeSources,
    activeMessages,
    // UI 交互层
    isSidebarOpen,
    isReadingDrawerOpen,
    currentReadingPaperId,
    currentReadingPage,
    currentReadingHighlight,
    isStreaming,
    isSwitchingSession,
    draftInput,
    scrollTick,
    editingMessageId,
    // 方法
    isColdStart,
    loadSessions,
    createSession,
    switchSession,
    renameSession,
    deleteSession,
    addSources,
    removeSource,
    sendMessage,
    stopStreaming,
    reloadMessages,
    editMessage,
    startEditMessage,
    cancelEditMessage,
    regenerateLastResponse,
    clearMessages,
    openReadingDrawer,
    closeReadingDrawer,
    loadDomains,
    toggleSidebar,
    saveDraft,
    updateSessionTitle,
  }
})
