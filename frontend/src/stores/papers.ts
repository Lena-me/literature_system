import { defineStore } from 'pinia'
import { papersApi } from '@/api/papers'
import type { ParseStatusEvent } from '@/api/papers'
import type { ContentItem, Paper } from '@/types/domain'
import { useNotebookStore } from '@/stores/notebook'

const DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024
const TERMINAL_PARSE_STATUSES = new Set(['completed', 'indexed', 'failed', 'deleted'])
const PARSE_POLL_MS = 5000
const PARSE_SSE_RECONNECT_MS = 2000

function sleep(ms: number) {
  return new Promise<void>(resolve => setTimeout(resolve, ms))
}

export const usePaperStore = defineStore('papers', {
  state: () => ({
    list: [] as Paper[],
    current: null as Paper | null,
    selectedIds: [] as number[],
    content: [] as ContentItem[],
    loading: false,
    parseEventsAbort: null as AbortController | null,
    parseEventsGeneration: 0,
    parsePollTimer: null as ReturnType<typeof setInterval> | null,
  }),
  getters: {
    selectedPapers: s => s.list.filter(p => s.selectedIds.includes(p.id)),
    parsedPapers: s => s.list.filter(p => p.parse_status === 'completed' || p.parse_status === 'indexed'),
  },
  actions: {
    async load(params?: { keyword?: string; status?: string; limit?: number }) {
      this.loading = true
      try {
        const incoming = await papersApi.list({ limit: params?.limit ?? 200, ...params })
        // 合并进行中的本地状态，避免 load 覆盖 SSE/轮询已更新的状态
        const processing = new Map(
          this.list
            .filter(p => p.parse_status && !TERMINAL_PARSE_STATUSES.has(p.parse_status))
            .map(p => [p.id, p.parse_status] as const),
        )
        this.list = incoming.map((p: Paper) => {
          if (TERMINAL_PARSE_STATUSES.has(p.parse_status)) return p
          const localStatus = processing.get(p.id)
          if (localStatus && !TERMINAL_PARSE_STATUSES.has(localStatus)) {
            return { ...p, parse_status: localStatus }
          }
          return p
        })
        this.syncParsePolling()
        return this.list
      } finally {
        this.loading = false
      }
    },

    applyParseUpdate(update: { id: number; parse_status: string; title?: string }) {
      const idx = this.list.findIndex(p => p.id === update.id)
      if (idx >= 0) {
        const current = this.list[idx]
        this.list = this.list.map((p, i) =>
          i === idx
            ? {
                ...current,
                parse_status: update.parse_status,
                title: update.title ?? current.title,
              }
            : p,
        )
      }

      try {
        const notebook = useNotebookStore()
        if (notebook.activeSources.some(p => p.id === update.id)) {
          notebook.activeSources = notebook.activeSources.map(p =>
            p.id === update.id
              ? { ...p, parse_status: update.parse_status, title: update.title ?? p.title }
              : p,
          )
        }
      } catch {
        // notebook store 未初始化时忽略
      }

      this.syncParsePolling()
    },

    handleParseStatusEvent(event: ParseStatusEvent) {
      if (event.type !== 'parse_status' || event.paper_id == null || !event.parse_status) return
      this.applyParseUpdate({
        id: event.paper_id,
        parse_status: event.parse_status,
        title: event.title,
      })
    },

    /** 建立 SSE 订阅 + 对进行中任务启动轮询兜底 */
    ensureParseSync() {
      this.connectParseEvents()
      this.syncParsePolling()
    },

    connectParseEvents() {
      if (this.parseEventsAbort) return

      const generation = ++this.parseEventsGeneration
      const controller = new AbortController()
      this.parseEventsAbort = controller

      const runLoop = async () => {
        while (!controller.signal.aborted && this.parseEventsGeneration === generation) {
          try {
            await papersApi.subscribeParseEvents(
              event => this.handleParseStatusEvent(event),
              { signal: controller.signal },
            )
          } catch (err: unknown) {
            const error = err as Error
            if (error?.name === 'AbortError' || controller.signal.aborted) break
            console.warn('[papers] parse-events disconnected:', error.message)
          }

          if (controller.signal.aborted || this.parseEventsGeneration !== generation) break
          await sleep(PARSE_SSE_RECONNECT_MS)
        }

        if (this.parseEventsAbort === controller) {
          this.parseEventsAbort = null
        }
      }

      void runLoop()
    },

    disconnectParseEvents() {
      this.parseEventsGeneration += 1
      this.parseEventsAbort?.abort()
      this.parseEventsAbort = null
      this.stopParsePolling()
    },

    processingPaperIds(): number[] {
      return this.list
        .filter(p => p.parse_status && !TERMINAL_PARSE_STATUSES.has(p.parse_status))
        .map(p => p.id)
    },

    syncParsePolling() {
      if (this.processingPaperIds().length > 0) {
        this.startParsePolling()
      } else {
        this.stopParsePolling()
      }
    },

    startParsePolling() {
      if (this.parsePollTimer) return

      const poll = async () => {
        const ids = this.processingPaperIds()
        if (!ids.length) {
          this.stopParsePolling()
          return
        }
        try {
          const rows = await papersApi.parseStatuses(ids)
          for (const row of rows) {
            this.applyParseUpdate({
              id: row.id,
              parse_status: row.parse_status,
              title: row.title,
            })
          }
        } catch {
          // 轮询失败静默，下次重试
        }
      }

      void poll()
      this.parsePollTimer = setInterval(() => void poll(), PARSE_POLL_MS)
    },

    stopParsePolling() {
      if (this.parsePollTimer) {
        clearInterval(this.parsePollTimer)
        this.parsePollTimer = null
      }
    },

    /** 重新解析：乐观更新 + 确保订阅/轮询（多篇并发重解析时避免 load 竞态） */
    async reparsePaper(id: number) {
      await papersApi.reparse(id)
      this.applyParseUpdate({ id, parse_status: 'queued' })
      this.ensureParseSync()
    },

    toggleSelect(id: number) {
      this.selectedIds = this.selectedIds.includes(id)
        ? this.selectedIds.filter(x => x !== id)
        : [...this.selectedIds, id]
    },
    async open(paper: Paper) {
      this.current = paper
      this.content = await papersApi.content(paper.id)
    },
    async upload(file: File, onProgress?: (n: number) => void) {
      const paper = await papersApi.upload(file, onProgress)
      await this.load()
      this.ensureParseSync()
      return paper
    },
    async batchUpload(files: File[], onProgress?: (n: number) => void) {
      const result = await papersApi.batchUpload(files, onProgress)
      await this.load()
      this.ensureParseSync()
      return result
    },
    async chunkUpload(file: File, onProgress?: (n: number) => void, chunkSize = DEFAULT_CHUNK_SIZE) {
      const totalChunks = Math.ceil(file.size / chunkSize)
      const session = await papersApi.initChunkUpload({
        filename: file.name,
        total_size: file.size,
        total_chunks: totalChunks,
        chunk_size: chunkSize,
      })
      const cacheKey = `chunk-upload:${file.name}:${file.size}`
      localStorage.setItem(cacheKey, session.upload_id)
      let received = new Set<number>()
      try {
        const status = await papersApi.chunkStatus(session.upload_id)
        received = new Set(status.received || [])
      } catch { /* ignore */ }
      for (let i = 0; i < totalChunks; i += 1) {
        if (received.has(i)) {
          onProgress?.(Math.round(((i + 1) / totalChunks) * 100))
          continue
        }
        const start = i * chunkSize
        const end = Math.min(file.size, start + chunkSize)
        await papersApi.uploadChunk(session.upload_id, i, file.slice(start, end))
        onProgress?.(Math.round(((i + 1) / totalChunks) * 100))
      }
      const paper = await papersApi.completeChunkUpload(session.upload_id)
      localStorage.removeItem(cacheKey)
      await this.load()
      this.ensureParseSync()
      return paper
    },
    async smartUpload(files: File[], onProgress?: (n: number) => void) {
      const pdfs = files.filter(f => f.name.toLowerCase().endsWith('.pdf'))
      if (!pdfs.length) return []
      if (pdfs.length >= 2) return await this.batchUpload(pdfs, onProgress)
      const file = pdfs[0]
      if (file.size >= 8 * 1024 * 1024) return [await this.chunkUpload(file, onProgress)]
      return [await this.upload(file, onProgress)]
    },
  },
})
