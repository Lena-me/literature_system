<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import 'katex/dist/katex.min.css'
import { papersApi } from '@/api/papers'
import { notesApi } from '@/api/notes'
import type { ContentItem, PaperNote, RelatedVisual, Source } from '@/types/domain'
import PdfReader from '@/components/reader/PdfReader.vue'
import PaperNotesPanel from '@/components/reader/PaperNotesPanel.vue'
import {
  navigateSourceInPdf,
  navigateVisualInPdf,
} from '@/utils/sourceNavigation'
import {
  isMixedFormulaBlock,
  looksLikeBareLatex,
  normalizeLatexForKatex,
  prepareMarkdownForRender,
  renderBareLatexBlock,
  renderKatexHtml,
  renderMathInMarkdownHtml,
} from '@/utils/mathRender'

const props = defineProps<{ paperId: number; paperTitle: string }>()
const emit = defineEmits<{ close: [] }>()

interface PaperReaderOpenOptions {
  page?: number
  highlight?: string
  source?: Source
  visual?: RelatedVisual
  tab?: 'markdown' | 'notes'
}

interface HighlightRect {
  left: number
  top: number
  width: number
  height: number
}

const HIGHLIGHT_HEX: Record<string, string> = {
  yellow: '#FFD24D',
  green: '#3CD278',
  red: '#FF5050',
  blue: '#5096FF',
}

// ── 状态 ──
const visible = ref(false)
const pdfUrl = ref('')
const contentItems = ref<ContentItem[]>([])
const paperNotes = ref<PaperNote[]>([])
const notesLoading = ref(false)
const loading = ref(false)
const activeTab = ref<'markdown' | 'notes'>('markdown')
const splitPercent = ref(62)
const dragging = ref(false)
const pdfReaderRef = ref<InstanceType<typeof PdfReader> | null>(null)
const notesPanelRef = ref<InstanceType<typeof PaperNotesPanel> | null>(null)
const initialPage = ref(1)
const highlightText = ref('')
const pendingNav = ref<PaperReaderOpenOptions | null>(null)
const formulaModeActive = ref(false)

// ── Markdown 渲染器（公式在 md.render 之后由 renderMathInMarkdownHtml 注入）──
const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
  typographer: true,
})

// ── 结构化章节（按 heading 分组折叠视图） ──
interface Section {
  title: string
  level: number
  children: ContentItem[]
}

const structuredSections = computed<Section[]>(() => {
  const items = contentItems.value
  if (!items.length) return []

  const sections: Section[] = []
  let current: Section | null = null

  for (const item of items) {
    const type = (item as any).type || (item as any).item_type || ''
    if (type === 'heading') {
      const level = (item as any).level || 1
      current = { title: (item as any).content || '', level, children: [] }
      sections.push(current)
    } else if (current) {
      current.children.push(item)
    } else {
      // 无 heading 开头的内容归入"引言 / 摘要"
      if (!sections.length) {
        sections.push({ title: '引言 / 摘要', level: 0, children: [] })
      }
      sections[0].children.push(item)
    }
  }

  // 如果没有任何章节（全是 heading 无 content），保留 heading 本身
  if (!sections.length && items.length) {
    sections.push({ title: '全文', level: 0, children: items })
  }

  return sections
})

// ── 单个 Block 的 Markdown 渲染（逐块渲染，保留坐标事件） ──
function renderItemHtml(item: ContentItem): string {
  const type = (item as any).type || (item as any).item_type || ''
  const text = (item.content || '').trim()

  if (type === 'heading') {
    const level = (item as any).level || 1
    return md.render('#'.repeat(level) + ' ' + text)
  }

  // 裸 LaTeX 段落（无 $$ 包裹，旧数据或未升维的公式块）
  if (looksLikeBareLatex(text)) {
    return renderBareLatexBlock(text)
  }

  const isDisplayFormula =
    type === 'formula' || (text.startsWith('$$') && text.endsWith('$$'))

  if (isDisplayFormula && !isMixedFormulaBlock(text)) {
    const inner = text.replace(/^\$\$|\$\$$/g, '').trim()
    const html = renderKatexHtml(inner, true)
    return html.includes('class="katex"')
      ? `<div class="formula-display">${html}</div>`
      : md.render(normalizeLatexForKatex(`$$\n${inner}\n$$`))
  }

  if (isDisplayFormula && isMixedFormulaBlock(text)) {
    const inner = text.replace(/^\$\$\n?|\n?\$\$$/g, '').trim()
    return renderMathInMarkdownHtml(md.render(prepareMarkdownForRender(inner)))
  }

  return renderMathInMarkdownHtml(md.render(prepareMarkdownForRender(text)))
}

// ── 点击 Block → 左侧 PDF 联动高亮并滚动 ──
function parseContentBbox(raw: unknown): [number, number, number, number] | null {
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

function handleBlockClick(item: ContentItem) {
  const pageNum = item.page_number
  if (!pageNum) return

  const pdfReader = pdfReaderRef.value as InstanceType<typeof PdfReader> | null
  if (!pdfReader) return

  const bbox = parseContentBbox((item as any).bbox)
  if (bbox && typeof (pdfReader as any).highlightAndScrollTo === 'function') {
    ;(pdfReader as any).highlightAndScrollTo(pageNum, bbox)
    return
  }

  if (typeof (pdfReader as any).jumpTo === 'function') {
    ;(pdfReader as any).jumpTo(pageNum)
  }
}

function noteToHighlightRects(bbox: PaperNote['bbox']): HighlightRect[] {
  if (!Array.isArray(bbox)) return []
  return bbox
    .map(item => ({
      left: Number(item.left),
      top: Number(item.top),
      width: Number(item.width),
      height: Number(item.height),
    }))
    .filter(item => [item.left, item.top, item.width, item.height].every(v => Number.isFinite(v)))
}

function applyNotesToPdfReader() {
  const reader = pdfReaderRef.value as any
  if (!reader?.setPersistedHighlights) return
  reader.setPersistedHighlights(
    paperNotes.value.map(note => ({
      id: note.id,
      pageNum: note.page_number,
      text: note.selected_text,
      rects: noteToHighlightRects(note.bbox),
      color: reader.hexToRgba?.(note.highlight_color) || undefined,
    })),
  )
}

async function loadNotes() {
  notesLoading.value = true
  try {
    paperNotes.value = await notesApi.list(props.paperId)
  } catch {
    paperNotes.value = []
  } finally {
    notesLoading.value = false
    await nextTick()
    applyNotesToPdfReader()
  }
}

async function saveHighlight(payload: {
  pageNum: number
  text: string
  rects: HighlightRect[]
  colorKey: string
  noteContent?: string
}) {
  const saved = await notesApi.create({
    paper_id: props.paperId,
    page_number: payload.pageNum,
    bbox: payload.rects,
    selected_text: payload.text,
    note_content: payload.noteContent || null,
    highlight_color: HIGHLIGHT_HEX[payload.colorKey] || HIGHLIGHT_HEX.yellow,
  })
  await loadNotes()
  return {
    id: saved.id,
    color: (pdfReaderRef.value as any)?.hexToRgba?.(saved.highlight_color),
  }
}

async function deleteHighlight(noteId: number | string) {
  await notesApi.delete(Number(noteId))
  await loadNotes()
}

async function applyPendingNavigation() {
  const nav = pendingNav.value
  if (!nav) return

  if (nav.tab) activeTab.value = nav.tab
  if (nav.page) initialPage.value = nav.page
  if (nav.highlight) highlightText.value = nav.highlight

  const reader = pdfReaderRef.value
  if (!reader) return

  if (typeof reader.whenReady === 'function') {
    await reader.whenReady(12000)
  }

  if (nav.source) {
    await navigateSourceInPdf(reader, nav.source, 300)
    pendingNav.value = null
    return
  }

  if (nav.visual) {
    await navigateVisualInPdf(reader, nav.visual, props.paperId, 300)
    pendingNav.value = null
    return
  }

  if (nav.page) {
    await reader.jumpTo?.(nav.page, nav.highlight || undefined)
  }

  pendingNav.value = null
}

async function onNoteSelect(note: PaperNote) {
  const reader = pdfReaderRef.value
  if (!reader) return
  const rects = noteToHighlightRects(note.bbox)
  if (rects.length === 1) {
    const rect = rects[0]
    await reader.highlightAndScrollTo?.(note.page_number, [
      rect.left,
      rect.top,
      rect.left + rect.width,
      rect.top + rect.height,
    ])
    return
  }
  if (rects.length > 1) {
    const xs = rects.map(r => r.left)
    const ys = rects.map(r => r.top)
    const xe = rects.map(r => r.left + r.width)
    const ye = rects.map(r => r.top + r.height)
    await reader.highlightAndScrollTo?.(note.page_number, [
      Math.min(...xs),
      Math.min(...ys),
      Math.max(...xe),
      Math.max(...ye),
    ])
    return
  }
  await reader.jumpTo?.(note.page_number)
}

async function onHighlightNoteClick(noteId: number) {
  activeTab.value = 'notes'
  await nextTick()
  const scrolled = notesPanelRef.value?.scrollToNote(noteId)
  if (!scrolled) {
    await loadNotes()
    await nextTick()
    notesPanelRef.value?.scrollToNote(noteId)
  }
}

function toggleFormulaModeInReader() {
  const reader = pdfReaderRef.value as { toggleFormulaMode?: () => void } | null
  reader?.toggleFormulaMode?.()
}

// ── 加载 ──
async function open(options?: PaperReaderOpenOptions) {
  pendingNav.value = options || null
  initialPage.value = options?.page || 1
  highlightText.value = options?.highlight || ''
  if (options?.tab) activeTab.value = options.tab
  visible.value = true
  await loadData()
  await applyPendingNavigation()
}

async function navigateToSource(source: Source) {
  pendingNav.value = { source, tab: 'markdown' }
  if (!visible.value) {
    await open({ source, tab: 'markdown' })
    return
  }
  await applyPendingNavigation()
}

async function navigateToVisual(visual: RelatedVisual) {
  pendingNav.value = { visual, tab: 'markdown' }
  if (!visible.value) {
    await open({ visual, tab: 'markdown' })
    return
  }
  await applyPendingNavigation()
}

async function loadData() {
  loading.value = true
  try {
    const [blobUrl, contentRes] = await Promise.all([
      papersApi.fileBlobUrl(props.paperId).catch(() => null),
      papersApi.content(props.paperId).catch(() => []),
    ])
    await loadNotes()
    if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
      URL.revokeObjectURL(pdfUrl.value)
    }
    pdfUrl.value = blobUrl || ''
    contentItems.value = Array.isArray(contentRes) ? contentRes : []
  } catch {
    // ignore
  } finally {
    loading.value = false
    await nextTick()
    applyNotesToPdfReader()
    schedulePdfFit()
  }
}

async function schedulePdfFit() {
  await nextTick()
  await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))

  const reader = pdfReaderRef.value as {
    whenReady?: (timeoutMs?: number) => Promise<boolean>
    fitToContainer?: (force?: boolean) => void | Promise<void>
  } | null
  if (!reader) return

  const ready = await reader.whenReady?.(15000)
  if (!ready) return

  await reader.fitToContainer?.(true)
  await nextTick()
  await reader.fitToContainer?.(true)

  window.setTimeout(() => {
    void reader.fitToContainer?.(true)
  }, 420)
}

function onDrawerEntered() {
  void schedulePdfFit()
}

function close() {
  visible.value = false
  pendingNav.value = null
  formulaModeActive.value = false
  if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(pdfUrl.value)
    pdfUrl.value = ''
  }
  ;(pdfReaderRef.value as any)?.clearPersistedHighlights?.()
  paperNotes.value = []
  emit('close')
}

// ── 分割线拖拽 ──
function startDrag(e: MouseEvent) {
  e.preventDefault()
  dragging.value = true
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
}

function onDrag(e: MouseEvent) {
  if (!dragging.value) return
  const container = document.querySelector('.reader-panes') as HTMLElement | null
  if (!container) return
  const rect = container.getBoundingClientRect()
  const pct = ((e.clientX - rect.left) / rect.width) * 100
  splitPercent.value = Math.max(20, Math.min(80, pct))
}

function stopDrag() {
  dragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('keydown', onKeydown)
  document.body.classList.remove('reader-open')
  if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(pdfUrl.value)
  }
})

watch(splitPercent, () => {
  nextTick(() => {
    (pdfReaderRef.value as { fitToContainer?: (force?: boolean) => void } | null)?.fitToContainer?.(true)
  })
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

watch(visible, v => {
  document.body.classList.toggle('reader-open', v)
  if (v) document.addEventListener('keydown', onKeydown)
  else document.removeEventListener('keydown', onKeydown)
})

defineExpose({ open, navigateToSource, navigateToVisual })
</script>

<template>
  <Teleport to="body">
    <transition name="reader-slide" @after-enter="onDrawerEntered">
      <div v-if="visible" class="reader-overlay" @click.self="close">
        <div class="reader-drawer" @click.stop>
          <!-- Header -->
          <header class="reader-header">
            <h2 class="reader-title" :title="paperTitle">{{ paperTitle }}</h2>
            <button class="reader-close-btn" @click="close">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </header>

          <!-- Loading -->
          <div v-if="loading" class="reader-loading">
            <div class="reader-spinner"></div>
            <span>加载中...</span>
          </div>

          <!-- 双窗格 -->
          <div v-else class="reader-panes">
            <!-- 左侧：PDF -->
            <section class="reader-pane reader-pane--pdf" :style="{ width: splitPercent + '%', flexShrink: 0 }">
              <div class="pane-header pane-header--pdf">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span>PDF 原文</span>
                <el-button
                  v-if="pdfUrl"
                  size="small"
                  class="formula-header-btn"
                  :type="formulaModeActive ? 'primary' : 'default'"
                  @click="toggleFormulaModeInReader"
                >
                  {{ formulaModeActive ? '退出框选' : '框选公式' }}
                </el-button>
                <span v-if="formulaModeActive" class="formula-mode-tip">在 PDF 上拖拽框选公式区域</span>
              </div>
              <div class="pane-body pane-body--pdf">
                <PdfReader
                  v-if="pdfUrl"
                  ref="pdfReaderRef"
                  :url="pdfUrl"
                  :initial-page="initialPage"
                  :highlight-text="highlightText"
                  :save-highlight-handler="saveHighlight"
                  :delete-highlight-handler="deleteHighlight"
                  :show-formula-button="false"
                  @highlight-saved="loadNotes"
                  @highlight-click="onHighlightNoteClick"
                  @formula-mode-change="formulaModeActive = $event"
                />
                <div v-else class="pane-empty">暂无 PDF 文件</div>
              </div>
            </section>

            <!-- 分割线 -->
            <div
              class="reader-divider"
              :class="{ active: dragging }"
              title="拖拽调整左右宽度"
              @mousedown="startDrag"
            >
              <div class="reader-divider-grip"></div>
            </div>

            <!-- 右侧：结构化知识 -->
            <section class="reader-pane reader-pane--md">
              <div class="pane-header">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
                <span>结构化知识</span>

                <!-- Tabs -->
                <div class="pane-tabs">
                  <button
                    class="pane-tab"
                    :class="{ active: activeTab === 'markdown' }"
                    @click="activeTab = 'markdown'"
                  >Markdown 视图</button>
                  <button
                    class="pane-tab"
                    :class="{ active: activeTab === 'notes' }"
                    @click="activeTab = 'notes'"
                  >我的笔记</button>
                </div>
              </div>

              <div class="pane-body">
                <!-- Markdown 视图 -->
                <div v-if="activeTab === 'markdown'" class="accordion-body">
                  <template v-if="structuredSections.length">
                    <details
                      v-for="(sec, si) in structuredSections"
                      :key="si"
                      class="acc-section"
                      :open="si === 0"
                    >
                      <summary class="acc-summary">
                        <span class="acc-title">{{ sec.title }}</span>
                        <span v-if="sec.children.length" class="acc-count">{{ sec.children.length }}</span>
                      </summary>
                      <div class="acc-content">
                        <div
                          v-for="(item, idx) in sec.children"
                          :key="idx"
                          class="clickable-block"
                          :class="{ 'has-locate': item.page_number }"
                          @click="handleBlockClick(item)"
                          v-html="renderItemHtml(item)"
                        ></div>
                      </div>
                    </details>
                  </template>
                  <div v-else class="pane-empty">暂无解析内容</div>
                </div>

                <!-- 笔记面板 -->
                <PaperNotesPanel
                  v-else
                  ref="notesPanelRef"
                  :paper-id="paperId"
                  :notes="paperNotes"
                  :loading="notesLoading"
                  @select="onNoteSelect"
                  @refresh="loadNotes"
                />
              </div>
            </section>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
/* ========================================
   Overlay + Drawer
   ======================================== */
.reader-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-surface);
  z-index: 1100;
  display: flex;
  justify-content: stretch;
}

.reader-drawer {
  width: 100%;
  max-width: 100vw;
  height: 100%;
  background: var(--bg-surface);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Slide transition ── */

.reader-slide-enter-active .reader-drawer,
.reader-slide-leave-active .reader-drawer {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.reader-slide-enter-from .reader-drawer {
  transform: translateX(100%);
}
.reader-slide-leave-to .reader-drawer {
  transform: translateX(100%);
}

/* ========================================
   Header
   ======================================== */
.reader-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px 8px;
  flex-shrink: 0;
  gap: 12px;
  border-bottom: 1px solid var(--border-lighter);
}

.reader-title {
  font-size: 15px;
  font-weight: 700;
  color: #0F172A;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.reader-close-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #94A3B8;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.reader-close-btn:hover {
  background: #F1F5F9;
  color: var(--text-primary);
}

/* ========================================
   Loading
   ======================================== */
.reader-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #94A3B8;
  font-size: 14px;
}

.reader-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #F1F5F9;
  border-top-color: #3B82F6;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ========================================
   Panes
   ======================================== */
.reader-panes {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.reader-pane {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.pane-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: var(--bg-canvas);
  border-bottom: 1px solid var(--border-lighter);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  flex-shrink: 0;
  white-space: nowrap;
}

.pane-header--pdf {
  flex-wrap: wrap;
  row-gap: 6px;
}

.formula-header-btn {
  margin-left: 4px;
  font-weight: 600;
}

.formula-mode-tip {
  margin-left: auto;
  font-size: 12px;
  font-weight: 500;
  color: #2563EB;
}

.pane-tabs {
  display: flex;
  gap: 2px;
  margin-left: auto;
  background: #F1F5F9;
  border-radius: 8px;
  padding: 2px;
}

.pane-tab {
  padding: 5px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748B;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.pane-tab:hover {
  color: var(--text-primary);
}

.pane-tab.active {
  background: #fff;
  color: #1D4ED8;
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.reader-pane--md {
  flex: 1;
  min-width: 0;
}

.reader-pane--pdf {
  min-width: 0;
}

.pane-body--pdf {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 0;
  background: #525659;
}

.pane-body--pdf :deep(.pdf-reader) {
  flex: 1;
  min-height: 0;
  height: 100%;
}

.pane-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.pane-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94A3B8;
  font-size: 14px;
  padding: 40px;
}

/* ========================================
   Resizable Divider
   ======================================== */
.reader-divider {
  width: 10px;
  flex-shrink: 0;
  background: transparent;
  border-left: 1px solid var(--border-light);
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  position: relative;
  z-index: 10;
}

.reader-divider::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: -5px;
  right: -5px;
}

.reader-divider:hover,
.reader-divider.active {
  background: rgba(166, 124, 82, 0.05);
  border-left-color: rgba(166, 124, 82, 0.3);
}

.reader-divider-grip {
  width: 3px;
  height: 24px;
  border-radius: 2px;
  background: rgba(166, 124, 82, 0.5);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.reader-divider:hover .reader-divider-grip,
.reader-divider.active .reader-divider-grip {
  opacity: 1;
}

/* ========================================
   Accordion (结构化折叠视图)
   ======================================== */
.accordion-body {
  padding: 20px 24px;
}

/* ── 章节容器 ── */
.acc-section {
  margin-bottom: 4px;
  border: none;
  outline: none;
}

.acc-section[open] {
  margin-bottom: 12px;
}

/* ── 标题栏 ── */
.acc-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  list-style: none;
  transition: background 0.2s, transform 0.2s, box-shadow 0.2s;
  outline: none;
  user-select: none;
  backdrop-filter: blur(0);
}

.acc-summary::-webkit-details-marker {
  display: none;
}
.acc-summary::marker {
  display: none;
  content: '';
}

/* 自定义三角箭头 */
.acc-summary::before {
  content: '▸';
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  font-size: 12px;
  color: #94A3B8;
  transition: transform 0.2s;
  flex-shrink: 0;
}

.acc-section[open] > .acc-summary::before {
  transform: rotate(90deg);
}

.acc-summary:hover {
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(8px);
  box-shadow: var(--shadow-sm);
  transform: scale(1.005);
}

.acc-section[open] > .acc-summary {
  background: rgba(248, 250, 252, 0.8);
  backdrop-filter: blur(6px);
}

/* 标题文字 */
.acc-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 子项计数 */
.acc-count {
  font-size: 11px;
  font-weight: 500;
  color: #94A3B8;
  background: #F1F5F9;
  padding: 1px 6px;
  border-radius: 10px;
  flex-shrink: 0;
}

/* ── 内容区 ── */
.acc-content {
  padding: 8px 0 4px 32px;
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);
}

/* ── 可点击 Block（逐块渲染，保留坐标联动事件） ── */
.clickable-block {
  margin-bottom: 0.8em;
  border-radius: 6px;
  transition: background-color 0.15s ease;
  cursor: default;
}

.clickable-block.has-locate {
  cursor: pointer;
}

.clickable-block.has-locate:hover {
  background-color: rgba(166, 124, 82, 0.08);
  outline: 1px dashed rgba(166, 124, 82, 0.35);
  outline-offset: 2px;
}

.acc-item {
  margin-bottom: 1em;
}

/* 内容区内嵌元素样式 */
.acc-content :deep(p) {
  margin: 0 0 0.8em;
}

.acc-content :deep(code) {
  background: #F1F5F9;
  color: #E11D48;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
}

.acc-content :deep(pre) {
  background: #1E293B;
  color: #E2E8F0;
  padding: 14px 18px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 10px 0;
}

.acc-content :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
  font-size: 13px;
  line-height: 1.6;
}

.acc-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
  table-layout: auto;
}

.acc-content :deep(th) {
  background: #F8FAFC;
  color: var(--text-primary);
  font-weight: 600;
  text-align: left;
  padding: 8px 12px;
  border: 1px solid #E2E8F0;
  vertical-align: middle;
}

.acc-content :deep(td) {
  padding: 8px 12px;
  border: 1px solid #E2E8F0;
  color: var(--text-primary);
  vertical-align: middle;
  line-height: 1.5;
}

/* 公式列略宽，类别列保持紧凑 */
.acc-content :deep(th:last-child),
.acc-content :deep(td:last-child) {
  min-width: 0;
}

.acc-content :deep(th:first-child),
.acc-content :deep(td:first-child) {
  width: 28%;
  white-space: nowrap;
}

.acc-content :deep(tr:nth-child(even) td) {
  background: #F8FAFC;
}

.acc-content :deep(blockquote) {
  margin: 10px 0;
  padding: 6px 14px;
  border-left: 2px solid #3B82F6;
  background: #F8FAFC;
  color: #64748B;
  border-radius: 0 4px 4px 0;
}

.acc-content :deep(ul),
.acc-content :deep(ol) {
  padding-left: 22px;
  margin: 6px 0;
}

.acc-content :deep(li) {
  margin: 3px 0;
  line-height: 1.7;
}

/* Link */
.markdown-body :deep(a) {
  color: #3B82F6;
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

/* Horizontal rule */
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid #E2E8F0;
  margin: 20px 0;
}

/* Image */
.acc-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 10px 0;
}

/* KaTeX formula blocks */
.acc-content :deep(.formula-display) {
  margin: 14px 0;
  overflow-x: auto;
  overflow-y: hidden;
  text-align: center;
}

.acc-content :deep(.katex-display) {
  margin: 14px 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.acc-content :deep(.katex) {
  font-size: 1.05em;
}

/* 行内公式：避免与中文重叠，保持垂直居中 */
.acc-content :deep(.math-inline) {
  display: inline;
  line-height: normal;
  vertical-align: middle;
  margin: 0 0.1em;
  padding: 0;
}

.acc-content :deep(.math-inline--cell) {
  display: inline;
  overflow: visible;
}

.acc-content :deep(.katex:not(.katex-display)) {
  display: inline-block;
  line-height: normal;
  vertical-align: middle;
  text-indent: 0;
}

/* 表格内公式：略缩小、无滚动条，自然换行 */
.acc-content :deep(td .math-inline--cell),
.acc-content :deep(th .math-inline--cell) {
  display: inline;
  overflow: visible;
  max-width: none;
}

.acc-content :deep(td .katex),
.acc-content :deep(th .katex) {
  font-size: 0.95em;
  white-space: normal;
  max-width: 100%;
}

.acc-content :deep(td .katex-display),
.acc-content :deep(th .katex-display) {
  margin: 0;
  text-align: left;
}

/* formula-block fallback */
.acc-content :deep(.formula-block) {
  background: #F8FAFC;
  border-left: 3px solid #3B82F6;
  padding: 10px 14px;
  margin: 10px 0;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: var(--text-primary);
  border-radius: 0 8px 8px 0;
  overflow-x: auto;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}

/* Bold / Italic */
.markdown-body :deep(strong) {
  color: #0F172A;
  font-weight: 700;
}
</style>
