import type { LiteratureGraphNode } from '@/api/knowledge'

/**
 * 莫兰迪色盘 — 低饱和暖调，与 Paper-Material 主题一致
 * 年份：焦糖 → 鼠尾草绿 → 赤陶 → 灰紫
 */
export const NODE_PALETTE = {
  caramel: '#c49a6c',
  sage: '#7d9b76',
  terracotta: '#b87d6a',
  mauve: '#a08b9c',
} as const

/** 年份渐变锚点 */
const YEAR_COLOR_STOPS: Array<{ t: number; color: string }> = [
  { t: 0, color: NODE_PALETTE.caramel },
  { t: 0.34, color: NODE_PALETTE.sage },
  { t: 0.67, color: NODE_PALETTE.terracotta },
  { t: 1, color: NODE_PALETTE.mauve },
]

export const YEAR_GRADIENT_CSS =
  `linear-gradient(90deg, ${NODE_PALETTE.caramel} 0%, ${NODE_PALETTE.sage} 34%, ${NODE_PALETTE.terracotta} 67%, ${NODE_PALETTE.mauve} 100%)`

export const YEAR_UNKNOWN_COLOR = '#b8aea4'

function hexToRgb(hex: string) {
  const normalized = hex.replace('#', '')
  const value = normalized.length === 3
    ? normalized.split('').map(ch => ch + ch).join('')
    : normalized
  return {
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16),
  }
}

function rgbToHex(r: number, g: number, b: number) {
  const toHex = (value: number) => Math.round(value).toString(16).padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

function lerpColor(from: string, to: string, ratio: number) {
  const a = hexToRgb(from)
  const b = hexToRgb(to)
  return rgbToHex(
    a.r + (b.r - a.r) * ratio,
    a.g + (b.g - a.g) * ratio,
    a.b + (b.b - a.b) * ratio,
  )
}

function interpolateYearColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t))
  for (let i = 0; i < YEAR_COLOR_STOPS.length - 1; i += 1) {
    const left = YEAR_COLOR_STOPS[i]
    const right = YEAR_COLOR_STOPS[i + 1]
    if (clamped >= left.t && clamped <= right.t) {
      const span = right.t - left.t || 1
      return lerpColor(left.color, right.color, (clamped - left.t) / span)
    }
  }
  return YEAR_COLOR_STOPS[YEAR_COLOR_STOPS.length - 1].color
}

export function yearToNodeColor(year: number | null | undefined, range: [number, number]): string {
  if (!year) return YEAR_UNKNOWN_COLOR
  const [minYear, maxYear] = range
  const span = Math.max(1, maxYear - minYear)
  const t = Math.max(0, Math.min(1, (year - minYear) / span))
  return interpolateYearColor(t)
}

const HOVER_COLOR_MAP: Record<string, string> = {
  [NODE_PALETTE.caramel]: '#a67c52',
  [NODE_PALETTE.sage]: '#6b8565',
  [NODE_PALETTE.terracotta]: '#a06858',
  [NODE_PALETTE.mauve]: '#8a7586',
  [YEAR_UNKNOWN_COLOR]: '#9c9086',
}

export function emphasizeNodeColor(color: string): string {
  const mapped = HOVER_COLOR_MAP[color.toLowerCase()]
  if (mapped) return mapped
  const { r, g, b } = hexToRgb(color)
  return rgbToHex(r * 0.9, g * 0.9, b * 0.9)
}

export function nodeAuthorShortLabel(node: LiteratureGraphNode): string {
  const fromLabel = String(node.label || '')
    .split(/[，,]/)[0]
    ?.trim()
  if (fromLabel && !['未知', 'unknown', 'Unknown'].includes(fromLabel)) {
    return fromLabel.length > 8 ? `${fromLabel.slice(0, 8)}…` : fromLabel
  }

  const authors = String(node.authors || '').trim()
  if (authors) {
    const first = authors.split(/[;,，；、]|\band\b/i)[0]?.trim() || ''
    if (first) {
      if (/[A-Za-z]/.test(first)) {
        const tokens = first.replace(/\./g, ' ').split(/\s+/).filter(Boolean)
        const last = tokens[tokens.length - 1] || first
        return last.length > 10 ? `${last.slice(0, 10)}…` : last
      }
      return first.length > 6 ? `${first.slice(0, 6)}…` : first
    }
  }

  return '未知'
}

export function nodeYearShortLabel(node: LiteratureGraphNode): string {
  return node.year ? String(node.year) : '—'
}

export function isCoreGraphNode(
  node: LiteratureGraphNode,
  nodes: LiteratureGraphNode[],
): boolean {
  if (!nodes.length) return false
  const maxCentrality = Math.max(...nodes.map(item => item.centrality || 0))
  if (maxCentrality <= 0) return false
  return (node.centrality || 0) >= maxCentrality * 0.88
}

export function morandiEdgeColor(strength?: 'strong' | 'medium' | 'weak', focused = false): string {
  if (strength === 'strong') return focused ? '#a67c52' : NODE_PALETTE.caramel
  if (strength === 'medium') return focused ? '#9c9086' : '#b8aea4'
  return focused ? '#d8d0c4' : '#e8e2d6'
}
