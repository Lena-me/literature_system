import type { RelatedVisual, Source } from '@/types/domain'

export function parseSourceBbox(raw: unknown): [number, number, number, number] | null {
  if (Array.isArray(raw) && raw.length === 4) {
    const nums = raw.map(v => Number(v))
    if (nums.every(v => Number.isFinite(v))) {
      return nums as [number, number, number, number]
    }
  }
  if (raw && typeof raw === 'object') {
    const box = raw as Record<string, unknown>
    if ('left' in box && 'top' in box && 'width' in box && 'height' in box) {
      const left = Number(box.left)
      const top = Number(box.top)
      const width = Number(box.width)
      const height = Number(box.height)
      if ([left, top, width, height].every(v => Number.isFinite(v))) {
        return [left, top, left + width, top + height]
      }
    }
  }
  return null
}

type PdfReaderLike = {
  jumpTo?: (page: number, text?: string) => Promise<void> | void
  highlightAndScrollTo?: (page: number, bbox: [number, number, number, number]) => Promise<void> | void
  whenReady?: (timeoutMs?: number) => Promise<boolean>
}

/** 从摘要概要或结构化来源中提取适合 PDF 文本高亮的片段 */
export function extractHighlightText(source: Source): string {
  if (source.locate_snippet?.trim()) {
    return source.locate_snippet.trim().slice(0, 220)
  }
  const raw = (source.snippet || source.text || '').trim()
  if (!raw) return ''

  const zh = raw.match(/摘要[：:]\s*([\s\S]+?)(?:\n(?:研究问题|方法|主要结果|创新点|标题)[：:]|$)/)
  if (zh?.[1]?.trim()) return zh[1].trim().slice(0, 220)

  const en = raw.match(/abstract[：:]\s*([\s\S]+?)(?:\n(?:research|method|title)[：:]|$)/i)
  if (en?.[1]?.trim()) return en[1].trim().slice(0, 220)

  return raw.slice(0, 220)
}

export async function navigateSourceInPdf(
  pdfReader: PdfReaderLike | null | undefined,
  source: Source,
  delayMs = 250,
): Promise<void> {
  if (!pdfReader) return

  if (typeof pdfReader.whenReady === 'function') {
    await pdfReader.whenReady(12000)
  }

  const page = source.page_number || 1
  const bbox = parseSourceBbox(source.bbox)
  const highlightText = extractHighlightText(source)

  if (delayMs > 0) {
    await new Promise(resolve => setTimeout(resolve, delayMs))
  }

  if (bbox && typeof pdfReader.highlightAndScrollTo === 'function') {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        await pdfReader.highlightAndScrollTo(page, bbox)
        return
      } catch {
        await new Promise(resolve => setTimeout(resolve, 300))
      }
    }
  }

  await pdfReader.jumpTo?.(page, highlightText)
}

export async function navigateVisualInPdf(
  pdfReader: PdfReaderLike | null | undefined,
  visual: RelatedVisual,
  paperId: number,
  delayMs = 250,
): Promise<void> {
  if (!pdfReader) return

  if (typeof pdfReader.whenReady === 'function') {
    await pdfReader.whenReady(12000)
  }

  const page = visual.page_number || 1
  const bbox = parseSourceBbox(visual.bbox)

  if (delayMs > 0) {
    await new Promise(resolve => setTimeout(resolve, delayMs))
  }

  if (bbox && typeof pdfReader.highlightAndScrollTo === 'function') {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        await pdfReader.highlightAndScrollTo(page, bbox)
        return
      } catch {
        await new Promise(resolve => setTimeout(resolve, 300))
      }
    }
  }

  // 图表定位：仅跳页，不用 caption 做文本高亮（避免误匹配到表前说明文字）
  await pdfReader.jumpTo?.(page)
}

export function visualLabel(visual: RelatedVisual): string {
  const prefix = visual.type === 'table' ? '表' : '图'
  const caption = (visual.caption || '').trim()
  if (caption) return caption.length > 28 ? `${caption.slice(0, 28)}…` : caption
  return `${prefix} · 第 ${visual.page_number || '?'} 页`
}

export function sourceLocateLabel(source: Source): string {
  if (source.locate_type === 'bbox' || source.bbox) return '精准定位'
  if (source.locate_type === 'abstract') return '摘要定位'
  if (source.page_number) return '页内跳转'
  return ''
}
