import { http } from './client'
export const featuresApi = {
  compare: (payload: { paper_ids: number[]; dimensions?: string[]; name?: string }) => http.post('/comparisons', payload),
  guide: (paper_id: number) => http.post('/experiments/reproducibility-guides', { paper_id }),
  overview: () => http.get('/learning-records/overview'),
  record: (payload: { paper_id?: number; event_type: string; event_data?: Record<string, unknown> }) => http.post('/learning-records', payload),
  evidenceMatrix: (payload: { paper_ids: number[]; question?: string }) => http.post('/analytics/evidence-matrix', payload),
  researchRadar: (payload: { paper_ids: number[] }) => http.post('/analytics/research-radar', payload),
  hotspots: () => http.get('/analytics/hotspots')
}
