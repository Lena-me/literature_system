<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
<<<<<<< HEAD
import mk from 'markdown-it-katex'
=======
>>>>>>> 4ef192ef98cfd767a44b504f4bc985edd4e31f23
import { papersApi } from '@/api/papers'
import type { ContentItem } from '@/types/domain'
import PdfReader from '@/components/reader/PdfReader.vue'

const props = defineProps<{ paperId: number; paperTitle: string }>()
const emit = defineEmits<{ close: [] }>()

// ── 状态 ──
const visible = ref(false)
const pdfUrl = ref('')
const contentItems = ref<ContentItem[]>([])
const loading = ref(false)
const activeTab = ref<'markdown' | 'graph'>('markdown')
const splitPercent = ref(50) // 左侧百分比
const dragging = ref(false)

<<<<<<< HEAD
// ── Markdown 渲染器（挂载 KaTeX 插件以支持 $$...$$ / $...$ 数学公式）──
const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
  typographer: true,
}).use(mk)
=======
// ── Markdown 渲染器 ──
const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: true,
})
>>>>>>> 4ef192ef98cfd767a44b504f4bc985edd4e31f23

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

<<<<<<< HEAD
// 章节级完整 Markdown 渲染流 ──
function renderSectionHtml(children: ContentItem[]): string {
  // 1. 将散落的数据库碎片，重新拼装成连续的 Markdown 文档流
  const combinedMarkdown = children.map(item => {
    const type = (item as any).type || (item as any).item_type || ''
    const text = (item.content || '').trim()

    // 还原标题的 Markdown 语义
    if (type === 'heading') {
      const level = (item as any).level || 1
      return '#'.repeat(level) + ' ' + text
    }

    // 公式/表格/图片等直接回填（后端已输出标准 Markdown 语法）
    return text
  }).join('\n\n') // 双换行确保 Markdown 标准块之间的隔离

  // 2. 一次性交给 markdown-it（内置 KaTeX 插件）解析完整的 AST
  return md.render(combinedMarkdown)
=======
// 渲染单个 ContentItem 为 HTML
function renderItemHtml(item: ContentItem): string {
  const type = (item as any).type || (item as any).item_type || ''
  const text = item.content || ''
  switch (type) {
    case 'code':
      return '<pre><code>' + escapeHtml(text) + '</code></pre>'
    case 'table':
      return text // 已是 Markdown table
    case 'image':
      return `<img src="${escapeHtml(text)}" alt="${escapeHtml(text)}" style="max-width:100%" />`
    case 'heading':
      return '<p><strong>' + escapeHtml(text) + '</strong></p>'
    case 'list_item':
      return '<p>' + escapeHtml(text) + '</p>'
    default:
      // paragraph 等 → 用 MarkdownIt 渲染内联格式
      return md.renderInline(text) ? md.render(text) : '<p>' + escapeHtml(text) + '</p>'
  }
>>>>>>> 4ef192ef98cfd767a44b504f4bc985edd4e31f23
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// ── 加载 ──
function open() {
  visible.value = true
  loadData()
}

async function loadData() {
  loading.value = true
  try {
    const [blobUrl, contentRes] = await Promise.all([
      papersApi.fileBlobUrl(props.paperId).catch(() => null),
      papersApi.content(props.paperId).catch(() => []),
    ])
    // 清理旧 blob URL
    if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
      URL.revokeObjectURL(pdfUrl.value)
    }
    pdfUrl.value = blobUrl || ''
    contentItems.value = Array.isArray(contentRes) ? contentRes : []
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

function close() {
  visible.value = false
  if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(pdfUrl.value)
    pdfUrl.value = ''
  }
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
  if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(pdfUrl.value)
  }
})

// ── Keyboard ──
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

watch(visible, v => {
  if (v) document.addEventListener('keydown', onKeydown)
  else document.removeEventListener('keydown', onKeydown)
})

defineExpose({ open })
</script>

<template>
  <Teleport to="body">
    <transition name="reader-slide">
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
            <section class="reader-pane reader-pane--pdf" :style="{ width: splitPercent + '%' }">
              <div class="pane-header">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span>PDF 原文</span>
              </div>
              <div class="pane-body">
                <PdfReader
                  v-if="pdfUrl"
                  :url="pdfUrl"
                />
                <div v-else class="pane-empty">暂无 PDF 文件</div>
              </div>
            </section>

            <!-- 分割线 -->
            <div
              class="reader-divider"
              :class="{ active: dragging }"
              @mousedown="startDrag"
            >
              <div class="reader-divider-grip"></div>
            </div>

            <!-- 右侧：结构化知识 -->
            <section class="reader-pane reader-pane--md" :style="{ width: (100 - splitPercent) + '%' }">
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
                    :class="{ active: activeTab === 'graph' }"
                    @click="activeTab = 'graph'"
                  >知识图谱预览</button>
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
<<<<<<< HEAD
                      <div class="acc-content" v-html="renderSectionHtml(sec.children)"></div>
=======
                      <div class="acc-content">
                        <div
                          v-for="(child, ci) in sec.children"
                          :key="ci"
                          class="acc-item"
                          v-html="renderItemHtml(child)"
                        ></div>
                      </div>
>>>>>>> 4ef192ef98cfd767a44b504f4bc985edd4e31f23
                    </details>
                  </template>
                  <div v-else class="pane-empty">暂无解析内容</div>
                </div>

                <!-- 知识图谱预览 -->
                <div v-else class="pane-empty">知识图谱预览功能即将上线</div>
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
  background: rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.reader-drawer {
  width: 85vw;
  height: 100%;
  background: #fff;
  box-shadow: -8px 0 30px rgba(0, 0, 0, 0.12);
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
  padding: 16px 24px;
  border-bottom: 1px solid #F1F5F9;
  flex-shrink: 0;
  gap: 16px;
}

.reader-title {
  font-size: 17px;
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
  color: #475569;
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
  padding: 12px 20px;
  background: #F8FAFC;
  border-bottom: 1px solid #F1F5F9;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  flex-shrink: 0;
  white-space: nowrap;
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
  color: #334155;
}

.pane-tab.active {
  background: #fff;
  color: #1D4ED8;
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
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
  width: 6px;
  flex-shrink: 0;
  background: #F1F5F9;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
  position: relative;
}

.reader-divider:hover,
.reader-divider.active {
  background: #3B82F6;
}

.reader-divider-grip {
  width: 2px;
  height: 40px;
  border-radius: 1px;
  background: #CBD5E1;
  transition: background 0.15s;
}

.reader-divider:hover .reader-divider-grip,
.reader-divider.active .reader-divider-grip {
  background: #fff;
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
  color: #334155;
  cursor: pointer;
  border-radius: 6px;
  list-style: none;
  transition: background 0.12s;
  outline: none;
  user-select: none;
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
  background: #F8FAFC;
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
  color: #475569;
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
}

.acc-content :deep(th) {
  background: #F8FAFC;
  color: #475569;
  font-weight: 600;
  text-align: left;
  padding: 8px 12px;
  border: 1px solid #E2E8F0;
}

.acc-content :deep(td) {
  padding: 6px 12px;
  border: 1px solid #E2E8F0;
  color: #334155;
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
<<<<<<< HEAD
.acc-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 10px 0;
}

/* KaTeX formula blocks */
.acc-content :deep(.katex-display) {
  margin: 14px 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.acc-content :deep(.katex) {
  font-size: 1.08em;
}

/* formula-block fallback */
.acc-content :deep(.formula-block) {
  background: #F8FAFC;
  border-left: 3px solid #3B82F6;
  padding: 10px 14px;
  margin: 10px 0;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: #334155;
  border-radius: 0 8px 8px 0;
  overflow-x: auto;
=======
.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 8px;
>>>>>>> 4ef192ef98cfd767a44b504f4bc985edd4e31f23
}

/* Bold / Italic */
.markdown-body :deep(strong) {
  color: #0F172A;
  font-weight: 700;
}
</style>
