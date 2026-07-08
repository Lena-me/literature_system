export function slugifyHeading(text: string) {
  const base = text
    .trim()
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
  return base || 'section'
}

const MISSING_REPORT_PHRASES = [
  '当前解析未提取到明确证据',
  '当前解析未提取到该维度的明确证据',
  '原文片段中未充分体现该项信息。',
  '原文片段中未充分体现该项信息',
  '原文片段中未充分体现',
  '当前解析未提取到明确研究问题，可结合摘要和引言进一步确认。',
  '当前解析未提取到独立的研究背景与核心问题',
  '当前解析未提取到明确数值型指标。',
  '当前解析未提取到明确方法流程。',
  '暂未生成拓展检索式。',
  '暂未生成可点击文献溯源链接。',
  '暂未在当前用户文献库中找到“同方向但方法不同”的已解析论文。',
  '暂未抽取',
]

function stripInlineMarkdown(text: string) {
  return text
    .replace(/\*\*/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .trim()
}

/** 判断是否为“未提取到”类占位文案 */
export function isMissingReportContent(content?: string) {
  const value = String(content || '').trim()
  if (!value || value === '-' || value === '—') return true

  const plain = stripInlineMarkdown(value)
  if (!plain || plain === '-') return true

  if (MISSING_REPORT_PHRASES.some(phrase => plain === phrase || plain.startsWith(phrase))) {
    return true
  }

  if (/^当前解析未提取/.test(plain)) return true
  if (/^原文片段中未充分体现/.test(plain)) return true
  if (/^暂未(?:抽取|生成|在)/.test(plain)) return true

  return false
}

export function displayReportValue(content?: string) {
  return isMissingReportContent(content) ? '-' : String(content || '').trim()
}

/** 参考文献推荐理由：隐藏工程化关键词句 */
export function displayReferenceReason(reason?: string) {
  const text = String(reason || '').trim()
  if (!text || isMissingReportContent(text)) return ''
  if (/^匹配关键词[:：]/.test(text)) return ''
  if (/^来自原文参考文献/.test(text)) return '与本文研究方向相关'
  return text
}

/** 合并被误断行的期刊页码片段，如 "195(jun.26" */
export function mergeOrphanCitationLines(text: string) {
  const lines = text.split('\n')
  const merged: string[] = []
  const citationTailRe = /^(?:[,;]\s*)?\d+\([a-z]{3}\.[\w.]+\)?/i

  for (const line of lines) {
    const trimmed = line.trim()
    if (
      merged.length &&
      trimmed &&
      !trimmed.startsWith('#') &&
      !trimmed.startsWith('-') &&
      !trimmed.startsWith('*') &&
      !/^\d+\.\s/.test(trimmed) &&
      (citationTailRe.test(trimmed) || /^[\d(][\d().a-z:-]{1,60}$/i.test(trimmed))
    ) {
      const prev = merged[merged.length - 1]
      merged[merged.length - 1] = `${prev}${prev.endsWith('-') || prev.endsWith('：') ? '' : ' '}${trimmed}`
      continue
    }
    merged.push(line)
  }
  return merged.join('\n')
}

/** 结构化文献溯源已单独展示时，清理 Markdown 中重复的参考文献段落 */
export function stripDuplicateReferenceMarkdown(text: string) {
  let result = text
    .replace(/\n{2,}##\s*(?:文献溯源链接|可点击文献溯源)\s*\n[\s\S]*$/u, '')
    .replace(/\n{2,}##\s*文献溯源\s*\n[\s\S]*?(?=\n##\s|$)/u, '\n')
    .replace(/\n{2,}##\s*文献溯源\s*\n\s*可点击参考文献已在结构化文献溯源模块中展示；导出文件会保留完整链接列表。\s*$/u, '')
    .replace(/\n#{1,3}\s*原文参考文献(?:溯源|列表)?\s*\n[\s\S]*?(?=\n#{1,3}\s|\n##\s|$)/u, '\n')
    .replace(/\n#{1,3}\s*可点击参考文献\s*\n[\s\S]*?(?=\n#{1,3}\s|\n##\s|$)/u, '\n')

  // 拓展检索模块只保留「基础知识与拓展检索式」，去掉 LLM 追加的重复文献列表
  result = result.replace(
    /(##\s*拓展检索\s*\n)([\s\S]*?)(?=\n##\s|$)/u,
    (_match, heading, body) => {
      const learningBlock = body.match(/###\s*基础知识与拓展检索式[\s\S]*?(?=\n###\s|\n##\s|$)/u)
      if (learningBlock) {
        return `${heading}${learningBlock[0].trim()}\n\n`
      }
      return heading
    },
  )

  return mergeOrphanCitationLines(result).trim()
}

/** 将 Markdown 正文中未提取到的字段统一替换为 "-" */
export function normalizeMissingReportMarkdown(text: string) {
  const lines = text.split('\n')
  const normalized = lines.map(line => {
    const fieldMatch = line.match(/^(\s*(?:[-*]\s+)?\*\*[^*]+\*\*[：:]\s*)(.+)$/)
    if (fieldMatch && isMissingReportContent(fieldMatch[2])) {
      return `${fieldMatch[1]}-`
    }

    const listMatch = line.match(/^(\s*[-*]\s+)(.+)$/)
    if (listMatch && isMissingReportContent(listMatch[2])) {
      return `${listMatch[1]}-`
    }

    const orderedMatch = line.match(/^(\s*\d+\.\s+)(.+)$/)
    if (orderedMatch && isMissingReportContent(orderedMatch[2])) {
      return `${orderedMatch[1]}-`
    }

    if (/^\s*[^#>\-*\d]/.test(line) && isMissingReportContent(line)) {
      return '-'
    }

    return line
  })

  return normalized.join('\n')
}

/** 在 Markdown 渲染完成后为 h2/h3 注入锚点，避免预置 HTML 标题导致后续列表无法解析 */
export function injectHeadingAnchors(html: string) {
  const used = new Set<string>()
  return html.replace(/<h([23])(\s[^>]*)?>([\s\S]*?)<\/h\1>/gi, (match, level, attrs, inner) => {
    if (attrs && /\bid\s*=/.test(String(attrs))) return match
    const plain = String(inner).replace(/<[^>]+>/g, '').trim()
    let id = slugifyHeading(plain)
    let dup = 2
    while (used.has(id)) {
      id = `${slugifyHeading(plain)}-${dup++}`
    }
    used.add(id)
    const attrStr = attrs ? String(attrs) : ''
    return `<h${level} id="${id}"${attrStr}>${inner}</h${level}>`
  })
}

export function parseMarkdownHeadings(markdown: string) {
  const items: Array<{ id: string; label: string; level: 1 | 2 }> = []
  const used = new Set<string>()
  const pattern = /^(#{2,3})\s+(.+)$/gm
  let match: RegExpExecArray | null
  while ((match = pattern.exec(markdown)) !== null) {
    const level: 1 | 2 = match[1].length === 3 ? 2 : 1
    const label = match[2].replace(/\s*\{#.+?\}\s*$/, '').trim()
    let id = slugifyHeading(label)
    let dup = 2
    while (used.has(id)) {
      id = `${slugifyHeading(label)}-${dup++}`
    }
    used.add(id)
    items.push({ id, label, level })
  }
  return items
}
