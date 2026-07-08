import { http } from './client'
import type {
  KnowledgeDomain,
  DomainOverview,
  DomainSuggestion,
  MergeSuggestion,
  MergeResult,
  RegionRecommendation,
} from '@/types/domain'

export type BuildMode = 'fast' | 'deep'
export type RelationStrength = 'strong' | 'medium' | 'weak'

export interface LiteratureGraphNode {
  id: string
  db_id?: number
  type: 'paper' | string
  entity_type: 'paper' | string
  paper_id: number
  name: string
  title: string
  label: string
  authors?: string | null
  year?: number | null
  journal_conf?: string | null
  doi?: string | null
  keywords?: string[]
  abstract?: string | null
  research_question?: string | null
  method?: string | null
  main_results?: string | null
  innovations?: string | null
  parse_status?: string | null
  centrality?: number
  degree?: number
  size?: number
  properties?: Record<string, unknown>
}

export interface LiteratureGraphEdge {
  id: string
  db_id?: number
  source: string
  target: string
  source_node_id?: string
  target_node_id?: string
  relation_type: string
  score: number
  strength: RelationStrength
  relation_types?: string[]
  shared_keywords?: string[]
  shared_terms?: string[]
  explanation?: string
  difference?: string
  properties?: Record<string, unknown>
}

export interface LiteratureGraphSummary {
  paper_count: number
  relation_count: number
  strong_count: number
  weak_count: number
  topic_count: number
  themes: string[]
  core_papers: Array<{ paper_id: number; title: string; label?: string }>
  year_range?: [number, number] | null
  status_hint?: string
  description?: string
}

export interface LiteratureGraph {
  id: number
  name: string
  domain_id?: number | null
  domain_name?: string | null
  created_at?: string | null
  nodes: LiteratureGraphNode[]
  edges: LiteratureGraphEdge[]
  summary?: LiteratureGraphSummary
}

export interface GraphListItem {
  id: number
  name: string
  domain_id: number | null
  domain_name?: string | null
  paper_count: number
  node_count?: number
  edge_count?: number
  relation_count?: number
  created_at: string | null
  status?: 'completed' | 'generating' | 'failed' | string
}

export interface LiteratureGraphCreatePayload {
  paper_ids: number[]
  name?: string
  domain_id?: number | null
  build_mode?: BuildMode
  include_weak?: boolean
}

export interface LiteratureGraphNamePayload {
  paper_ids: number[]
  topic_name?: string
}

export const knowledgeApi = {
  // 文献关系图谱
  suggestName: (payload: LiteratureGraphNamePayload) =>
    http.post<{ name: string }>('/knowledge-graphs/suggest-name', payload),
  create: (payload: LiteratureGraphCreatePayload) =>
    http.post<LiteratureGraph>('/knowledge-graphs', payload),
  list: (domainId?: number | null) =>
    http.get<GraphListItem[]>('/knowledge-graphs', { params: domainId ? { domain_id: domainId } : {} }),
  get: (id: number) =>
    http.get<LiteratureGraph>(`/knowledge-graphs/graph/${id}`),
  deleteGraph: (id: number) =>
    http.delete<{ message: string }>(`/knowledge-graphs/graph/${id}`),
  regenerateGraph: (id: number) =>
    http.post<LiteratureGraph>(`/knowledge-graphs/graph/${id}/regenerate`),

  // 研究主题：仍复用后端 /domains 路径，前端显示为“研究主题”。
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

  // 兼容旧页面。后端已降级为空结果。
  suggestDomain: (payload: { paper_ids: number[] }) =>
    http.post<{ suggestions: DomainSuggestion[] }>('/knowledge-graphs/domains/suggest', payload),
  getMergeSuggestions: (domainId: number) =>
    http.get<{ suggestions: MergeSuggestion[] }>(`/knowledge-graphs/domains/${domainId}/merge-suggestions`),
  mergeEntities: (domainId: number, payload: { source_node_id: number; target_node_id: number }) =>
    http.post<MergeResult>(`/knowledge-graphs/domains/${domainId}/merge`, payload),
  getRecommendations: (domainId: number) =>
    http.get<{ recommendations: RegionRecommendation[]; source: string }>(`/knowledge-graphs/domains/${domainId}/recommendations`),
  exploreConcept: (domainId: number, payload: { concept: string; source: string }) =>
    http.post<{ message: string }>(`/knowledge-graphs/domains/${domainId}/explore`, payload),
}
