import { http } from './client'
export const featuresApi = {
  compare: (payload: { paper_ids: number[]; dimensions?: string[]; name?: string }) =>
    http.post('/comparisons', payload) as unknown as Promise<any>,
  suggestCompareName: (payload: { paper_ids: number[]; dimensions?: string[] }) =>
    http.post('/comparisons/suggest-name', payload) as unknown as Promise<{ name: string }>,
  compareList: () =>
    http.get('/comparisons') as unknown as Promise<any[]>,
  compareDetail: (id: number) =>
    http.get(`/comparisons/${id}`) as unknown as Promise<any>,
  deleteCompare: (id: number) =>
    http.delete(`/comparisons/${id}`) as unknown as Promise<any>,
  guide: (paper_id: number) => http.post('/experiments/reproducibility-guides', { paper_id }),
  overview: () => http.get('/learning-records/overview'),
  record: (payload: { paper_id?: number; event_type: string; event_data?: Record<string, unknown> }) => http.post('/learning-records', payload),
  evidenceMatrix: (payload: { paper_ids: number[]; question?: string; dimensions?: string[] }) =>
    http.post('/analytics/evidence-matrix', payload) as unknown as Promise<any>,
  researchRadar: (payload: { paper_ids: number[] }) => http.post('/analytics/research-radar', payload),
  hotspots: () => http.get('/analytics/hotspots')
}
