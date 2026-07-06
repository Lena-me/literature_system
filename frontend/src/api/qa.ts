import { API_PREFIX, http, LLM_HTTP_TIMEOUT } from './client'

import type { ChatMessage, SessionDetail, SessionSummary, SuggestedQuestions } from '@/types/domain'



export type AskStreamPayload = {

  question: string

  paper_ids?: number[]

  session_id?: number

  top_k?: number

  regenerate?: boolean

}



export type AskStreamResult = {

  receivedDone: boolean

}



function parseSsePart(part: string): unknown | null {

  const line = part.split('\n').find(x => x.startsWith('data:'))

  if (!line) return null

  try {

    return JSON.parse(line.slice(5).trim())

  } catch {

    console.warn('[qaApi] SSE JSON parse failed:', line.slice(0, 120))

    return null

  }

}



export const qaApi = {

  ask: (payload: AskStreamPayload) =>

    http.post<any, { session_id: number; answer: string; sources: any[] }>('/qa/ask', payload),



  async askStream(

    payload: AskStreamPayload,

    onEvent: (event: any) => void | Promise<void>,

    options?: { signal?: AbortSignal },

  ): Promise<AskStreamResult> {

    const token = localStorage.getItem('access_token')

    const res = await fetch(`${API_PREFIX}/qa/ask-stream`, {

      method: 'POST',

      headers: {

        'Content-Type': 'application/json',

        ...(token ? { Authorization: `Bearer ${token}` } : {}),

      },

      body: JSON.stringify(payload),

      signal: options?.signal,

    })

    if (!res.ok || !res.body) throw new Error(await res.text())



    const reader = res.body.getReader()

    const decoder = new TextDecoder('utf-8')

    let buffer = ''

    let receivedDone = false



    const dispatchEvents = async (parts: string[]) => {

      for (const part of parts) {

        const event = parseSsePart(part)

        if (!event || typeof event !== 'object') continue

        if ((event as any).type === 'done') receivedDone = true

        await Promise.resolve(onEvent(event))

      }

    }



    const consumeBuffer = async (flush = false) => {

      const chunks = buffer.split('\n\n')

      if (!flush) {

        buffer = chunks.pop() || ''

      } else {

        buffer = ''

      }

      await dispatchEvents(chunks.filter(Boolean))

    }



    try {

      while (true) {

        const { done, value } = await reader.read()

        if (done) break

        buffer += decoder.decode(value, { stream: true })

        await consumeBuffer(false)

      }

      buffer += decoder.decode()

      await consumeBuffer(true)

    } catch (e: any) {

      if (e?.name === 'AbortError') throw e

      buffer += decoder.decode()

      await consumeBuffer(true)

      console.error('[qaApi] Stream read error:', e)

      if (!receivedDone) {

        await Promise.resolve(onEvent({ type: 'stream_interrupted' }))

      }

    }



    return { receivedDone }

  },



  sessions: () => http.get<any, SessionSummary[]>('/qa/sessions'),

  getSession: (id: number, signal?: AbortSignal) =>

    http.get<any, SessionDetail>(`/qa/sessions/${id}`, { signal }),

  createSession: (payload?: { title?: string; paper_ids?: number[] }) =>

    http.post<any, SessionDetail>('/qa/sessions', payload || {}),

  updateSession: (id: number, payload: { title?: string; add_paper_ids?: number[]; remove_paper_ids?: number[] }) =>

    http.patch<any, SessionDetail>(`/qa/sessions/${id}`, payload),

  deleteSession: (id: number) => http.delete(`/qa/sessions/${id}`),



  messages: (sessionId: number, limit?: number, signal?: AbortSignal) => {

    const params = limit ? `?limit=${limit}` : ''

    return http.get<any, ChatMessage[]>(`/qa/sessions/${sessionId}/messages${params}`, {

      signal,

      timeout: LLM_HTTP_TIMEOUT,

    })

  },



  deleteMessageTail: (sessionId: number, messageId: number) =>

    http.delete<any, { deleted: number }>(`/qa/sessions/${sessionId}/messages/${messageId}/tail`),



  suggestedQuestions: (sessionId: number) =>

    http.get<any, SuggestedQuestions>(`/qa/sessions/${sessionId}/suggested-questions`, {

      timeout: LLM_HTTP_TIMEOUT,

    }),



  generateSessionTitle: (sessionId: number, firstMessage: string) =>

    http.post<any, { title: string }>(

      `/qa/sessions/${sessionId}/generate-title`,

      { first_message: firstMessage },

      { timeout: LLM_HTTP_TIMEOUT },

    ),

}


