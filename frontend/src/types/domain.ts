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
export interface ContentItem { id: number; type: string; level?: number | null; content: string; page_number?: number | null; order_index: number }
export interface ChatMessage { id?: number; role: 'user' | 'assistant'; content: string; created_at?: string; sources?: Source[] }
export interface Source { paper_id: number; page_number?: number; section_title?: string; text?: string; snippet?: string; similarity_score?: number; rerank_score?: number }
export interface Report { id: number; paper_id: number; title: string; content: any; created_at: string }
export interface GraphNode { id: number | string; type: string; name: string; properties?: Record<string, unknown> }
export interface GraphEdge { id?: number | string; source: number | string; target: number | string; relation_type: string; properties?: Record<string, unknown> }
export interface KnowledgeGraph { id: number; name: string; nodes: GraphNode[]; edges: GraphEdge[] }
export interface OperationOverview { paper_count: number; report_count: number; qa_count: number; records: any[]; recent_records?: any[]; keyword_cloud?: Record<string, number> }
