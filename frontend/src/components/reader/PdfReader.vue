<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'
import 'pdfjs-dist/web/pdf_viewer.css'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).href

// ============================================================================
// Props / Emits / Expose（保持与 WorkbenchView 兼容）
// ============================================================================

const props = defineProps<{ url?: string; initialPage?: number; highlightText?: string }>()
const emit = defineEmits<{ (e: 'oldUrlCleanup', url: string): void }>()

// ============================================================================
// 响应式状态
// ============================================================================

const containerRef = ref<HTMLElement | null>(null)
const pdfLoading = ref(false)
const error = ref('')
const totalPages = ref(0)
const scale = ref(1.15)
const pageHeightPx = ref(800)           // 骨架屏高度（首页渲染后更新）
const pageWidthPx = ref(566)            // 骨架屏宽度（A4 比例 ≈ height / 1.414）
const scrollPage = ref(1)               // 当前视口最可见的页码（工具栏显示用）
const renderedPages = shallowRef(new Set<number>())

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
  clearLinkHighlight()
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

    // 获取首页尺寸，用于骨架屏高度
    await estimatePageHeight()

    // 初始化 IntersectionObserver（需要 DOM 更新后）
    await nextTick()
    setupObserver()

    // 立即渲染首屏（第一页）
    await renderPage(1)

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

    canvas.width = Math.floor(viewport.width)
    canvas.height = Math.floor(viewport.height)
    canvas.style.width = `${Math.floor(viewport.width)}px`
    canvas.style.height = `${Math.floor(viewport.height)}px`

    const renderTask = page.render({ canvasContext: context, viewport })
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
    for (const rect of hl.rects) {
      const box = document.createElement('div')
      box.className = 'highlight-box'
      box.style.left = `${rect.left * 100}%`
      box.style.top = `${rect.top * 100}%`
      box.style.width = `${rect.width * 100}%`
      box.style.height = `${rect.height * 100}%`
      box.style.backgroundColor = hl.color || 'rgba(255, 210, 77, 0.45)'
      box.title = hl.text.slice(0, 100)
      box.dataset.highlightId = hl.id

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

// ============================================================================
// 文本划词选择 → 提取百分比坐标 → 暂存 pending → 弹出菜单
// ============================================================================

function handleTextSelection(evt: MouseEvent) {
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
  const clientRects = Array.from(range.getClientRects())
  if (clientRects.length === 0) return

  const text = selection.toString().trim()

  // 转换为百分比坐标（0~1），缩放无关
  const rects: HighlightRect[] = clientRects.map(r => ({
    left: (r.left - containerRect.left) / containerRect.width,
    top: (r.top - containerRect.top) / containerRect.height,
    width: r.width / containerRect.width,
    height: r.height / containerRect.height,
  }))

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
  showHighlightMenu.value = true
}

// ============================================================================
// 悬浮菜单操作
// ============================================================================

const HIGHLIGHT_COLORS: Record<string, string> = {
  yellow: 'rgba(255, 210, 77, 0.45)',
  green:  'rgba(60, 210, 120, 0.40)',
  red:    'rgba(255, 80, 80, 0.40)',
  blue:   'rgba(80, 150, 255, 0.40)',
}

function confirmHighlight(color: string) {
  if (!pendingHighlight.value) return

  const newHighlight: PageHighlight = {
    id: `hl-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    pageNum: pendingHighlight.value.pageNum,
    text: pendingHighlight.value.text,
    rects: pendingHighlight.value.rects,
    color: HIGHLIGHT_COLORS[color] || HIGHLIGHT_COLORS.yellow,
  }

  highlights.value = [...highlights.value, newHighlight]
  renderAnnotationLayer(newHighlight.pageNum)

  // 控制台输出（供调试/对接 API）
  console.log('📝 高亮已确认（百分比坐标，缩放无关）：', {
    page: newHighlight.pageNum,
    color,
    text: newHighlight.text.slice(0, 80),
    rects: newHighlight.rects.map(r => ({
      left: r.left.toFixed(4),
      top: r.top.toFixed(4),
      width: r.width.toFixed(4),
      height: r.height.toFixed(4),
    })),
  })

  dismissMenu()
}

function dismissMenu() {
  showHighlightMenu.value = false
  pendingHighlight.value = null
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

function deleteHighlight(id: string) {
  const item = highlights.value.find(h => h.id === id)
  if (!item) return
  highlights.value = highlights.value.filter(h => h.id !== id)
  renderAnnotationLayer(item.pageNum)
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

async function applyZoom(newScale: number) {
  scale.value = newScale
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

// ============================================================================
// 跳转 & 滚动
// ============================================================================

async function scrollToPage(page: number) {
  if (!containerRef.value) return
  const el = containerRef.value.querySelector<HTMLElement>(`[data-page="${page}"]`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  scrollPage.value = page
}

async function jumpTo(page: number, _text?: string) {
  if (!doc) return
  const target = Math.min(Math.max(Number(page) || 1, 1), totalPages.value || 1)
  await scrollToPage(target)
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

defineExpose({ jumpTo, highlightAndScrollTo, whenReady })
</script>

<template>
  <div class="pdf-reader">
    <!-- 工具栏（保留原有翻页/缩放控件） -->
    <div class="toolbar">
      <div>
        <el-button size="small" @click="zoomOut">Zoom out</el-button>
        <el-button size="small" @click="zoomIn">Zoom in</el-button>
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
        <span class="scale-badge">{{ Math.round(scale * 100) }}%</span>
      </div>
    </div>

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
    <!-- 连续滚动容器：骨架屏 + 按需渲染 Canvas -->
    <!-- ================================================================ -->
    <div
      v-else
      ref="containerRef"
      class="scroll-container slim-scroll"
      v-loading="pdfLoading"
      @mouseup="handleTextSelection"
    >
      <div
        v-for="p in totalPages"
        :key="p"
        :data-page="p"
        class="page-wrapper"
        :style="{ minHeight: pageHeightPx + 'px' }"
      >
        <div class="page-inner" :style="{ minWidth: pageWidthPx + 'px', minHeight: pageHeightPx + 'px' }">
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
        transform: 'translate(-50%, -100%)',
      }"
      @mousedown.stop
    >
      <button
        v-for="(_, color) in HIGHLIGHT_COLORS"
        :key="color"
        class="color-btn"
        :class="color"
        :title="color"
        @click.stop="confirmHighlight(color)"
      ></button>
      <div class="menu-divider" />
      <button class="action-btn" @click.stop="copyHighlightText" title="复制到剪贴板">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
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
  gap: 12px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 16px;
  background: rgba(255, 255, 255, .06);
  border: 1px solid rgba(255, 255, 255, .08);
  flex-shrink: 0;
}

.pager {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
}

.scale-badge {
  color: var(--muted);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

/* ===================================================================
   滚动容器
   =================================================================== */
.scroll-container {
  flex: 1;
  overflow-y: auto;
  border-radius: 18px;
  background: rgba(0, 0, 0, .26);
  padding: 16px 24px;
}

/* ===================================================================
   每页骨架
   =================================================================== */
.page-wrapper {
  margin: 0 auto 20px;
  max-width: 100%;
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
  pointer-events: auto;     /* 单个高亮框可以交互（hover tooltip 等） */
  transition: background-color .15s ease;
  overflow: visible;
}

.annotationLayer :deep(.highlight-box:hover) {
  filter: brightness(1.2);
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
  background: rgba(59, 130, 246, 0.25);
  border: 2px solid rgba(59, 130, 246, 0.7);
  animation: targetFlash 1.2s ease-in-out 3;
  z-index: 5;
}

@keyframes targetFlash {
  0%   { background: rgba(59, 130, 246, 0.45); border-color: rgba(59, 130, 246, 0.9); }
  50%  { background: rgba(59, 130, 246, 0.10); border-color: rgba(59, 130, 246, 0.3); }
  100% { background: rgba(59, 130, 246, 0.45); border-color: rgba(59, 130, 246, 0.9); }
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
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(24, 28, 36, .96);
  border: 1px solid rgba(255, 255, 255, .12);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, .45);
  backdrop-filter: blur(12px);
  user-select: none;
  animation: menuIn .18s ease-out;
}

@keyframes menuIn {
  from { opacity: 0; transform: translate(-50%, -100%) scale(.85); }
  to   { opacity: 1; transform: translate(-50%, -100%) scale(1); }
}

.pdf-highlight-menu .color-btn {
  width: 24px;
  height: 24px;
  border: 2px solid transparent;
  border-radius: 50%;
  cursor: pointer;
  transition: border-color .15s ease, transform .15s ease;
  padding: 0;
  outline: none;
}

.pdf-highlight-menu .color-btn.yellow { background: #ffd24d; }
.pdf-highlight-menu .color-btn.green  { background: #3cd278; }
.pdf-highlight-menu .color-btn.red    { background: #ff5050; }
.pdf-highlight-menu .color-btn.blue   { background: #5096ff; }

.pdf-highlight-menu .color-btn:hover {
  border-color: #fff;
  transform: scale(1.18);
}

.pdf-highlight-menu .menu-divider {
  width: 1px;
  height: 20px;
  background: rgba(255, 255, 255, .18);
  margin: 0 4px;
}

.pdf-highlight-menu .action-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: rgba(255, 255, 255, .08);
  color: rgba(255, 255, 255, .8);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background .15s ease, color .15s ease;
}

.pdf-highlight-menu .action-btn:hover {
  background: rgba(255, 255, 255, .18);
  color: #fff;
}
</style>
