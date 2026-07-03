import { http, rawDownload } from './client'
import type { Report } from '@/types/domain'
export const reportsApi = {
  create: (payload: { paper_id: number; modules?: string[]; title?: string }) => http.post<any, Report>('/reports', payload),
  list: () => http.get<any, Report[]>('/reports'),
  export: (id: number, format: 'docx' | 'pdf' | 'md' = 'md') => rawDownload(`/reports/${id}/export`, { format }),
  remove: (id: number) => http.delete(`/reports/${id}`)
}
