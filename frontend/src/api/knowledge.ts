import { http } from './client'
import type { KnowledgeGraph } from '@/types/domain'
export const knowledgeApi = {
  create: (payload: { paper_ids: number[]; name?: string }) => http.post<any, KnowledgeGraph>('/knowledge-graphs', payload),
  get: (id: number) => http.get<any, KnowledgeGraph>(`/knowledge-graphs/${id}`)
}
