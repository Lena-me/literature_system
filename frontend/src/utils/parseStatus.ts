export const TERMINAL_PARSE_STATUSES = new Set(['completed', 'indexed', 'failed', 'deleted'])

export function isParseTerminal(status?: string | null): boolean {
  return !!status && TERMINAL_PARSE_STATUSES.has(status)
}

export function isParseReady(status?: string | null): boolean {
  return status === 'completed' || status === 'indexed'
}

export function parseStatusLabel(status?: string | null): string {
  switch (status) {
    case 'completed':
    case 'indexed':
      return '已解析'
    case 'failed':
      return '解析失败'
    case 'queued':
      return '排队中'
    case 'extracting':
      return '抽取中'
    case 'vectorizing':
      return '向量化中'
    case 'uploaded':
      return '已上传'
    case 'processing':
    case 'parsing':
      return '解析中'
    case 'pending':
      return '等待中'
    default:
      return status ? String(status) : '解析中'
  }
}

export function parseStatusClass(status?: string | null): string {
  if (isParseReady(status)) return 'ready'
  if (status === 'failed') return 'failed'
  return 'processing'
}
