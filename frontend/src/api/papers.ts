import { http, rawDownload } from './client'
import type { ContentItem, Paper } from '@/types/domain'

export const papersApi = {
  list: (params?: { keyword?: string; status?: string; skip?: number; limit?: number }) =>
    http.get<any, Paper[]>('/papers', { params }),

  upload: (file: File, onProgress?: (n: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<any, Paper>('/papers/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: e => onProgress?.(Math.round((e.loaded * 100) / (e.total || e.loaded)))
    })
  },

  batchUpload: (files: File[], onProgress?: (n: number) => void) => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    return http.post<any, Paper[]>('/papers/batch-upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: e => onProgress?.(Math.round((e.loaded * 100) / (e.total || e.loaded)))
    })
  },

  initChunkUpload: (payload: { filename: string; total_size: number; total_chunks: number; chunk_size: number }) =>
    http.post<any, { upload_id: string }>('/papers/upload/init', payload),

  uploadChunk: (upload_id: string, chunk_index: number, blob: Blob) => {
    const form = new FormData()
    form.append('upload_id', upload_id)
    form.append('chunk_index', String(chunk_index))
    form.append('file', blob)
    return http.put('/papers/upload/chunk', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },

  chunkStatus: (upload_id: string) =>
    http.get<any, { upload_id: string; filename: string; received: number[]; total_chunks: number }>(
      `/papers/upload/${upload_id}/status`
    ),

  completeChunkUpload: (upload_id: string) => http.post<any, Paper>('/papers/upload/complete', { upload_id }),

  get: (id: number) => http.get<any, Paper>(`/papers/${id}`),
  update: (id: number, payload: Partial<Paper>) => http.put<any, Paper>(`/papers/${id}`, payload),
  remove: (id: number) => http.delete(`/papers/${id}`),
  content: (id: number) => http.get<any, ContentItem[]>(`/papers/${id}/content`),
  reparse: (id: number) => http.post(`/papers/${id}/reparse`),
  fileUrl: (id: number) => http.get<any, { url: string }>(`/papers/${id}/file-url`),

  fileBlobUrl: async (id: number) => {
    const res = await rawDownload(`/papers/${id}/file`)
    return URL.createObjectURL(res.data)
  },

  createCategory: (name: string, parent_id?: number) => http.post('/papers/categories', { name, parent_id }),
  categories: () => http.get('/papers/categories'),
  updateCategory: (id: number, data: { name: string; parent_id?: number | null }) => http.put(`/papers/categories/${id}`, data),
  deleteCategory: (id: number) => http.delete(`/papers/categories/${id}`),
}
