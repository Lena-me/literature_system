export interface PixelRect {
  x: number
  y: number
  width: number
  height: number
}

export interface NormalizedRect {
  left: number
  top: number
  width: number
  height: number
}

interface EdgeRect {
  top: number
  left: number
  right: number
  bottom: number
}

/**
 * 合并零碎的 DOMRect（PDF.js 文本层划选常见）
 * @param rects getClientRects() 原始矩形
 * @param xThreshold 同行相邻块 X 轴最大间距（像素）
 * @param yThreshold 同一行 Y 轴容差（像素）
 */
export function mergeClientRects(
  rects: DOMRectList | DOMRect[] | ArrayLike<DOMRect>,
  xThreshold = 4,
  yThreshold = 4,
): PixelRect[] {
  const sortedRects = Array.from(rects)
    .filter(r => r.width > 0 && r.height > 0)
    .sort((a, b) => {
      if (Math.abs(a.top - b.top) > yThreshold) return a.top - b.top
      return a.left - b.left
    })

  const merged: EdgeRect[] = []
  let currentRect: EdgeRect | null = null

  for (const rect of sortedRects) {
    if (!currentRect) {
      currentRect = {
        top: rect.top,
        left: rect.left,
        right: rect.right,
        bottom: rect.bottom,
      }
      continue
    }

    const isSameLine = Math.abs(currentRect.top - rect.top) <= yThreshold
    const isCloseOnX = rect.left - currentRect.right <= xThreshold

    if (isSameLine && isCloseOnX) {
      currentRect.top = Math.min(currentRect.top, rect.top)
      currentRect.bottom = Math.max(currentRect.bottom, rect.bottom)
      currentRect.right = Math.max(currentRect.right, rect.right)
    } else {
      merged.push(currentRect)
      currentRect = {
        top: rect.top,
        left: rect.left,
        right: rect.right,
        bottom: rect.bottom,
      }
    }
  }

  if (currentRect) merged.push(currentRect)

  return merged.map(r => ({
    x: r.left,
    y: r.top,
    width: r.right - r.left,
    height: r.bottom - r.top,
  }))
}

/** 视口像素矩形 → 相对 page-inner 的 0~1 归一化坐标 */
export function pixelRectsToNormalized(
  rects: PixelRect[],
  containerRect: DOMRect,
): NormalizedRect[] {
  if (containerRect.width <= 0 || containerRect.height <= 0) return []
  return rects.map(r => ({
    left: (r.x - containerRect.left) / containerRect.width,
    top: (r.y - containerRect.top) / containerRect.height,
    width: r.width / containerRect.width,
    height: r.height / containerRect.height,
  }))
}

/** 划选 DOMRect 一步合并并归一化 */
export function mergeSelectionRects(
  clientRects: DOMRectList | DOMRect[],
  containerRect: DOMRect,
  xThreshold = 4,
  yThreshold = 4,
): NormalizedRect[] {
  const merged = mergeClientRects(clientRects, xThreshold, yThreshold)
  return pixelRectsToNormalized(merged, containerRect)
}
