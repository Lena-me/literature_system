<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useNotebookStore } from '@/stores/notebook'
import { papersApi } from '@/api/papers'
import { ElMessage } from 'element-plus'
import type { Source } from '@/types/domain'
import SourceBar from '@/components/notebook/SourceBar.vue'
import MessageList from '@/components/notebook/MessageList.vue'
import ChatInput from '@/components/notebook/ChatInput.vue'
import PdfReader from '@/components/reader/PdfReader.vue'
import SuggestedQuestions from '@/components/notebook/SuggestedQuestions.vue'
import MultiPaperComparePanel from '@/components/notebook/MultiPaperComparePanel.vue'

const route = useRoute()
const notebook = useNotebookStore()

// SourceBar ref — expose openPicker
const sourceBarRef = ref<InstanceType<typeof SourceBar> | null>(null)
const showComparePanel = ref(false)

// ——— Drag & Drop ———
const isDragOver = ref(false)
let dragEnterCount = 0

function onDragEnter(e: DragEvent) {
  e.preventDefault()
  dragEnterCount++
  isDragOver.value = true
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

function onDragLeave(e: DragEvent) {
  e.preventDefault()
  dragEnterCount--
  if (dragEnterCount <= 0) {
    dragEnterCount = 0
    isDragOver.value = false
  }
}

async function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  dragEnterCount = 0

  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  const uploadedIds: number[] = []
  for (const file of Array.from(files)) {
    if (file.type !== 'application/pdf') {
      ElMessage.warning(`${file.name} 不是 PDF 文件，已跳过`)
      continue
    }
    try {
      const paper = await papersApi.upload(file)
      uploadedIds.push(paper.id)
      await notebook.addSources([paper.id])
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '上传失败'
      ElMessage.error(`${file.name}: ${msg}`)
    }
  }

  if (uploadedIds.length > 0) {
    ElMessage.success(`已上传并挂载 ${uploadedIds.length} 篇文献`)
  }
}

// ——— ChatInput events ———
function onChatInputOpenLibraryPicker() {
  sourceBarRef.value?.openPicker()
}

function onChatInputFilesUploaded(ids: number[]) {
  // Files already added to session inside ChatInput
}

function openComparePanel() {
  if (notebook.activeSources.length < 2) {
    ElMessage.warning('请先在当前会话中挂载至少 2 篇文献')
    return
  }
  showComparePanel.value = true
}

// ——— ReadingDrawer ———
const pdfUrl = ref('')
const pdfError = ref('')
const pdfPage = ref(1)
const pdfHighlight = ref('')
const drawerTab = ref<'pdf' | 'outline'>('pdf')
const pdfReaderRef = ref<InstanceType<typeof PdfReader> | null>(null)

onMounted(async () => {
  const sessionId = route.params.id ? Number(route.params.id) : null
  if (sessionId) {
    await notebook.switchSession(sessionId)
  }
})

async function onSourceClick(source: Source) {
  notebook.openReadingDrawer(
    source.paper_id,
    source.page_number,
    source.snippet || source.text
  )
  pdfPage.value = source.page_number || 1
  pdfHighlight.value = source.snippet || source.text || ''
  await loadPdf(source.paper_id)
  await new Promise(r => setTimeout(r, 200))
  pdfReaderRef.value?.jumpTo?.(pdfPage.value, pdfHighlight.value)
}

async function loadPdf(paperId: number) {
  pdfUrl.value = ''
  pdfError.value = ''
  try {
    pdfUrl.value = await papersApi.fileBlobUrl(paperId)
  } catch (e: any) {
    pdfError.value = e?.response?.data?.detail || e?.message || 'PDF无法加载'
    console.error('PDF load error:', e)
  }
}

async function onChipClick(paperId: number) {
  notebook.openReadingDrawer(paperId)
  pdfPage.value = 1
  pdfHighlight.value = ''
  drawerTab.value = 'pdf'
  await loadPdf(paperId)
}

function closeDrawer() {
  notebook.closeReadingDrawer()
  onOldUrlCleanup(pdfUrl.value)
  pdfUrl.value = ''
}

function onOldUrlCleanup(url: string) {
  if (url?.startsWith('blob:')) {
    try { URL.revokeObjectURL(url) } catch {}
  }
}
</script>

<template>
  <div
    class="notebook-view"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <!-- ★ Drag & Drop 遮罩 -->
    <Transition name="dnd-fade">
      <div v-if="isDragOver" class="dnd-overlay">
        <div class="dnd-content">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="var(--academic-primary)" stroke-width="1.5" stroke-linecap="round">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <p>松开鼠标，将文献挂载至当前会话</p>
          <span>仅支持 PDF 文件</span>
        </div>
      </div>
    </Transition>

    <!-- 欢迎页 -->
    <div v-if="!notebook.activeSessionId" class="welcome-screen">
      <div class="welcome-spark">✦</div>
      <h2>欢迎使用 AI 研读工作台</h2>
      <p>在左侧选择一个会话开始探索，或者上传文献获得智能分析。</p>
    </div>

    <!-- 主画布 -->
    <template v-else>
      <div class="top-bar">
        <SourceBar ref="sourceBarRef" @chip-click="onChipClick" />
        <button
          class="compare-entry"
          :disabled="notebook.activeSources.length < 2"
          @click="openComparePanel"
        >
          <span>多文献对比</span>
          <b>{{ notebook.activeSources.length }}</b>
        </button>
      </div>
      <div class="chat-body">
        <!-- ★ 会话切换 loading -->
        <div v-if="notebook.isSwitchingSession" class="switch-loading">
          <span class="loading-pulse"></span>
          <span>加载对话中...</span>
        </div>
        <template v-else>
          <SuggestedQuestions />
          <MessageList @source-click="onSourceClick" />
        </template>
      </div>
      <ChatInput
        class="chat-input-fixed"
        @open-library-picker="onChatInputOpenLibraryPicker"
        @files-uploaded="onChatInputFilesUploaded"
      />
    </template>

    <!-- ReadingDrawer -->
    <Transition name="drawer-slide">
      <div v-if="notebook.isReadingDrawerOpen" class="reading-drawer">
        <div class="drawer-head">
          <span class="drawer-title">
            {{ notebook.activeSources.find(p => p.id === notebook.currentReadingPaperId)?.title || '文献阅读' }}
          </span>
          <div class="drawer-tabs">
            <button :class="{ active: drawerTab === 'pdf' }" @click="drawerTab = 'pdf'">PDF</button>
            <button :class="{ active: drawerTab === 'outline' }" @click="drawerTab = 'outline'">大纲</button>
          </div>
          <button class="drawer-close" @click="closeDrawer">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="drawer-body">
          <div v-show="drawerTab === 'pdf'" class="pdf-container">
            <div v-if="pdfError" class="pdf-error">{{ pdfError }}</div>
            <PdfReader
              v-else-if="pdfUrl"
              ref="pdfReaderRef"
              :url="pdfUrl"
              :initial-page="pdfPage"
              :highlight-text="pdfHighlight"
              @old-url-cleanup="onOldUrlCleanup"
            />
            <div v-else class="pdf-loading">加载中...</div>
          </div>
          <div v-show="drawerTab === 'outline'" class="outline-container">
            <div class="outline-placeholder">大纲功能开发中...</div>
          </div>
        </div>
      </div>
    </Transition>

    <MultiPaperComparePanel
      :visible="showComparePanel"
      :papers="notebook.activeSources"
      @close="showComparePanel = false"
      @source-click="onSourceClick"
    />
  </div>
</template>

<style scoped>
.notebook-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  background: var(--academic-canvas);
}

/* ===== Drag & Drop 遮罩 ===== */
.dnd-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  background: rgba(248, 250, 252, 0.85);
  backdrop-filter: blur(12px);
  display: grid;
  place-items: center;
  border: 3px dashed var(--academic-primary);
  border-radius: 16px;
  margin: 8px;
}

.dnd-content {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.dnd-content p {
  font-size: 18px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin: 0;
}

.dnd-content span {
  font-size: 13px;
  color: var(--academic-text-muted);
}

.dnd-fade-enter-active { transition: all 0.2s ease; }
.dnd-fade-leave-active { transition: all 0.15s ease; }
.dnd-fade-enter-from,
.dnd-fade-leave-to { opacity: 0; }

/* ===== 侧边栏展开按钮 ===== */
.top-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--academic-border);
}

.top-bar :deep(.source-bar) {
  flex: 1;
  border-bottom: none;
}

.compare-entry {
  margin-right: 16px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--academic-border);
  background: var(--academic-primary);
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  box-shadow: var(--shadow-soft);
  white-space: nowrap;
}

.compare-entry b {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.compare-entry:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

/* ===== 欢迎页 ===== */
.welcome-screen {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  text-align: center;
}

.welcome-spark {
  font-size: 48px;
  color: var(--academic-primary);
  margin-bottom: 4px;
}

.welcome-screen h2 {
  font-size: 20px;
  color: var(--academic-text-main);
  margin: 0;
  font-weight: 600;
}

.welcome-screen p {
  color: var(--academic-text-muted);
  margin: 0;
  max-width: 380px;
  line-height: var(--line-academic);
}

.chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.chat-input-fixed { flex-shrink: 0; }

/* ★ 会话切换 loading */
.switch-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--academic-text-muted);
  font-size: 14px;
}

.loading-pulse {
  width: 32px;
  height: 32px;
  border: 3px solid var(--academic-border);
  border-top-color: var(--academic-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ===== ReadingDrawer ===== */
.reading-drawer {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 48%;
  min-width: 400px;
  background: var(--academic-panel);
  border-left: 1px solid var(--academic-border);
  display: flex;
  flex-direction: column;
  z-index: 30;
  box-shadow: var(--shadow-float);
}

.drawer-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--academic-border);
  background: var(--academic-canvas);
}

.drawer-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--academic-text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.drawer-tabs { display: flex; gap: 2px; }

.drawer-tabs button {
  padding: 6px 14px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.drawer-tabs button:hover { color: var(--academic-text-main); background: rgba(0,0,0,0.04); }

.drawer-tabs button.active {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  font-weight: 600;
}

.drawer-close {
  width: 32px; height: 32px;
  border-radius: 8px; border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  display: grid; place-items: center;
  transition: all 0.15s;
}

.drawer-close:hover { background: rgba(0,0,0,0.05); color: var(--academic-text-main); }

.drawer-body { flex: 1; overflow: hidden; background: var(--academic-panel); }
.pdf-container { height: 100%; overflow: auto; }
.pdf-error { padding: 40px; text-align: center; color: var(--danger); }
.pdf-loading { display: grid; place-items: center; height: 100%; color: var(--academic-text-muted); }

.drawer-slide-enter-active { transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.drawer-slide-leave-active { transition: transform 0.25s cubic-bezier(0.5, 0, 0.75, 0); }
.drawer-slide-enter-from,
.drawer-slide-leave-to { transform: translateX(100%); }
</style>
