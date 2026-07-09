import type { LiteratureGraphNode } from '@/api/knowledge'

/**
 * 知性蓝冷色盘 — 与学术浅色主题一致
 * 年份：灰蓝 → 青绿 → 蓝 → 靛紫
 */
export const NODE_PALETTE = {
  slate: '#6b7d93',
  teal: '#14b8a6',
  blue: '#3b82f6',
  indigo: '#6366f1',
} as const

/** 年份渐变锚点 */
const YEAR_COLOR_STOPS: Array<{ t: number; color: string }> = [
  { t: 0, color: NODE_PALETTE.slate },
  { t: 0.34, color: NODE_PALETTE.teal },
  { t: 0.67, color: NODE_PALETTE.blue },
  { t: 1, color: NODE_PALETTE.indigo },
]

export const YEAR_GRADIENT_CSS =
  `linear-gradient(90deg, ${NODE_PALETTE.slate} 0%, ${NODE_PALETTE.teal} 34%, ${NODE_PALETTE.blue} 67%, ${NODE_PALETTE.indigo} 100%)`

export const YEAR_UNKNOWN_COLOR = '#7f91a6'

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
  [NODE_PALETTE.slate]: '#5a6b80',
  [NODE_PALETTE.teal]: '#0d9488',
  [NODE_PALETTE.blue]: '#2563eb',
  [NODE_PALETTE.indigo]: '#4f46e5',
  [YEAR_UNKNOWN_COLOR]: '#6b7d93',
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
  if (strength === 'strong') return focused ? '#1d4ed8' : NODE_PALETTE.blue
  if (strength === 'medium') return focused ? '#64748b' : '#94a3b8'
  return focused ? '#cbd5e1' : '#e2e8f0'
}
