import { defineStore } from 'pinia'
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { qaApi } from '@/api/qa'
import type { ChatMessage, KnowledgeDomain, SessionDetail, SessionPaper, SessionSummary, Source, StreamStage } from '@/types/domain'

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
  const isStreaming = ref(false)
  const isSwitchingSession = ref(false) // ★ loading 指示器
  const draftInput = ref('')

  // ========== 缓存 + 请求取消 ==========
  const messageCache = new Map<number, ChatMessage[]>()
  const detailCache = new Map<number, SessionDetail>()
  let switchAbortController: AbortController | null = null

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
      activeMessages.value = cachedMsgs
      isSwitchingSession.value = false
      return
    }

    // ★ 未命中缓存：显示 loading，但保留旧内容不闪白
    isSwitchingSession.value = true
    // 注意：不清空 activeMessages（stale-while-revalidate）

    try {
      const [detail, msgs] = await Promise.all([
        qaApi.getSession(sessionId, signal),
        qaApi.messages(sessionId, 100, signal),
      ])

      // 已被新请求取消，丢弃旧结果
      if (signal.aborted) return

      activeSessionDetail.value = detail
      activeSources.value = detail.papers || []
      activeMessages.value = msgs

      detailCache.set(sessionId, detail)
      messageCache.set(sessionId, msgs)
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

  async function sendMessage(text: string, mentionedIds?: number[] | null) {
    if (!text.trim() || isStreaming.value || !activeSessionId.value) return

    const question = text.trim()
    const isFirstMessage = activeMessages.value.length === 0
    activeMessages.value.push({ role: 'user', content: question })
    isStreaming.value = true

    const assistant: ChatMessage = { role: 'assistant', content: '', sources: [], streamStage: 'embedding' }
    activeMessages.value.push(assistant)

    try {
      const paperIds = mentionedIds && mentionedIds.length > 0
        ? mentionedIds
        : (activeSources.value.length > 0 ? activeSources.value.map(p => p.id) : null)

      await qaApi.askStream(
        { question, paper_ids: paperIds as any, session_id: activeSessionId.value },
        async (event) => {
          if (event.type === 'session') {
            activeSessionId.value = event.session_id
          }
          if (event.type === 'sources') {
            assistant.sources = event.sources
          }
          if (event.type === 'status' && event.stage) {
            assistant.streamStage = event.stage as StreamStage
          }
          if (event.type === 'delta') {
            if (event.content) assistant.streamStage = undefined
            assistant.content += event.content
          }
          if (event.type === 'done') {
            assistant.streamStage = undefined
            assistant.content = event.answer || assistant.content
            if (event.sources?.length) {
              assistant.sources = event.sources
            }
          }
          if (event.type === 'error') {
            assistant.content = `❌ 对话失败：${event.error}`
          }
          await nextTick()
        }
      )
    } catch (e: any) {
      assistant.content = `❌ 对话失败：${e?.message || '未知错误'}`
    } finally {
      isStreaming.value = false
      // ★ 发送消息后，清除该会话缓存，下次切换会重新拉取最新消息
      if (activeSessionId.value) {
        messageCache.delete(activeSessionId.value)
        detailCache.delete(activeSessionId.value)
      }
      await loadSessions()

      // ★ 首条消息后自动生成标题
      const sessionId = activeSessionId.value
      if (isFirstMessage && sessionId) {
        const listed = sessions.value.find(s => s.id === sessionId)
        const currentTitle = listed?.title || activeSessionDetail.value?.title || ''
        if (isDefaultTitle(currentTitle)) {
          console.log('[auto-title] 触发标题生成', { sessionId, question })
          await autoGenerateTitle(sessionId, question)
        }
      }
    }
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
    clearMessages,
    openReadingDrawer,
    closeReadingDrawer,
    loadDomains,
    toggleSidebar,
    saveDraft,
    updateSessionTitle,
  }
})
