export interface PaperLinkMeta {
  doi?: string | null
  official_url?: string | null
}

const ARXIV_DOI_RE = /^10\.48550\/arXiv\.(\d{4}\.\d{4,5}(?:v\d+)?)$/i
const DOI_RE = /^10\.\d{4,9}\/\S+$/i
const ARXIV_ID_RE = /^(\d{4}\.\d{4,5}(?:v\d+)?)$/

export interface PaperLinkRef {
  title?: string | null
  official_url?: string | null
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function normalizeTitle(value: string): string {
  return value
    .replace(/\*\*/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

export function isOfficialPaperUrl(url: string | null | undefined): boolean {
  if (!url) return false
  const u = url.toLowerCase()
  if (u.includes('scholar.google.com')) return false
  return (
    u.includes('arxiv.org') ||
    u.includes('doi.org') ||
    u.includes('ieeexplore.ieee.org') ||
    u.includes('dl.acm.org') ||
    u.includes('pubmed.ncbi.nlm.nih.gov') ||
    u.includes('ncbi.nlm.nih.gov/pubmed') ||
    u.includes('scopus.com') ||
    u.includes('webofscience.com')
  )
}

export function officialUrlPriority(url: string | null | undefined): number {
  if (!url) return 0
  const u = url.toLowerCase()
  if (u.includes('arxiv.org')) return 100
  if (u.includes('ieeexplore.ieee.org') || u.includes('dl.acm.org')) return 95
  if (u.includes('pubmed.ncbi.nlm.nih.gov') || u.includes('ncbi.nlm.nih.gov/pubmed')) return 95
  if (u.includes('scopus.com')) return 90
  if (u.includes('webofscience.com')) return 90
  if (u.includes('doi.org')) return 80
  if (u.includes('scholar.google.com')) return 5
  return 50
}

function findRefUrl(boldInner: string, refs: PaperLinkRef[]): string | null {
  const inner = normalizeTitle(boldInner)
  if (!inner || inner.length < 3) return null

  let best: { url: string; score: number } | null = null
  for (const ref of refs) {
    const rawTitle = ref.title?.trim()
    const url = ref.official_url?.trim()
    if (!rawTitle || !url || !isOfficialPaperUrl(url)) continue

    const refNorm = normalizeTitle(rawTitle)
    if (!refNorm) continue

    let score = officialUrlPriority(url)
    if (inner === refNorm) {
      score += 100 + refNorm.length
    } else if (refNorm.startsWith(inner) || inner.startsWith(refNorm)) {
      score += 60 + Math.min(inner.length, refNorm.length)
    } else if (inner.length >= 12 && refNorm.includes(inner.slice(0, Math.min(24, inner.length)))) {
      score += 40 + inner.length
    } else if (refNorm.length >= 12 && inner.includes(refNorm.slice(0, Math.min(24, refNorm.length)))) {
      score += 40 + refNorm.length
    } else {
      continue
    }

    if (!best || score > best.score) {
      best = { url, score }
    }
  }

  return best?.url ?? null
}

/** 将回答中的 **论文名** / [论文名](url) 替换为可点击 Markdown 链接 */
export function injectPaperTitleLinks(markdown: string, refs: PaperLinkRef[] | null | undefined): string {
  if (!markdown || !refs?.length) return markdown

  let out = markdown

  out = out.replace(/\*\*([^*\n]+)\*\*/g, (match, inner: string, offset: number) => {
    const before = out.slice(Math.max(0, offset - 1), offset)
    if (before === ']' || before === '!') return match

    const url = findRefUrl(inner, refs)
    if (!url) return match
    return `[**${inner.trim()}**](${url})`
  })

  const sorted = [...refs]
    .filter(r => r.title?.trim() && r.official_url?.trim() && isOfficialPaperUrl(r.official_url))
    .sort((a, b) => (b.title!.length - a.title!.length))

  for (const ref of sorted) {
    const title = ref.title!.trim()
    const url = ref.official_url!.trim()
    const pat = new RegExp(`(?<!\\*\\*)\\[(${escapeRegExp(title)})\\]\\(${escapeRegExp(url)}\\)`, 'gi')
    out = out.replace(pat, `[**$1**](${url})`)
  }

  return out
}

export function resolveOfficialPaperUrl(meta: PaperLinkMeta | null | undefined): string | null {
  if (!meta) return null
  if (meta.official_url) return meta.official_url

  const raw = (meta.doi || '').trim().replace(/[.,;]+$/, '')
  if (!raw) return null

  const arxivDoi = raw.match(ARXIV_DOI_RE)
  if (arxivDoi) return `https://arxiv.org/abs/${arxivDoi[1]}`

  if (DOI_RE.test(raw)) return `https://doi.org/${raw}`

  if (ARXIV_ID_RE.test(raw)) return `https://arxiv.org/abs/${raw}`

  if (raw.toLowerCase().startsWith('arxiv:')) {
    const id = raw.slice(6).trim()
    if (ARXIV_ID_RE.test(id)) return `https://arxiv.org/abs/${id}`
  }

  return null
}

export function officialLinkLabel(url: string | null | undefined): string {
  if (!url) return '官网溯源'
  const u = url.toLowerCase()
  if (u.includes('arxiv.org')) return '查看 arXiv'
  if (u.includes('doi.org')) return '查看 DOI'
  if (u.includes('ieeexplore.ieee.org')) return '查看 IEEE'
  if (u.includes('dl.acm.org')) return '查看 ACM'
  if (u.includes('pubmed.ncbi.nlm.nih.gov') || u.includes('ncbi.nlm.nih.gov/pubmed')) return '查看 PubMed'
  if (u.includes('scopus.com')) return '查看 Scopus'
  if (u.includes('webofscience.com')) return '查看 WoS'
  if (u.includes('scholar.google.com')) return 'Scholar 检索'
  return '官网溯源'
}

function wrapOfficialLink(match: string): string {
  return `<a href="${match}" target="_blank" rel="noopener noreferrer" class="scholarly-link">${match}</a>`
}

/** 为 Markdown 渲染出的外链补上 target="_blank" 与 scholarly-link 样式 */
export function ensureExternalLinksOpenInNewTab(html: string): string {
  if (!html) return html

  return html.replace(/<a\s+([^>]*href="(https?:\/\/[^"]+)"[^>]*)>/gi, (full, attrs, href) => {
    if (/target\s*=/.test(attrs)) return full
    let next = attrs
    if (!/\bclass\s*=/.test(attrs) && isOfficialPaperUrl(href)) {
      next += ' class="scholarly-link"'
    }
    return `<a ${next} target="_blank" rel="noopener noreferrer">`
  })
}

/** 将正文中的 DOI / arXiv / IEEE / ACM / PubMed 等编号与 URL 转为可点击外链 */
export function linkifyScholarlyReferences(html: string): string {
  if (!html) return html

  let out = html

  out = out.replace(
    /(?<!href="https?:\/\/doi\.org\/)(?<![\w/"=])((10\.\d{4,9}\/[-._;()/:A-Z0-9]+))(?!\.org)/gi,
    (_match, doi: string) => {
      const clean = doi.replace(/[.,;]+$/, '')
      return `<a href="https://doi.org/${clean}" target="_blank" rel="noopener noreferrer" class="scholarly-link">${clean}</a>`
    },
  )

  out = out.replace(
    /(?<!\/abs\/)(?<![\w/"=])(arXiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?))/gi,
    (_match, _full: string, id: string) =>
      `<a href="https://arxiv.org/abs/${id}" target="_blank" rel="noopener noreferrer" class="scholarly-link">${_full}</a>`,
  )

  out = out.replace(
    /(?<!href=")(https?:\/\/arxiv\.org\/abs\/(\d{4}\.\d{4,5}(?:v\d+)?))/gi,
    (match) => wrapOfficialLink(match),
  )

  const publisherPatterns = [
    /(?<!href=")(https?:\/\/ieeexplore\.ieee\.org\/document\/\d+)/gi,
    /(?<!href=")(https?:\/\/dl\.acm\.org\/doi\/[^\s<"]+)/gi,
    /(?<!href=")(https?:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/\d+)/gi,
    /(?<!href=")(https?:\/\/ncbi\.nlm\.nih\.gov\/pubmed\/\d+)/gi,
    /(?<!href=")(https?:\/\/(?:apps\.)?webofscience\.com\/[^\s<"]+)/gi,
    /(?<!href=")(https?:\/\/(?:www\.)?scopus\.com\/[^\s<"]+)/gi,
  ]
  for (const pat of publisherPatterns) {
    out = out.replace(pat, (match) => wrapOfficialLink(match))
  }

  out = out.replace(
    /(<a\s+[^>]*href="[^"]*(?:arxiv\.org|doi\.org|ieeexplore\.ieee\.org|dl\.acm\.org|pubmed\.ncbi|scopus\.com|webofscience\.com)[^"]*"[^>]*)(>)/gi,
    (match, open, close) => (open.includes('class=') ? match : `${open} class="scholarly-link"${close}`),
  )

  return out
}

export function sanitizePaperTitle(title: string | null | undefined): string {
  if (!title) return ''
  return title
    .replace(/\*\*/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}
