import { API_PREFIX, http } from './client'
import type { ChatMessage, SessionDetail, SessionSummary, SuggestedQuestions } from '@/types/domain'
export const qaApi = {
  ask: (payload: { question: string; paper_ids?: number[]; session_id?: number; top_k?: number }) => http.post<any, { session_id: number; answer: string; sources: any[] }>('/qa/ask', payload),
  async askStream(payload: { question: string; paper_ids?: number[]; session_id?: number; top_k?: number }, onEvent: (event: any) => void) {
    const token = localStorage.getItem('access_token')
    const res = await fetch(`${API_PREFIX}/qa/ask-stream`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(payload) })
    if (!res.ok || !res.body) throw new Error(await res.text())
    const reader = res.body.getReader(); const decoder = new TextDecoder('utf-8'); let buffer = ''
    try {
      while (true) {
        const { done, value } = await reader.read(); if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n'); buffer = parts.pop() || ''
        for (const part of parts) {
          const line = part.split('\n').find(x => x.startsWith('data:'))
          if (line) onEvent(JSON.parse(line.slice(5).trim()))
        }
      }
    } catch (e) {
      console.error('[qaApi] Stream read error:', e)
      onEvent({ type: 'error', error: '连接中断，请重试' })
    }
  },
  // ===== Session CRUD =====
  sessions: () => http.get<any, SessionSummary[]>('/qa/sessions'),
  getSession: (id: number, signal?: AbortSignal) => http.get<any, SessionDetail>(`/qa/sessions/${id}`, { signal }),
  createSession: (payload?: { title?: string; paper_ids?: number[] }) =>
    http.post<any, SessionDetail>('/qa/sessions', payload || {}),
  updateSession: (id: number, payload: { title?: string; add_paper_ids?: number[]; remove_paper_ids?: number[] }) =>
    http.patch<any, SessionDetail>(`/qa/sessions/${id}`, payload),
  deleteSession: (id: number) => http.delete(`/qa/sessions/${id}`),
  messages: (sessionId: number, limit?: number, signal?: AbortSignal) => {
    const params = limit ? `?limit=${limit}` : ''
    return http.get<any, ChatMessage[]>(`/qa/sessions/${sessionId}/messages${params}`, { signal })
  },
  suggestedQuestions: (sessionId: number) => http.get<any, SuggestedQuestions>(`/qa/sessions/${sessionId}/suggested-questions`),
  generateSessionTitle: (sessionId: number, firstMessage: string) => http.post<any, { title: string }>(`/qa/sessions/${sessionId}/generate-title`, { first_message: firstMessage }),
}
