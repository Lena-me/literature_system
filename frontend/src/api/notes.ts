import { http } from './client'

export interface HighlightRect {
  left: number
  top: number
  width: number
  height: number
}

export interface PaperNote {
  id: number
  paper_id: number
  page_number: number
  bbox: HighlightRect[]
  selected_text: string
  note_content?: string | null
  highlight_color: string
  created_at: string
  updated_at: string
}

export interface PaperNoteCreatePayload {
  paper_id: number
  page_number: number
  bbox: HighlightRect[]
  selected_text: string
  note_content?: string | null
  highlight_color?: string
}

export interface PaperNoteUpdatePayload {
  note_content?: string | null
  highlight_color?: string
}

export const notesApi = {
  list: (paperId: number) =>
    http.get<any, PaperNote[]>('/paper-notes', { params: { paper_id: paperId } }),

  create: (payload: PaperNoteCreatePayload) =>
    http.post<any, PaperNote>('/paper-notes', payload),

  update: (noteId: number, payload: PaperNoteUpdatePayload) =>
    http.put<any, PaperNote>(`/paper-notes/${noteId}`, payload),

  delete: (noteId: number) =>
    http.delete<any, { message: string }>(`/paper-notes/${noteId}`),
}
