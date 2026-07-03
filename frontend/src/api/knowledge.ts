import { http } from './client'
import type { KnowledgeGraph, KnowledgeDomain, DomainOverview, DomainSuggestion, MergeSuggestion, MergeResult, CoverageInfo, RegionRecommendation } from '@/types/domain'

export interface GraphListItem {
  id: number
  name: string
  domain_id: number | null
  paper_count: number
  created_at: string
}

export const knowledgeApi = {
  // 知识图谱
  create: (payload: { paper_ids: number[]; name?: string; domain_id?: number }) =>
    http.post<KnowledgeGraph>('/knowledge-graphs', payload),
  list: (domainId?: number) =>
    http.get<GraphListItem[]>('/knowledge-graphs', { params: domainId !== undefined ? { domain_id: domainId } : {} }),
  get: (id: number) =>
    http.get<KnowledgeGraph>(`/knowledge-graphs/graph/${id}`),

  // 知识域
  createDomain: (payload: { name: string; description?: string; icon?: string; parent_domain_id?: number }) =>
    http.post<KnowledgeDomain>('/knowledge-graphs/domains', payload),
  listDomains: () =>
    http.get<KnowledgeDomain[]>('/knowledge-graphs/domains'),
  getDomain: (id: number) =>
    http.get<KnowledgeDomain>(`/knowledge-graphs/domains/${id}`),
  updateDomain: (id: number, payload: { name?: string; description?: string; icon?: string }) =>
    http.put<KnowledgeDomain>(`/knowledge-graphs/domains/${id}`, payload),
  deleteDomain: (id: number) =>
    http.delete<{ message: string }>(`/knowledge-graphs/domains/${id}`),
  getDomainOverview: (id: number) =>
    http.get<DomainOverview>(`/knowledge-graphs/domains/${id}/overview`),

  // AI 感知：域推荐
  suggestDomain: (payload: { paper_ids: number[] }) =>
    http.post<{ suggestions: DomainSuggestion[] }>('/knowledge-graphs/domains/suggest', payload),

  // 实体融合
  getMergeSuggestions: (domainId: number) =>
    http.get<{ suggestions: MergeSuggestion[] }>(`/knowledge-graphs/domains/${domainId}/merge-suggestions`),
  mergeEntities: (domainId: number, payload: { source_node_id: number; target_node_id: number }) =>
    http.post<MergeResult>(`/knowledge-graphs/domains/${domainId}/merge`, payload),

  // 知识推荐
  getRecommendations: (domainId: number) =>
    http.get<{ recommendations: RegionRecommendation[]; source: string }>(`/knowledge-graphs/domains/${domainId}/recommendations`),
  exploreConcept: (domainId: number, payload: { concept: string; source: string }) =>
    http.post<{ message: string }>(`/knowledge-graphs/domains/${domainId}/explore`, payload),
}
