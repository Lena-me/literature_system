import { http } from './client'

export interface FormulaExtractResult {
  status: string
  latex: string
  cost_ms: number
}

export const formulaApi = {
  extract: (imageBase64: string) =>
    http.post<any, FormulaExtractResult>('/formula/extract', {
      image_base64: imageBase64,
    }),
}
