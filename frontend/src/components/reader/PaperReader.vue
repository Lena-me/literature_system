<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
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

// ── Markdown 渲染器 ──
const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: true,
})

// 将 ContentItem[] 转为 Markdown 字符串
const markdownContent = computed(() => {
  if (!contentItems.value.length) return '*暂无解析内容*'
  return contentItems.value
    .map(item => {
      const text = item.content || ''
      switch (item.type) {
        case 'heading':
          const level = Math.min(item.level || 1, 6)
          return '#'.repeat(level) + ' ' + text
        case 'code':
          return '```\n' + text + '\n```'
        case 'table':
          return text // 表格已是 Markdown 格式
        case 'list':
        case 'list_item':
          return text
        case 'image':
          return `![${text}](${text})`
        default:
          return text
      }
    })
    .join('\n\n')
})

const renderedHtml = computed(() => md.render(markdownContent.value))

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
                <div v-if="activeTab === 'markdown'" class="markdown-body" v-html="renderedHtml"></div>

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
.reader-slide-enter-active,
.reader-slide-leave-active {
  transition: opacity 0.25s ease;
}
.reader-slide-enter-active .reader-drawer,
.reader-slide-leave-active .reader-drawer {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.reader-slide-enter-from {
  opacity: 0;
}
.reader-slide-enter-from .reader-drawer {
  transform: translateX(100%);
}
.reader-slide-leave-to {
  opacity: 0;
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
   Markdown Content
   ======================================== */
.markdown-body {
  padding: 28px 32px;
  font-size: 15px;
  line-height: 1.75;
  color: #334155;
  max-width: 100%;
}

/* Headings */
.markdown-body :deep(h1) {
  font-size: 22px;
  font-weight: 700;
  color: #0F172A;
  margin: 28px 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #E2E8F0;
}
.markdown-body :deep(h1:first-child) {
  margin-top: 0;
}

.markdown-body :deep(h2) {
  font-size: 18px;
  font-weight: 600;
  color: #1E293B;
  margin: 24px 0 10px;
}
.markdown-body :deep(h2:first-child) {
  margin-top: 0;
}

.markdown-body :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  color: #334155;
  margin: 20px 0 8px;
}

.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  font-size: 14px;
  font-weight: 600;
  color: #475569;
  margin: 16px 0 6px;
}

/* Paragraph */
.markdown-body :deep(p) {
  margin: 0 0 12px;
}

/* Code */
.markdown-body :deep(code) {
  background: #F1F5F9;
  color: #E11D48;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
}

.markdown-body :deep(pre) {
  background: #1E293B;
  color: #E2E8F0;
  padding: 16px 20px;
  border-radius: 10px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-body :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
  font-size: 13px;
  line-height: 1.6;
}

/* Table */
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}

.markdown-body :deep(th) {
  background: #F8FAFC;
  color: #475569;
  font-weight: 600;
  text-align: left;
  padding: 10px 14px;
  border: 1px solid #E2E8F0;
}

.markdown-body :deep(td) {
  padding: 8px 14px;
  border: 1px solid #E2E8F0;
  color: #334155;
}

.markdown-body :deep(tr:nth-child(even) td) {
  background: #F8FAFC;
}

/* Blockquote */
.markdown-body :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 16px;
  border-left: 3px solid #3B82F6;
  background: #F8FAFC;
  color: #64748B;
  border-radius: 0 6px 6px 0;
}

/* List */
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.markdown-body :deep(li) {
  margin: 4px 0;
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
