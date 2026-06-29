import { API_PREFIX, http } from './client'
import type { ChatMessage } from '@/types/domain'
export const qaApi = {
  ask: (payload: { question: string; paper_ids?: number[]; session_id?: number; top_k?: number }) => http.post<any, { session_id: number; answer: string; sources: any[] }>('/qa/ask', payload),
  async askStream(payload: { question: string; paper_ids?: number[]; session_id?: number; top_k?: number }, onEvent: (event: any) => void) {
    const token = localStorage.getItem('access_token')
    const res = await fetch(`${API_PREFIX}/qa/ask-stream`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(payload) })
    if (!res.ok || !res.body) throw new Error(await res.text())
    const reader = res.body.getReader(); const decoder = new TextDecoder('utf-8'); let buffer = ''
    while (true) {
      const { done, value } = await reader.read(); if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n'); buffer = parts.pop() || ''
      for (const part of parts) {
        const line = part.split('\n').find(x => x.startsWith('data:'))
        if (line) onEvent(JSON.parse(line.slice(5).trim()))
      }
    }
  },
  sessions: () => http.get('/qa/sessions'),
  messages: (sessionId: number) => http.get<any, ChatMessage[]>(`/qa/sessions/${sessionId}/messages`)
}
