﻿﻿﻿<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, shallowRef, watch, withDefaults } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'
import {ZoomIn, ZoomOut } from '@element-plus/icons-vue'
import { mergeSelectionRects } from '@/utils/mergeRects'
import { normalizeOcrLatex } from '@/utils/mathRender'
import { formulaApi } from '@/api/formula'
import { ElMessage } from 'element-plus'
import 'pdfjs-dist/web/pdf_viewer.css'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).href

// ============================================================================
// Props / Emits / Expose
// ============================================================================

const props = withDefaults(defineProps<{
  url?: string
  initialPage?: number
  highlightText?: string
  saveHighlightHandler?: (payload: {
    pageNum: number
    text: string
    rects: HighlightRect[]
    colorKey: string
    noteContent?: string
  }) => Promise<{ id: number; color?: string } | null>
  deleteHighlightHandler?: (id: number | string) => Promise<void>
  showFormulaButton?: boolean
}>(), {
  showFormulaButton: true,
})
const emit = defineEmits<{
  (e: 'oldUrlCleanup', url: string): void
  (e: 'highlightSaved'): void
  (e: 'highlightClick', noteId: number): void
  (e: 'formulaModeChange', active: boolean): void
}>()

// ============================================================================
// 响应式状态
// ============================================================================

const containerRef = ref<HTMLElement | null>(null)
const pdfLoading = ref(false)
const error = ref('')
const totalPages = ref(0)
const scale = ref(1)
const userManualZoom = ref(false)
const pageHeightPx = ref(800)           // 骨架屏高度（首页渲染后更新）
const pageWidthPx = ref(566)            // 骨架屏宽度（A4 比例 ≈ height / 1.414）
const scrollPage = ref(1)               // 当前视口最可见的页码（工具栏显示用）
const renderedPages = shallowRef(new Set<number>())
const icons = { ZoomIn, ZoomOut }

// ============================================================================
// 内部非响应式引用
// ============================================================================

let doc: any = null
let observer: IntersectionObserver | null = null
const canvasMap = new Map<number, HTMLCanvasElement>()
const textLayerMap = new Map<number, HTMLDivElement>()
const annotationLayerMap = new Map<number, HTMLDivElement>()
const taskMap = new Map<number, any>()
let loadGen = 0
let prevUrl: string | undefined
let visiblePagesSet = new Set<number>()  // IntersectionObserver 报告的可视页码

// ============================================================================
// 高亮 / 批注状态
// ============================================================================

interface HighlightRect {
  left: number; top: number; width: number; height: number
}

interface PageHighlight {
  id: string
  pageNum: number
  text: string
  rects: HighlightRect[]   // 百分比坐标（0~1），相对于页面容器
  color?: string
}

const highlights = shallowRef<PageHighlight[]>([])

// ── 联动高亮（临时，来自右侧读者点击） ──
const activeLinkHighlight = shallowRef<{ pageNum: number; rect: HighlightRect } | null>(null)
let linkHighlightTimer: ReturnType<typeof setTimeout> | null = null

// ============================================================================
// 悬浮菜单状态（Zotero-style）
// ============================================================================

const showHighlightMenu = ref(false)
const menuPosition = ref({ x: 0, y: 0 })
const pendingHighlight = ref<{ pageNum: number; text: string; rects: HighlightRect[] } | null>(null)
const pendingNoteContent = ref('')
const selectedColorKey = ref('yellow')
const savingHighlight = ref(false)

// ── 公式框选 OCR ──
const formulaMode = ref(false)
const formulaDragPage = ref<number | null>(null)
const formulaDragStart = ref<{ x: number; y: number } | null>(null)
const formulaCropRect = ref<HighlightRect | null>(null)
const showFormulaDialog = ref(false)
const formulaLatex = ref('')
const formulaExtracting = ref(false)
const formulaSaving = ref(false)
const pendingFormulaNote = ref<{ pageNum: number; rect: HighlightRect } | null>(null)
const formulaPreviewUrl = ref('')

// 全局 mousedown 监听 → 点击菜单外部关闭菜单
function onGlobalMouseDown(e: MouseEvent) {
  if (!showHighlightMenu.value) return
  const menuEl = document.querySelector('.pdf-highlight-menu')
  if (menuEl && !menuEl.contains(e.target as Node)) {
    dismissMenu()
  }
}

// ============================================================================
// 渲染窗口配置
// ============================================================================

const VIEWPORT_MARGIN = 300       // IntersectionObserver rootMargin（px），提前预渲染
const WINDOW_PAGES_BEFORE = 2     // 可视区之前保留的已渲染页数
const WINDOW_PAGES_AFTER = 3      // 可视区之后保留的已渲染页数

// ============================================================================
// Watch
// ============================================================================

watch(
  () => props.url,
  async (_newUrl, oldUrl) => {
    await loadPdf()
    if (prevUrl && prevUrl !== _newUrl && prevUrl.startsWith('blob:')) {
      emit('oldUrlCleanup', prevUrl)
    }
    prevUrl = _newUrl
  },
  { immediate: true }
)

watch(() => props.initialPage, async p => {
  if (p && doc) await scrollToPage(p)
})

watch(() => props.highlightText, async () => {
  // 重新渲染当前所有已渲染页面的文本层
  await refreshTextLayers()
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onGlobalMouseDown)
  resizeObs?.disconnect()
  if (resizeFitTimeout) clearTimeout(resizeFitTimeout)
  clearLinkHighlight()
  cancelFormulaCrop()
  destroyObserver()
  cancelAllTasks()
  try { doc?.destroy?.() } catch {}
  if (prevUrl?.startsWith('blob:')) {
    emit('oldUrlCleanup', prevUrl)
  }
})

// 注册全局 mousedown 监听（用于关闭悬浮菜单）
document.addEventListener('mousedown', onGlobalMouseDown)

// ============================================================================
// 生命周期辅助
// ============================================================================

function cancelAllTasks() {
  for (const t of taskMap.values()) {
    try { t?.cancel?.() } catch {}
  }
  taskMap.clear()
}

function destroyObserver() {
  observer?.disconnect()
  observer = null
}

function clearAllCanvases() {
  for (const canvas of canvasMap.values()) {
    canvas.width = 0
    canvas.height = 0
  }
  for (const layer of textLayerMap.values()) {
    layer.innerHTML = ''
  }
  for (const layer of annotationLayerMap.values()) {
    layer.innerHTML = ''
  }
  renderedPages.value = new Set()
}

// ============================================================================
// PDF 加载
// ============================================================================

async function loadPdf() {
  error.value = ''
  cancelAllTasks()
  destroyObserver()
  clearAllCanvases()
  loadGen += 1
  const myGen = loadGen

  if (!props.url) {
    totalPages.value = 0
    return
  }

  pdfLoading.value = true
  try {
    const isBlob = props.url?.startsWith('blob:')
    const task = pdfjsLib.getDocument({
      url: props.url,
      withCredentials: false,
      disableRange: isBlob,
      disableStream: isBlob,
    })
    const newDoc = await task.promise
    if (myGen !== loadGen) {
      try { newDoc.destroy() } catch {}
      return
    }
    try { doc?.destroy?.() } catch {}
    doc = newDoc
    totalPages.value = doc.numPages

    userManualZoom.value = false
    totalPages.value = doc.numPages

    await nextTick()
    await nextTick()

    setupResizeObserver()
    await fitToContainerWidth(true)
    setupObserver()

    await renderPage(1)
    await nextTick()
    await fitToContainerWidth(true)

    // 如果指定了 initialPage，滚动过去
    const target = Math.min(Math.max(props.initialPage || 1, 1), totalPages.value)
    if (target > 1) {
      await nextTick()
      await scrollToPage(target)
    }
  } catch (e: any) {
    if (myGen !== loadGen) return
    error.value = e?.message || 'PDF failed to load.'
  } finally {
    if (myGen === loadGen) pdfLoading.value = false
  }
}

let resizeObs: ResizeObserver | null = null
let resizeFitTimeout: ReturnType<typeof setTimeout> | null = null

function setupResizeObserver() {
  resizeObs?.disconnect()
  if (!containerRef.value) return
  resizeObs = new ResizeObserver(() => {
    if (resizeFitTimeout) clearTimeout(resizeFitTimeout)
    resizeFitTimeout = setTimeout(() => {
      void fitToContainerWidth()
    }, 150)
  })
  resizeObs.observe(containerRef.value)
}

async function fitToContainerWidth(force = false) {
  if (!containerRef.value || !doc) return
  if (userManualZoom.value && !force) return

  await nextTick()

  const containerWidth = containerRef.value.clientWidth
  if (containerWidth < 120) return

  try {
    const page = await doc.getPage(1)
    const baseVp = page.getViewport({ scale: 1 })
    const styles = getComputedStyle(containerRef.value)
    const padX = (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0)
    const horizontalPad = padX + 4
    const targetScale = (containerWidth - horizontalPad) / baseVp.width
    const clamped = Math.min(Math.max(targetScale, 0.5), 3)
    if (Math.abs(clamped - scale.value) > 0.005) {
      await applyZoom(clamped, { preserveManualZoom: true })
      await renderPage(1)
    } else {
      await estimatePageHeight()
    }
  } catch { /* ignore */ }
}

async function estimatePageHeight() {
  if (!doc) return
  try {
    const page = await doc.getPage(1)
    const vp = page.getViewport({ scale: scale.value })
    pageHeightPx.value = Math.floor(vp.height)
    pageWidthPx.value = Math.floor(vp.width)
  } catch { /* 忽略，使用默认骨架高度 */ }
}

// ============================================================================
// IntersectionObserver
// ============================================================================

function setupObserver() {
  destroyObserver()
  if (!containerRef.value) return

  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const pageNum = Number((entry.target as HTMLElement).dataset.page)
        if (!pageNum) continue

        if (entry.isIntersecting) {
          visiblePagesSet.add(pageNum)
        } else {
          visiblePagesSet.delete(pageNum)
        }
      }
      syncRenderWindow()
      updateScrollPage()
    },
    {
      root: containerRef.value,
      rootMargin: `${VIEWPORT_MARGIN}px 0px ${VIEWPORT_MARGIN}px 0px`,
      threshold: 0,
    }
  )

  // 观察所有页骨架
  const wrappers = containerRef.value.querySelectorAll<HTMLElement>('[data-page]')
  for (const el of wrappers) {
    observer.observe(el)
  }
}

function syncRenderWindow() {
  if (visiblePagesSet.size === 0) return

  const sorted = [...visiblePagesSet].sort((a, b) => a - b)
  const first = sorted[0]
  const last = sorted[sorted.length - 1]

  const windowStart = Math.max(1, first - WINDOW_PAGES_BEFORE)
  const windowEnd = Math.min(totalPages.value, last + WINDOW_PAGES_AFTER)

  const current = new Set(renderedPages.value)
  const target = new Set<number>()
  for (let i = windowStart; i <= windowEnd; i++) target.add(i)

  // 销毁离开窗口的页
  for (const p of current) {
    if (!target.has(p)) destroyPage(p)
  }
  // 渲染进入窗口的页
  for (const p of target) {
    if (!current.has(p)) {
      // 不阻塞 observer 回调
      renderPage(p)
    }
  }
}

function updateScrollPage() {
  if (!containerRef.value || visiblePagesSet.size === 0) return
  const sorted = [...visiblePagesSet].sort((a, b) => a - b)
  // 取第一个完全在视口内的页，否则取最接近顶部那一页
  scrollPage.value = sorted[0]
}

// ============================================================================
// 页面渲染 / 销毁
// ============================================================================

async function renderPage(pageNum: number) {
  if (!doc || pageNum < 1 || pageNum > totalPages.value) return

  // 如果已渲染，跳过
  if (renderedPages.value.has(pageNum)) return

  // 标记为已渲染（先占位，避免并发重复渲染）
  markRendered(pageNum, true)

  try {
    // 取消该页之前的渲染任务
    const oldTask = taskMap.get(pageNum)
    try { oldTask?.cancel?.() } catch {}
    taskMap.delete(pageNum)

    const page = await doc.getPage(pageNum)
    const viewport = page.getViewport({ scale: scale.value })

    // 等待下一帧确保 canvas DOM 就绪
    await nextTick()

    const canvas = canvasMap.get(pageNum)
    if (!canvas) {
      // canvas 还没挂载到 DOM（可能骨架 div 刚创建）
      markRendered(pageNum, false)
      return
    }

    const context = canvas.getContext('2d')
    if (!context) {
      markRendered(pageNum, false)
      return
    }

    const outputScale = window.devicePixelRatio || 1
    canvas.width = Math.floor(viewport.width * outputScale)
    canvas.height = Math.floor(viewport.height * outputScale)
    canvas.style.width = `${Math.floor(viewport.width)}px`
    canvas.style.height = `${Math.floor(viewport.height)}px`

    const transform = outputScale !== 1
      ? [outputScale, 0, 0, outputScale, 0, 0]
      : null

    const renderTask = page.render({
      canvasContext: context,
      transform,
      viewport,
    })
    taskMap.set(pageNum, renderTask)
    await renderTask.promise
    taskMap.delete(pageNum)

    await renderTextLayerOnPage(page, viewport, pageNum)
    await renderAnnotationLayer(pageNum)
  } catch (e: any) {
    if (e?.name !== 'RenderingCancelledException') {
      markRendered(pageNum, false)
      throw e
    }
    markRendered(pageNum, false)
  }
}

function destroyPage(pageNum: number) {
  // 取消渲染任务
  const task = taskMap.get(pageNum)
  try { task?.cancel?.() } catch {}
  taskMap.delete(pageNum)

  // 释放 GPU 内存
  const canvas = canvasMap.get(pageNum)
  if (canvas) {
    canvas.width = 0
    canvas.height = 0
  }

  // 清空文本层
  const layer = textLayerMap.get(pageNum)
  if (layer) layer.innerHTML = ''

  // 清空标注层（高亮框会在重新渲染时自动恢复）
  const annLayer = annotationLayerMap.get(pageNum)
  if (annLayer) annLayer.innerHTML = ''

  markRendered(pageNum, false)
}

// ============================================================================
// 文本层渲染（使用官方 TextLayer API + --scale-factor）
// ============================================================================

async function renderTextLayerOnPage(page: any, viewport: any, pageNum: number) {
  const layer = textLayerMap.get(pageNum)
  if (!layer) return

  layer.innerHTML = ''
  // 核心：设置 --scale-factor 确保文字大小 / 位置正确缩放
  layer.style.setProperty('--scale-factor', String(viewport.scale))
  layer.style.width = `${Math.floor(viewport.width)}px`
  layer.style.height = `${Math.floor(viewport.height)}px`

  const textContent = await page.getTextContent()
  if (!textContent) return

  try {
    const textLayer = new pdfjsLib.TextLayer({
      textContentSource: textContent,
      container: layer,
      viewport: viewport,
    })
    await textLayer.render()
  } catch (e: any) {
    if (e?.name !== 'RenderingCancelledException') {
      throw e
    }
  }
}

async function refreshTextLayers() {
  if (!doc) return
  for (const pageNum of renderedPages.value) {
    try {
      const page = await doc.getPage(pageNum)
      const viewport = page.getViewport({ scale: scale.value })
      await renderTextLayerOnPage(page, viewport, pageNum)
      await renderAnnotationLayer(pageNum)
    } catch { /* 单页刷新失败不影响其他页 */ }
  }
}

// ============================================================================
// 标注层（Annotation Layer）—— 渲染百分比坐标的高亮框
// ============================================================================

async function renderAnnotationLayer(pageNum: number) {
  const layer = annotationLayerMap.get(pageNum)
  if (!layer) return
  layer.innerHTML = ''

  const pageHighlights = highlights.value.filter(h => h.pageNum === pageNum)
  for (const hl of pageHighlights) {
    const isPersistedNote = /^\d+$/.test(hl.id)
    for (const rect of hl.rects) {
      const box = document.createElement('div')
      box.className = isPersistedNote ? 'highlight-box highlight-box--linked' : 'highlight-box'
      box.style.left = `${rect.left * 100}%`
      box.style.top = `${rect.top * 100}%`
      box.style.width = `${rect.width * 100}%`
      box.style.height = `${rect.height * 100}%`
      box.style.backgroundColor = hl.color || HIGHLIGHT_COLORS.yellow
      const tone = resolveHighlightTone(hl.color)
      box.style.setProperty('--hl-edge', highlightEdgeColor(HIGHLIGHT_HEX[tone]))
      box.title = isPersistedNote ? '点击查看笔记' : hl.text.slice(0, 100)
      box.dataset.highlightId = hl.id
      if (isPersistedNote) {
        box.dataset.noteId = hl.id
      }

      // 删除按钮（hover 时显示）
      const delBtn = document.createElement('button')
      delBtn.className = 'highlight-delete-btn'
      delBtn.innerHTML = '×'
      delBtn.title = '删除此高亮'
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation()
        deleteHighlight(hl.id)
      })
      box.appendChild(delBtn)

      layer.appendChild(box)
    }
  }

  // ── 联动高亮（临时，来自右侧内容块点击） ──
  const linkHl = activeLinkHighlight.value
  if (linkHl && linkHl.pageNum === pageNum) {
    const { rect } = linkHl
    const box = document.createElement('div')
    box.className = 'link-highlight-box'
    box.style.left = `${rect.left * 100}%`
    box.style.top = `${rect.top * 100}%`
    box.style.width = `${rect.width * 100}%`
    box.style.height = `${rect.height * 100}%`
    layer.appendChild(box)
  }
}

async function refreshAnnotationLayers() {
  for (const pageNum of renderedPages.value) {
    await renderAnnotationLayer(pageNum)
  }
}

function findPageInnerFromEvent(target: EventTarget | null): { pageNum: number; pageInner: HTMLElement } | null {
  let pageEl = target as HTMLElement | null
  while (pageEl && !pageEl.dataset.page) {
    pageEl = pageEl.parentElement
  }
  if (!pageEl?.dataset.page) return null
  const pageInner = pageEl.querySelector('.page-inner') as HTMLElement | null
  if (!pageInner) return null
  return { pageNum: Number(pageEl.dataset.page), pageInner }
}

function pointerToNormalized(pageInner: HTMLElement, clientX: number, clientY: number): HighlightRect | null {
  const containerRect = pageInner.getBoundingClientRect()
  if (containerRect.width <= 0 || containerRect.height <= 0) return null
  const x = (clientX - containerRect.left) / containerRect.width
  const y = (clientY - containerRect.top) / containerRect.height
  return {
    left: Math.max(0, Math.min(1, x)),
    top: Math.max(0, Math.min(1, y)),
    width: 0,
    height: 0,
  }
}

function normalizeDragRect(start: HighlightRect, end: HighlightRect): HighlightRect | null {
  const left = Math.min(start.left, end.left)
  const top = Math.min(start.top, end.top)
  const right = Math.max(start.left, end.left)
  const bottom = Math.max(start.top, end.top)
  const width = right - left
  const height = bottom - top
  if (width <= 0.005 || height <= 0.005) return null
  return {
    left: Math.max(0, Math.min(1, left)),
    top: Math.max(0, Math.min(1, top)),
    width: Math.max(0, Math.min(1 - left, width)),
    height: Math.max(0, Math.min(1 - top, height)),
  }
}

function toggleFormulaMode() {
  formulaMode.value = !formulaMode.value
  if (!formulaMode.value) cancelFormulaCrop()
  dismissMenu()
  window.getSelection()?.removeAllRanges()
  emit('formulaModeChange', formulaMode.value)
}

function cancelFormulaCrop() {
  formulaDragPage.value = null
  formulaDragStart.value = null
  formulaCropRect.value = null
  showFormulaDialog.value = false
  formulaLatex.value = ''
  pendingFormulaNote.value = null
  if (formulaPreviewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(formulaPreviewUrl.value)
  }
  formulaPreviewUrl.value = ''
}

function onFormulaMouseDown(e: MouseEvent) {
  if (!formulaMode.value || e.button !== 0) return
  const found = findPageInnerFromEvent(e.target)
  if (!found) return
  e.preventDefault()
  e.stopPropagation()
  const start = pointerToNormalized(found.pageInner, e.clientX, e.clientY)
  if (!start) return
  formulaDragPage.value = found.pageNum
  formulaDragStart.value = { x: start.left, y: start.top }
  formulaCropRect.value = { left: start.left, top: start.top, width: 0, height: 0 }
}

function onFormulaMouseMove(e: MouseEvent) {
  if (!formulaMode.value || !formulaDragStart.value || formulaDragPage.value == null) return
  const pageInner = containerRef.value?.querySelector<HTMLElement>(
    `[data-page="${formulaDragPage.value}"] .page-inner`,
  )
  if (!pageInner) return
  const end = pointerToNormalized(pageInner, e.clientX, e.clientY)
  if (!end) return
  const startRect: HighlightRect = {
    left: formulaDragStart.value.x,
    top: formulaDragStart.value.y,
    width: 0,
    height: 0,
  }
  formulaCropRect.value = normalizeDragRect(startRect, end) || formulaCropRect.value
}

async function onFormulaMouseUp(e: MouseEvent) {
  if (!formulaMode.value || !formulaDragStart.value || formulaDragPage.value == null) return
  const pageNum = formulaDragPage.value
  const rect = formulaCropRect.value
  formulaDragStart.value = null
  if (!rect || rect.width <= 0.01 || rect.height <= 0.01) {
    formulaCropRect.value = null
    return
  }
  e.preventDefault()
  pendingFormulaNote.value = { pageNum, rect }
  await openFormulaDialog(pageNum, rect)
}

function cropCanvasToBase64(pageNum: number, rect: HighlightRect): string | null {
  const canvas = canvasMap.get(pageNum)
  if (!canvas || canvas.width <= 0 || canvas.height <= 0) return null
  const sx = Math.max(0, Math.floor(rect.left * canvas.width))
  const sy = Math.max(0, Math.floor(rect.top * canvas.height))
  const sw = Math.max(1, Math.floor(rect.width * canvas.width))
  const sh = Math.max(1, Math.floor(rect.height * canvas.height))
  const off = document.createElement('canvas')
  off.width = sw
  off.height = sh
  const ctx = off.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(canvas, sx, sy, sw, sh, 0, 0, sw, sh)
  return off.toDataURL('image/png', 1.0)
}

async function openFormulaDialog(pageNum: number, rect: HighlightRect) {
  showFormulaDialog.value = true
  formulaLatex.value = ''
  formulaExtracting.value = true
  if (formulaPreviewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(formulaPreviewUrl.value)
  }
  formulaPreviewUrl.value = cropCanvasToBase64(pageNum, rect) || ''
  try {
    if (!formulaPreviewUrl.value) {
      throw new Error('当前页尚未渲染完成，请稍后再试')
    }
    const result = await formulaApi.extract(formulaPreviewUrl.value)
    formulaLatex.value = normalizeOcrLatex(result.latex || '')
  } catch (err: any) {
    const detail = err?.response?.data?.detail || err?.message || '公式识别失败'
    ElMessage.error(typeof detail === 'string' ? detail : '公式识别失败')
  } finally {
    formulaExtracting.value = false
  }
}

async function retryFormulaExtract() {
  const pending = pendingFormulaNote.value
  if (!pending) return
  await openFormulaDialog(pending.pageNum, pending.rect)
}

async function saveFormulaNote() {
  const pending = pendingFormulaNote.value
  const latex = formulaLatex.value.trim()
  if (!pending || !latex) {
    ElMessage.warning('请先识别或填写 LaTeX 内容')
    return
  }
  if (!props.saveHighlightHandler) {
    ElMessage.warning('当前阅读器未启用笔记保存')
    return
  }
  formulaSaving.value = true
  try {
    const noteContent = latex.startsWith('$$') ? latex : `$$\n${latex}\n$$`
    await props.saveHighlightHandler({
      pageNum: pending.pageNum,
      text: '[公式]',
      rects: [pending.rect],
      colorKey: 'blue',
      noteContent,
    })
    emit('highlightSaved')
    ElMessage.success('公式笔记已保存')
    cancelFormulaCrop()
    formulaMode.value = false
    emit('formulaModeChange', false)
  } finally {
    formulaSaving.value = false
  }
}

// ============================================================================
// 文本划词选择 → 提取百分比坐标 → 暂存 pending → 弹出菜单
// ============================================================================

function handleTextSelection(evt: MouseEvent) {
  if (formulaMode.value) return
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) {
    // 普通点击（无选中文字）→ 不关闭菜单（让全局 mousedown 处理）
    return
  }
  if (!selection.toString().trim()) return

  // 找到选择所在的页面容器
  let pageEl: HTMLElement | null = evt.target as HTMLElement
  while (pageEl && !pageEl.dataset.page) {
    pageEl = pageEl.parentElement
  }
  if (!pageEl?.dataset.page) return

  const pageNum = Number(pageEl.dataset.page)
  const pageInner = pageEl.querySelector('.page-inner') as HTMLElement | null
  if (!pageInner) return

  const containerRect = pageInner.getBoundingClientRect()
  if (containerRect.width === 0 || containerRect.height === 0) return

  const range = selection.getRangeAt(0)
  const clientRects = range.getClientRects()
  if (clientRects.length === 0) return

  const text = selection.toString().trim()

  // 合并碎片化 DOMRect，再转为百分比坐标（缩放无关）
  const rects: HighlightRect[] = mergeSelectionRects(clientRects, containerRect)
  if (rects.length === 0) return

  // 去重：已有完全相同文字+页码的高亮则跳过
  const existing = highlights.value.find(
    h => h.pageNum === pageNum && h.text === text
  )
  if (existing) return

  // 计算悬浮菜单位置：选区上方居中
  const selectionRect = range.getBoundingClientRect()
  menuPosition.value = {
    x: selectionRect.left + selectionRect.width / 2,
    y: selectionRect.top - 8,  // 选区顶部略上方
  }

  pendingHighlight.value = { pageNum, text, rects }
  pendingNoteContent.value = ''
  selectedColorKey.value = 'yellow'
  showHighlightMenu.value = true
}

function onHighlightLayerClick(e: MouseEvent) {
  if (formulaMode.value) return
  const target = e.target as HTMLElement
  if (target.closest('.highlight-delete-btn')) return

  const box = target.closest('.highlight-box') as HTMLElement | null
  if (!box) return

  const noteId = box.dataset.noteId
  if (!noteId || !/^\d+$/.test(noteId)) return

  e.preventDefault()
  e.stopPropagation()
  emit('highlightClick', Number(noteId))
}

// ============================================================================
// 悬浮菜单操作
// ============================================================================

const HIGHLIGHT_COLORS: Record<string, string> = {
  yellow: 'rgba(255, 210, 77, 0.2)',
  green:  'rgba(60, 210, 120, 0.2)',
  red:    'rgba(255, 80, 80, 0.2)',
  blue:   'rgba(80, 150, 255, 0.2)',
}

const HIGHLIGHT_HEX: Record<string, string> = {
  yellow: '#FFD24D',
  green: '#3CD278',
  red: '#FF5050',
  blue: '#5096FF',
}

function hexToRgba(hex: string, alpha = 0.2): string {
  const normalized = hex.replace('#', '')
  if (normalized.length !== 6) return HIGHLIGHT_COLORS.yellow
  const r = parseInt(normalized.slice(0, 2), 16)
  const g = parseInt(normalized.slice(2, 4), 16)
  const b = parseInt(normalized.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function highlightEdgeColor(hex: string): string {
  return hexToRgba(hex.replace('#', '').length === 6 ? hex : '#FFD24D', 0.75)
}

function resolveHighlightTone(color?: string): keyof typeof HIGHLIGHT_HEX {
  if (!color) return 'yellow'
  for (const [key, value] of Object.entries(HIGHLIGHT_COLORS)) {
    if (value === color) return key as keyof typeof HIGHLIGHT_HEX
  }
  return 'yellow'
}

async function confirmHighlight(color?: string) {
  if (!pendingHighlight.value || savingHighlight.value) return

  const colorKey = color || selectedColorKey.value || 'yellow'
  selectedColorKey.value = colorKey
  const displayColor = HIGHLIGHT_COLORS[colorKey] || HIGHLIGHT_COLORS.yellow

  if (props.saveHighlightHandler) {
    savingHighlight.value = true
    try {
      const saved = await props.saveHighlightHandler({
        pageNum: pendingHighlight.value.pageNum,
        text: pendingHighlight.value.text,
        rects: pendingHighlight.value.rects,
        colorKey,
        noteContent: pendingNoteContent.value.trim() || undefined,
      })
      if (saved) {
        const newHighlight: PageHighlight = {
          id: String(saved.id),
          pageNum: pendingHighlight.value.pageNum,
          text: pendingHighlight.value.text,
          rects: pendingHighlight.value.rects,
          color: saved.color || displayColor,
        }
        highlights.value = [...highlights.value, newHighlight]
        await renderAnnotationLayer(newHighlight.pageNum)
        emit('highlightSaved')
      }
    } finally {
      savingHighlight.value = false
    }
    dismissMenu()
    return
  }

  const newHighlight: PageHighlight = {
    id: `hl-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    pageNum: pendingHighlight.value.pageNum,
    text: pendingHighlight.value.text,
    rects: pendingHighlight.value.rects,
    color: displayColor,
  }

  highlights.value = [...highlights.value, newHighlight]
  await renderAnnotationLayer(newHighlight.pageNum)
  dismissMenu()
}

function dismissMenu() {
  showHighlightMenu.value = false
  pendingHighlight.value = null
  pendingNoteContent.value = ''
  window.getSelection()?.removeAllRanges()
}

function copyHighlightText() {
  if (!pendingHighlight.value) return
  navigator.clipboard?.writeText(pendingHighlight.value.text).catch(() => {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = pendingHighlight.value!.text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  })
  dismissMenu()
}

async function deleteHighlight(id: string) {
  const item = highlights.value.find(h => h.id === id)
  if (!item) return
  if (props.deleteHighlightHandler && /^\d+$/.test(id)) {
    try {
      await props.deleteHighlightHandler(Number(id))
      emit('highlightSaved')
    } catch {
      return
    }
  }
  highlights.value = highlights.value.filter(h => h.id !== id)
  await renderAnnotationLayer(item.pageNum)
}

function setPersistedHighlights(items: Array<{
  id: number
  pageNum: number
  text: string
  rects: HighlightRect[]
  color?: string
}>) {
  highlights.value = items.map(item => ({
    id: String(item.id),
    pageNum: item.pageNum,
    text: item.text,
    rects: item.rects,
    color: item.color || HIGHLIGHT_COLORS.yellow,
  }))
  refreshAnnotationLayers()
}

function clearPersistedHighlights() {
  highlights.value = []
  refreshAnnotationLayers()
}

// ============================================================================
// Set 操作（触发 shallowRef 响应）
// ============================================================================

function markRendered(pageNum: number, rendered: boolean) {
  const next = new Set(renderedPages.value)
  if (rendered) {
    next.add(pageNum)
  } else {
    next.delete(pageNum)
  }
  renderedPages.value = next
}

// ============================================================================
// 缩放
// ============================================================================

async function applyZoom(newScale: number, options?: { preserveManualZoom?: boolean }) {
  scale.value = newScale
  if (!options?.preserveManualZoom) {
    userManualZoom.value = true
  }
  if (!doc) return

  // 重新计算骨架高度
  await estimatePageHeight()

  // 清空所有已渲染内容
  cancelAllTasks()
  clearAllCanvases()

  // 重新观察并渲染
  await nextTick()
  setupObserver()
  // IntersectionObserver 会自动触发可见页渲染
}

async function zoomIn() {
  await applyZoom(Math.min(scale.value + 0.15, 2.5))
}

async function zoomOut() {
  await applyZoom(Math.max(scale.value - 0.15, 0.7))
}

let zoomTimeout: ReturnType<typeof setTimeout> | null = null

function handleWheelZoom(e: WheelEvent) {
  if (!e.ctrlKey && !e.metaKey) return
  e.preventDefault()
  if (zoomTimeout) return
  zoomTimeout = setTimeout(() => { zoomTimeout = null }, 150)
  if (e.deltaY < 0) {
    void zoomIn()
  } else {
    void zoomOut()
  }
}

async function scrollToPage(page: number) {
  if (!containerRef.value) return
  const el = containerRef.value.querySelector<HTMLElement>(`[data-page="${page}"]`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  scrollPage.value = page
}

function normalizeSearchText(text: string): string {
  return text.replace(/\s+/g, '').toLowerCase()
}

function pickSearchNeedles(rawText: string): string[] {
  const content = rawText.replace(/\s+/g, ' ').trim()
  if (!content) return []

  const needles = new Set<string>()
  needles.add(content.slice(0, 160))
  needles.add(content.slice(0, 80))
  needles.add(content.slice(0, 48))

  const sentences = content.split(/(?<=[。！？；;!?])\s*/).map(s => s.trim()).filter(s => s.length >= 16)
  for (const sent of sentences.slice(0, 3)) {
    needles.add(sent.slice(0, 120))
  }

  return [...needles].filter(n => n.length >= 8)
}

async function highlightTextOnPage(pageNum: number, rawText: string): Promise<boolean> {
  const layer = textLayerMap.get(pageNum)
  if (!layer || !rawText.trim()) return false

  const spans = Array.from(layer.querySelectorAll('span')) as HTMLElement[]
  if (!spans.length) return false

  let full = ''
  const map: Array<{ span: HTMLElement; start: number; end: number }> = []
  for (const span of spans) {
    const piece = span.textContent || ''
    if (!piece) continue
    const start = full.length
    full += piece
    map.push({ span, start, end: full.length })
  }

  const normalizedFull = normalizeSearchText(full)
  let matchStart = -1
  let matchLen = 0
  for (const needle of pickSearchNeedles(rawText)) {
    const normalizedNeedle = normalizeSearchText(needle)
    const idx = normalizedFull.indexOf(normalizedNeedle)
    if (idx >= 0) {
      matchStart = idx
      matchLen = normalizedNeedle.length
      break
    }
  }
  if (matchStart < 0) return false

  const matchEnd = matchStart + matchLen
  const matchedSpans = map.filter(entry => entry.end > matchStart && entry.start < matchEnd)
  if (!matchedSpans.length) return false

  const pageEl = containerRef.value?.querySelector<HTMLElement>(`[data-page="${pageNum}"]`)
  const pageRect = pageEl?.getBoundingClientRect()
  if (!pageRect?.width || !pageRect?.height) return false

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const { span } of matchedSpans) {
    const rect = span.getBoundingClientRect()
    minX = Math.min(minX, rect.left)
    minY = Math.min(minY, rect.top)
    maxX = Math.max(maxX, rect.right)
    maxY = Math.max(maxY, rect.bottom)
  }

  const clamp = (v: number) => Math.max(0, Math.min(1, v))
  const left = clamp((minX - pageRect.left) / pageRect.width)
  const top = clamp((minY - pageRect.top) / pageRect.height)
  const width = clamp(Math.max(0.01, (maxX - minX) / pageRect.width))
  const height = clamp(Math.max(0.008, (maxY - minY) / pageRect.height))

  clearLinkHighlight()
  activeLinkHighlight.value = {
    pageNum,
    rect: { left, top, width, height },
  }
  await renderAnnotationLayer(pageNum)
  linkHighlightTimer = setTimeout(() => {
    clearLinkHighlight()
  }, 3000)
  return true
}

async function jumpTo(page: number, text?: string): Promise<boolean> {
  if (!doc) return false
  const target = Math.min(Math.max(Number(page) || 1, 1), totalPages.value || 1)
  await renderPage(target)
  await scrollToPage(target)

  if (!text?.trim()) return false

  for (let attempt = 0; attempt < 6; attempt += 1) {
    await nextTick()
    if (await highlightTextOnPage(target, text)) return true
    await new Promise(resolve => setTimeout(resolve, 180))
  }
  return false
}

// ── 联动高亮：接收物理坐标 bbox [x0, y0, x1, y1]，翻页并绘制临时高亮 ──
async function highlightAndScrollTo(pageNum: number, bbox: [number, number, number, number]) {
  if (!doc || !bbox || bbox.length !== 4) return

  // 清除上一次的联动高亮
  clearLinkHighlight()

  const targetPage = Math.min(Math.max(pageNum, 1), totalPages.value || 1)

  // 1. 获取目标页 scale=1.0 时的 viewport（PDF 原始坐标参考）
  const page = await doc.getPage(targetPage)
  const vp = page.getViewport({ scale: 1.0 })
  const vpW = vp.width
  const vpH = vp.height
  if (vpW <= 0 || vpH <= 0) return

  // 2. 坐标转换：支持 0~1 比例坐标（MinerU）或 PDF 绝对坐标
  const [x0, y0, x1, y1] = bbox
  const isNormalized = [x0, y0, x1, y1].every(v => v >= 0 && v <= 1)
  let left: number
  let top: number
  let width: number
  let height: number

  if (isNormalized) {
    left = x0
    top = y0
    width = x1 - x0
    height = y1 - y0
  } else {
    left = x0 / vpW
    width = (x1 - x0) / vpW
    top = 1 - (y1 / vpH)
    height = (y1 - y0) / vpH
  }

  // 限制坐标在有效范围 [0, 1]
  const clamp = (v: number) => Math.max(0, Math.min(1, v))
  const rect: HighlightRect = {
    left: clamp(left),
    top: clamp(top),
    width: clamp(width),
    height: clamp(height),
  }

  // 3. 赋值联动高亮
  activeLinkHighlight.value = { pageNum: targetPage, rect }

  // 4. 滚动到目标页
  await scrollToPage(targetPage)

  // 5. 等待渲染完成后触发 annotationLayer 更新
  await nextTick()

  // 6. 渲染高亮层
  await renderAnnotationLayer(targetPage)

  // 7. 3 秒后自动清除临时高亮
  linkHighlightTimer = setTimeout(() => {
    clearLinkHighlight()
  }, 3000)
}

function clearLinkHighlight() {
  if (linkHighlightTimer) {
    clearTimeout(linkHighlightTimer)
    linkHighlightTimer = null
  }
  if (activeLinkHighlight.value) {
    const prevPage = activeLinkHighlight.value.pageNum
    activeLinkHighlight.value = null
    renderAnnotationLayer(prevPage)
  }
}

// ============================================================================
// Ref 回调（Vue 动态 ref）
// ============================================================================

function setCanvasRef(pageNum: number, el: any) {
  if (el) {
    canvasMap.set(pageNum, el as HTMLCanvasElement)
  } else {
    canvasMap.delete(pageNum)
  }
}

function setTextLayerRef(pageNum: number, el: any) {
  if (el) {
    textLayerMap.set(pageNum, el as HTMLDivElement)
  } else {
    textLayerMap.delete(pageNum)
  }
}

function setAnnotationLayerRef(pageNum: number, el: any) {
  if (el) {
    annotationLayerMap.set(pageNum, el as HTMLDivElement)
  } else {
    annotationLayerMap.delete(pageNum)
  }
}

async function whenReady(timeoutMs = 15000): Promise<boolean> {
  const start = Date.now()
  while (!doc && Date.now() - start < timeoutMs) {
    await new Promise(resolve => setTimeout(resolve, 80))
  }
  return !!doc
}

defineExpose({ jumpTo, highlightAndScrollTo, whenReady, setPersistedHighlights, clearPersistedHighlights, hexToRgba, toggleFormulaMode, formulaMode, fitToContainer: fitToContainerWidth })
</script>

<template>
  <div class="pdf-reader">
    <!-- 错误 -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
    />

    <!-- 空状态 -->
    <div v-else-if="!url" class="empty">
      Select a paper to render the original PDF here.
    </div>

    <!-- ================================================================ -->
    <!-- 连续滚动容器：工具栏 + 骨架屏 + 按需渲染 Canvas -->
    <!-- ================================================================ -->
    <div
      v-else
      ref="containerRef"
      class="scroll-container slim-scroll"
      :class="{ 'formula-mode': formulaMode }"
      v-loading="pdfLoading"
      @wheel="handleWheelZoom"
      @mouseup="(e) => { onFormulaMouseUp(e); handleTextSelection(e) }"
      @mousedown="onFormulaMouseDown"
      @mousemove="onFormulaMouseMove"
      @click="onHighlightLayerClick"
    >
      <div class="toolbar">
        <div>
          <el-button size="small" @click="zoomOut"><el-icon><ZoomOut /></el-icon></el-button>
          <el-button size="small" @click="zoomIn"><el-icon><ZoomIn /></el-icon></el-button>
        </div>
        <div class="pager">
          <span>Page</span>
          <el-input-number
            v-model="scrollPage"
            :min="1"
            :max="totalPages || 1"
            size="small"
            @change="(v: number) => scrollToPage(v)"
          />
          <span>/ {{ totalPages || '-' }}</span>
        </div>
        <div>
          <el-button
            v-if="saveHighlightHandler && showFormulaButton"
            size="small"
            class="formula-toolbar-btn"
            :type="formulaMode ? 'primary' : 'default'"
            @click="toggleFormulaMode"
          >
            {{ formulaMode ? '退出框选' : '框选公式' }}
          </el-button>
          <span class="scale-badge">{{ Math.round(scale * 100) }}%</span>
        </div>
      </div>

      <div
        v-for="p in totalPages"
        :key="p"
        :data-page="p"
        class="page-wrapper"
        :style="{ minHeight: pageHeightPx + 'px' }"
      >
        <div class="page-inner" :style="{ width: pageWidthPx + 'px', minHeight: pageHeightPx + 'px' }">
          <canvas
            :ref="(el: any) => setCanvasRef(p, el)"
            class="page-canvas"
          />
          <div
            :ref="(el: any) => setTextLayerRef(p, el)"
            class="textLayer"
          />
          <div
            :ref="(el: any) => setAnnotationLayerRef(p, el)"
            class="annotationLayer"
          />
          <div
            v-if="formulaMode && formulaDragPage === p && formulaCropRect"
            class="formula-crop-box"
            :style="{
              left: `${formulaCropRect.left * 100}%`,
              top: `${formulaCropRect.top * 100}%`,
              width: `${formulaCropRect.width * 100}%`,
              height: `${formulaCropRect.height * 100}%`,
            }"
          />
          <!-- 未渲染时的骨架 loading -->
          <div
            v-if="!renderedPages.has(p)"
            class="page-skeleton"
          >
            <div class="skeleton-pulse" />
            <span class="skeleton-label">Page {{ p }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ================================================================ -->
  <!-- 悬浮菜单（Teleport 到 body，避免被 overflow 裁切） -->
  <!-- ================================================================ -->
  <Teleport to="body">
    <div
      v-if="showHighlightMenu"
      class="pdf-highlight-menu"
      :style="{
        left: `${menuPosition.x}px`,
        top: `${menuPosition.y}px`,
        transform: 'translate(-50%, calc(-100% - 8px))',
      }"
      @mousedown.stop
    >
      <div class="menu-row">
        <button
          v-for="(_, color) in HIGHLIGHT_COLORS"
          :key="color"
          class="color-btn"
          :class="[color, { active: selectedColorKey === color }]"
          :title="color"
          @click.stop="selectedColorKey = color"
        ></button>
        <div class="menu-divider" />
        <button class="action-btn" @click.stop="copyHighlightText" title="复制到剪贴板">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        </button>
      </div>
      <textarea
        v-model="pendingNoteContent"
        class="menu-note-input"
        rows="2"
        placeholder="添加批注（可选）"
        @mousedown.stop
      />
      <button
        class="menu-save-btn"
        :disabled="savingHighlight"
        @click.stop="confirmHighlight(selectedColorKey)"
      >
        {{ savingHighlight ? '保存中...' : '保存高亮' }}
      </button>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="showFormulaDialog" class="formula-dialog-overlay" @click.self="cancelFormulaCrop">
      <div class="formula-dialog" @click.stop>
        <header class="formula-dialog-head">
          <h3>公式识别结果</h3>
          <button type="button" class="formula-dialog-close" @click="cancelFormulaCrop">×</button>
        </header>
        <div class="formula-dialog-body">
          <div v-if="formulaPreviewUrl" class="formula-preview">
            <img :src="formulaPreviewUrl" alt="框选区域预览" />
          </div>
          <p v-if="formulaExtracting" class="formula-status">正在识别公式…</p>
          <textarea
            v-model="formulaLatex"
            class="formula-latex-input"
            rows="6"
            placeholder="LaTeX 源码将显示在这里，可手动修正"
          />
        </div>
        <footer class="formula-dialog-actions">
          <el-button @click="cancelFormulaCrop">取消</el-button>
          <el-button :loading="formulaExtracting" @click="retryFormulaExtract">重新识别</el-button>
          <el-button type="primary" :loading="formulaSaving" @click="saveFormulaNote">保存为笔记</el-button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ===================================================================
   外层
   =================================================================== */
.pdf-reader {
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
}

.toolbar {
  position: sticky;
  top: 8px;
  z-index: 50;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  width: fit-content;
  max-width: calc(100% - 12px);
  margin: 0 auto 8px;
  padding: 5px 12px;
  border-radius: 100px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.08);
  flex-shrink: 0;
}

.pager {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.scale-badge {
  color: var(--text-secondary);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.formula-toolbar-btn {
  margin-right: 8px;
  font-weight: 600;
}

/* ===================================================================
   滚动容器
   =================================================================== */
.scroll-container {
  flex: 1;
  overflow-y: auto;
  border-radius: 0;
  background: #525659;
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.scroll-container.formula-mode {
  cursor: crosshair;
}

.formula-crop-box {
  position: absolute;
  border: 1px solid rgba(37, 99, 235, 0.5);
  background: rgba(37, 99, 235, 0.08);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.5),
    inset 0 0 12px rgba(37, 99, 235, 0.15);
  pointer-events: none;
  z-index: 6;
  box-sizing: border-box;
}

/* ===================================================================
   每页骨架
   =================================================================== */
.page-wrapper {
  width: 100%;
  max-width: 100%;
  margin: 0 auto 20px;
  display: flex;
  justify-content: center;
}

.page-inner {
  position: relative;       /* 核心！Canvas / TextLayer / AnnotationLayer 的定位基准 */
  margin: 0 auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, .35);
}

/* Canvas —— absolute 覆盖整个 page-inner */
.page-canvas {
  display: block;
  background: #fff;
}

/* ===================================================================
   文本层 —— 使用 pdfjs-dist 官方 class 名 textLayer
   样式由 pdf_viewer.css 提供；这里仅做增强 / 覆盖
   =================================================================== */

/* 确保文本层精确覆盖 canvas（官方 CSS 已设 absolute，这里加固） */
.textLayer {
  z-index: 2;
  /* 开发调试时可临时改为 opacity: 0.4 观察对齐效果 */
}

/* ===================================================================
   标注层 —— 渲染从数据库中读取的百分比坐标高亮框
   =================================================================== */
.annotationLayer {
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;     /* 不阻挡下方 textLayer 的文字选中 */
  overflow: hidden;
}

.annotationLayer :deep(.highlight-box) {
  position: absolute;
  border-radius: 2px;
  pointer-events: auto;
  transition: all .15s ease;
  overflow: visible;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  mix-blend-mode: multiply;
  box-shadow:
    inset 0 2px 0 var(--hl-edge, rgba(255, 210, 77, 0.75)),
    inset 0 -2px 0 var(--hl-edge, rgba(255, 210, 77, 0.75));
}

.annotationLayer :deep(.highlight-box--linked) {
  cursor: pointer;
}

.annotationLayer :deep(.highlight-box:hover) {
  filter: brightness(1.2);
}

.annotationLayer :deep(.highlight-box--linked:hover) {
  filter: brightness(1.25);
  outline: 1px solid rgba(255, 255, 255, .35);
}

/* 高亮删除按钮（hover 时显示） */
.annotationLayer :deep(.highlight-delete-btn) {
  position: absolute;
  top: -10px;
  right: -10px;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid rgba(255,255,255,.25);
  border-radius: 50%;
  background: rgba(30, 30, 30, .85);
  color: #fff;
  font-size: 13px;
  line-height: 20px;
  text-align: center;
  cursor: pointer;
  opacity: 0;
  transform: scale(.8);
  transition: opacity .15s ease, transform .15s ease;
  z-index: 10;
}

.annotationLayer :deep(.highlight-box:hover .highlight-delete-btn) {
  opacity: 1;
  transform: scale(1);
}

.annotationLayer :deep(.highlight-delete-btn:hover) {
  background: #e53935;
  border-color: #e53935;
}

/* ── 联动高亮框（临时，呼吸闪烁动画） ── */
.annotationLayer :deep(.link-highlight-box) {
  position: absolute;
  border-radius: 3px;
  pointer-events: none;
  background: rgba(37, 99, 235, 0.25);
  border: 2px solid rgba(37, 99, 235, 0.7);
  animation: targetFlash 1.2s ease-in-out 3;
  z-index: 5;
}

@keyframes targetFlash {
  0%   { background: rgba(37, 99, 235, 0.45); border-color: rgba(37, 99, 235, 0.9); }
  50%  { background: rgba(37, 99, 235, 0.10); border-color: rgba(37, 99, 235, 0.3); }
  100% { background: rgba(37, 99, 235, 0.45); border-color: rgba(37, 99, 235, 0.9); }
}

/* ===================================================================
   骨架 Loading（未渲染时显示）
   =================================================================== */
.page-skeleton {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  background: rgba(255, 255, 255, .03);
  border-radius: 4px;
}

.skeleton-pulse {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(
    135deg,
    rgba(102, 231, 255, .18),
    rgba(138, 124, 255, .12)
  );
  animation: skPulse 1.5s ease-in-out infinite;
}

@keyframes skPulse {
  0%, 100% { opacity: .3; transform: scale(.88); }
  50%      { opacity: .9; transform: scale(1.06); }
}

.skeleton-label {
  color: var(--muted);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

/* ===================================================================
   空状态
   =================================================================== */
.empty {
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 16px;
}

/* ===================================================================
   悬浮菜单（Zotero-style，Teleport 到 body）
   ⚠️ 这里不用 scoped，因为 Teleport 到 body 不在组件范围内
   =================================================================== */
</style>

<style>
.pdf-highlight-menu {
  position: fixed;
  z-index: 99999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  min-width: 240px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  user-select: none;
  animation: menuIn .18s ease-out;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
}

.pdf-highlight-menu .menu-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

@keyframes menuIn {
  from { opacity: 0; transform: translate(-50%, -100%) scale(.92); }
  to   { opacity: 1; transform: translate(-50%, -100%) scale(1); }
}

.pdf-highlight-menu .color-btn {
  width: 22px;
  height: 22px;
  border: 2px solid transparent;
  border-radius: 50%;
  cursor: pointer;
  transition: border-color .15s ease, transform .15s ease, box-shadow .15s ease;
  padding: 0;
  outline: none;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06);
}

.pdf-highlight-menu .color-btn.yellow { background: #ffd24d; }
.pdf-highlight-menu .color-btn.green  { background: #3cd278; }
.pdf-highlight-menu .color-btn.red    { background: #ff5050; }
.pdf-highlight-menu .color-btn.blue   { background: #5096ff; }

.pdf-highlight-menu .color-btn:hover {
  transform: scale(1.1);
}

.pdf-highlight-menu .color-btn.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
  transform: scale(1.1);
}

.pdf-highlight-menu .menu-note-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-canvas);
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.5;
  padding: 8px 10px;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.pdf-highlight-menu .menu-note-input:focus {
  border-color: rgba(37, 99, 235, 0.45);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.pdf-highlight-menu .menu-note-input::placeholder {
  color: var(--text-tertiary);
}

.pdf-highlight-menu .menu-save-btn {
  border: none;
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
  box-shadow: var(--shadow-sm);
}

.pdf-highlight-menu .menu-save-btn:hover:not(:disabled) {
  background: var(--el-color-primary-hover);
}

.pdf-highlight-menu .menu-save-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.pdf-highlight-menu .menu-divider {
  width: 1px;
  height: 20px;
  background: var(--border-light);
  margin: 0 4px;
}

.pdf-highlight-menu .action-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background .15s ease, color .15s ease, border-color .15s ease;
}

.pdf-highlight-menu .action-btn:hover {
  background: var(--el-color-primary-light);
  border-color: rgba(37, 99, 235, 0.25);
  color: var(--el-color-primary);
}

.formula-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 100000;
  background: rgba(15, 23, 42, 0.45);
  display: grid;
  place-items: center;
  padding: 24px;
}

.formula-dialog {
  width: min(560px, 92vw);
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.25);
  overflow: hidden;
}

.formula-dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #E2E8F0;
}

.formula-dialog-head h3 {
  margin: 0;
  font-size: 16px;
  color: #0F172A;
}

.formula-dialog-close {
  border: none;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  color: #64748B;
}

.formula-dialog-body {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.formula-preview {
  border: 1px solid #E2E8F0;
  border-radius: 10px;
  padding: 10px;
  background: #F8FAFC;
  text-align: center;
}

.formula-preview img {
  max-width: 100%;
  max-height: 160px;
}

.formula-status {
  margin: 0;
  font-size: 13px;
  color: #64748B;
}

.formula-latex-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #CBD5E1;
  border-radius: 10px;
  padding: 12px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
}

.formula-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px 18px;
  border-top: 1px solid #E2E8F0;
}
</style>
