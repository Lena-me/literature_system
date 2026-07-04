export type Role = 'researcher' | 'admin'
export interface User {
  id: number
  username: string
  name?: string | null
  email?: string | null
  phone?: string | null
  role: Role | string
  status: string
  paper_upload_count?: number
  report_generate_count?: number
  created_at?: string
}
export interface TokenOut { access_token: string; token_type: string; user: User }
export interface Paper {
  id: number
  original_filename: string
  file_size: number
  upload_time: string
  parse_status: string
  title?: string | null
  authors?: string[] | string | null
  keywords?: string[] | string | null
  subject_labels?: string[] | string | null
  notes?: string | null
  category_id?: number | null
  doi?: string | null
  publication_year?: number | null
  journal_conf?: string | null
}
export interface ContentItem { id: number; type: string; level?: number | null; content: string; bbox?: [number, number, number, number] | null; page_number?: number | null; order_index: number }
export type StreamStage =
  | 'classifying'
  | 'embedding'
  | 'searching'
  | 'reranking'
  | 'comparing'
  | 'generating'

export type StreamFlow = 'rag' | 'compare' | 'general'

export interface ChatMessage {
  id?: number
  role: 'user' | 'assistant'
  content: string
  /** LLM 思考/推理过程（与正文分开展示） */
  reasoning?: string
  /** 流式思考阶段是否展开 */
  reasoningExpanded?: boolean
  created_at?: string
  sources?: Source[]
  /** 流式问答当前阶段（仅 assistant 生成过程中） */
  streamStage?: StreamStage
  /** 流式进度条所属流程（由 stage 事件推断） */
  streamFlow?: StreamFlow
  /** 用户中止生成 */
  cancelled?: boolean
}
export interface RelatedVisual {
  id: number
  type: 'figure' | 'table' | string
  caption?: string | null
  page_number?: number | null
  image_path?: string | null
  bbox?: [number, number, number, number] | null
  locate_snippet?: string | null
  section_id?: number | null
}

export interface Source {
  chunk_id?: number
  paper_id: number
  page_number?: number
  section_id?: number | null
  section_title?: string
  text?: string
  snippet?: string
  similarity_score?: number
  rerank_score?: number
  bbox?: [number, number, number, number] | null
  start_position?: number
  end_position?: number
  related_figures?: RelatedVisual[]
  synthetic?: boolean
  locate_type?: 'bbox' | 'abstract' | 'page' | 'none' | string
  locate_snippet?: string
  ref_index?: number
  ref_label?: string
}
export interface Report { id: number; paper_id: number; title: string; content: any; created_at: string }
export interface GraphNode { 
  id: number | string
  entity_type: string
  name: string
  properties?: Record<string, unknown>
  // 向后兼容
  type?: string
}
export interface GraphEdge { 
  id?: number | string
  source_node_id?: number | string
  target_node_id?: number | string
  relation_type: string
  properties?: Record<string, unknown>
  // 向后兼容
  source?: number | string
  target?: number | string
}
export interface KnowledgeGraph { id: number; name: string; domain_id?: number | null; nodes: GraphNode[]; edges: GraphEdge[] }
export interface GraphSummary { id: number; name: string; created_at: string }
export interface OperationOverview { paper_count: number; report_count: number; qa_count: number; records: any[]; recent_records?: any[]; keyword_cloud?: Record<string, number> }

// ========== Notebook / Session 相关类型 ==========

export interface SessionPaper {
  id: number
  title: string
  original_filename: string
  parse_status: string
  authors?: string[] | string | null
  publication_year?: number | null
}

export interface SessionSummary {
  id: number
  title: string
  paper_count: number
  paper_ids: number[]
  last_message_preview?: string
  created_at: string
  updated_at: string
}

export interface SessionDetail {
  id: number
  user_id: number
  title: string
  papers: SessionPaper[]
  paper_count: number
  created_at: string
  updated_at: string
}

export interface KnowledgeDomain {
  id: number
  name: string
  description?: string | null
  icon: string
  parent_domain_id?: number | null
  graph_count: number
  paper_count: number
  created_at: string
  updated_at: string
}

export interface DomainOverview {
  domain: KnowledgeDomain
  graphs: GraphSummary[]
  coverage?: CoverageInfo
  recommendation_count?: number
}

export interface CoverageInfo {
  coverage_rate: number
  covered_count: number
  suggested_count: number
  core_concepts: string[]
  missing_concepts: string[]
}

export interface RegionRecommendation {
  concept: string
  entity_type: string
  reason: string
  source: 'relation' | 'llm'
  node_id: number | null
  score: number | null
  bridge_nodes: string[]
}

export interface DomainSuggestion {
  domain_id: number | null
  domain_name: string
  match_type: 'existing' | 'new'
  reason: string
  paper_count_in_domain: number
}

export interface MergeSuggestion {
  node_a: { id: number; name: string; type: string }
  node_b: { id: number; name: string; type: string }
  similarity: number
}

export interface MergeResult {
  merged_edges: number
  deleted_duplicates: number
  message: string
}

export interface SuggestedQuestions {
  questions: string[]
  session_id?: number
}
