const HASH_FILENAME = /^[a-f0-9]{16,}(?:\.[a-z0-9]+)?$/i

export function isTechnicalFilename(name?: string | null): boolean {
  if (!name) return false
  const base = name.trim()
  if (HASH_FILENAME.test(base)) return true
  if (/^[a-f0-9]{8,}[\._-]/i.test(base)) return true
  return false
}

function stripExtension(name: string): string {
  return name.replace(/\.(pdf|docx?|txt)$/i, '').trim()
}

export function displayPaperTitle(paper: {
  id: number
  title?: string | null
  original_filename?: string | null
}): string {
  const title = (paper.title || '').trim()
  if (title && !isTechnicalFilename(title)) return title

  const filename = (paper.original_filename || '').trim()
  if (filename && !isTechnicalFilename(filename)) {
    return stripExtension(filename)
  }

  return `未命名文献 ${paper.id}`
}

export type PaperReadiness = 'ready' | 'processing' | 'failed' | 'unknown'

export function paperReadiness(status?: string | null): PaperReadiness {
  switch (status) {
    case 'completed':
    case 'parsed':
    case 'success':
      return 'ready'
    case 'failed':
      return 'failed'
    case 'pending':
    case 'queued':
    case 'parsing':
    case 'extracting':
    case 'vectorizing':
    case 'processing':
      return 'processing'
    default:
      return 'unknown'
  }
}

/** 产品化状态文案：就绪时不显示文字，仅 processing/failed 需要提示 */
export function paperReadinessLabel(status?: string | null): string {
  switch (paperReadiness(status)) {
    case 'processing':
      return '整理中'
    case 'failed':
      return '暂不可用'
    default:
      return ''
  }
}

export function paperReadinessHint(status?: string | null): string {
  switch (paperReadiness(status)) {
    case 'processing':
      return '文献仍在整理，关联说明可能较少'
    case 'failed':
      return '该文献暂不可用，仍可尝试加入图谱'
    default:
      return ''
  }
}

export function formatPaperAuthors(value: unknown): string {
  if (value == null) return ''
  if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean).join('、')
  return String(value).trim()
}

export function paperSubtitle(paper: {
  authors?: unknown
  publication_year?: number | null
  year?: number | null
  journal_conf?: string | null
}): string {
  const authors = formatPaperAuthors(paper.authors) || '作者待补充'
  const year = paper.publication_year || paper.year
  const yearText = year ? `${year} 年` : '年份待补充'
  const source = (paper.journal_conf || '').trim()
  return source ? `${authors} · ${yearText} · ${source}` : `${authors} · ${yearText}`
}
