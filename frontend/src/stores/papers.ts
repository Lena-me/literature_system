import { defineStore } from 'pinia'
import { papersApi } from '@/api/papers'
import { featuresApi } from '@/api/features'
import type { ContentItem, Paper } from '@/types/domain'

const DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024

async function recordLearningEvent(eventType: string, paperId?: number, eventData?: Record<string, unknown>) {
  try {
    await featuresApi.record({ paper_id: paperId, event_type: eventType, event_data: eventData })
  } catch {
    // 学习记录失败不影响主流程
  }
}

export const usePaperStore = defineStore('papers', {
  state: () => ({ list: [] as Paper[], current: null as Paper | null, selectedIds: [] as number[], content: [] as ContentItem[], loading: false }),
  getters: { selectedPapers: s => s.list.filter(p => s.selectedIds.includes(p.id)), parsedPapers: s => s.list.filter(p => p.parse_status === 'completed' || p.parse_status === 'indexed') },
  actions: {
    async load(params?: { keyword?: string; status?: string }) { this.loading = true; try { this.list = await papersApi.list(params); return this.list } finally { this.loading = false } },
    toggleSelect(id: number) { this.selectedIds = this.selectedIds.includes(id) ? this.selectedIds.filter(x => x !== id) : [...this.selectedIds, id] },
    async open(paper: Paper) { this.current = paper; this.content = await papersApi.content(paper.id); recordLearningEvent('paper_open', paper.id) },
    async upload(file: File, onProgress?: (n: number) => void) { const paper = await papersApi.upload(file, onProgress); await this.load(); recordLearningEvent('paper_upload', paper?.id, { filename: file.name }); return paper },
    async batchUpload(files: File[], onProgress?: (n: number) => void) { const result = await papersApi.batchUpload(files, onProgress); await this.load(); result.forEach((p: Paper) => p && recordLearningEvent('paper_upload', p?.id)); return result },
    async chunkUpload(file: File, onProgress?: (n: number) => void, chunkSize = DEFAULT_CHUNK_SIZE) {
      const totalChunks = Math.ceil(file.size / chunkSize)
      const session = await papersApi.initChunkUpload({ filename: file.name, total_size: file.size, total_chunks: totalChunks, chunk_size: chunkSize })
      const cacheKey = `chunk-upload:${file.name}:${file.size}`
      localStorage.setItem(cacheKey, session.upload_id)
      let received = new Set<number>()
      try {
        const status = await papersApi.chunkStatus(session.upload_id)
        received = new Set(status.received || [])
      } catch {}
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
      recordLearningEvent('paper_upload', paper?.id, { filename: file.name })
      return paper
    },
    async smartUpload(files: File[], onProgress?: (n: number) => void) {
      const pdfs = files.filter(f => f.name.toLowerCase().endsWith('.pdf'))
      if (!pdfs.length) return []
      if (pdfs.length >= 2) return await this.batchUpload(pdfs, onProgress)
      const file = pdfs[0]
      if (file.size >= 8 * 1024 * 1024) return [await this.chunkUpload(file, onProgress)]
      return [await this.upload(file, onProgress)]
    }
  }
})
