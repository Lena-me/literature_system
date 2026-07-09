<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useNotebookStore } from '@/stores/notebook'
import { ElMessage } from 'element-plus'
import { useSessionPaperUpload } from '@/composables/useSessionPaperUpload'
import type { RelatedVisual, Source } from '@/types/domain'
import ContextIsland from '@/components/notebook/ContextIsland.vue'
import SessionTitleBar from '@/components/notebook/SessionTitleBar.vue'
import MessageList from '@/components/notebook/MessageList.vue'
import ChatInput from '@/components/notebook/ChatInput.vue'
import PaperReader from '@/components/reader/PaperReader.vue'
import { extractHighlightText } from '@/utils/sourceNavigation'
import SuggestedQuestions from '@/components/notebook/SuggestedQuestions.vue'

const route = useRoute()
const notebook = useNotebookStore()
const { uploadLocalFiles } = useSessionPaperUpload()

const readerRef = ref<InstanceType<typeof PaperReader> | null>(null)
const readerPaper = ref<{ id: number; title: string } | null>(null)
const pendingReaderNav = ref<{ source?: Source; visual?: RelatedVisual } | null>(null)

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

  const uploadedIds = await uploadLocalFiles(files)

  if (uploadedIds.length > 0) {
    ElMessage.success(`已上传并挂载 ${uploadedIds.length} 篇文献`)
  }
}

function onChatInputFilesUploaded(_ids: number[]) {
  // Files already added to session inside ChatInput
}

function resolvePaperTitle(paperId: number) {
  return notebook.activeSources.find(p => p.id === paperId)?.title || '文献阅读'
}

async function openReader(
  paperId: number,
  options?: {
    page?: number
    highlight?: string
    source?: Source
    visual?: RelatedVisual
  },
) {
  readerPaper.value = { id: paperId, title: resolvePaperTitle(paperId) }
  await nextTick()
  await readerRef.value?.open(options)
}

function handleReaderClose() {
  readerPaper.value = null
  pendingReaderNav.value = null
  notebook.closeReadingDrawer()
}

watch(
  () => [
    notebook.isReadingDrawerOpen,
    notebook.currentReadingPaperId,
    notebook.currentReadingPage,
    notebook.currentReadingHighlight,
  ] as const,
  async ([open, paperId, page, highlight]) => {
    if (!open || !paperId) return
    const nav = pendingReaderNav.value
    pendingReaderNav.value = null
    await openReader(paperId, {
      page: page || 1,
      highlight: highlight || undefined,
      source: nav?.source,
      visual: nav?.visual,
    })
  },
)

async function onSourceClick(source: Source) {
  pendingReaderNav.value = { source }
  notebook.openReadingDrawer(
    source.paper_id,
    source.page_number,
    extractHighlightText(source),
  )
}

async function onVisualClick(source: Source, visual: RelatedVisual) {
  pendingReaderNav.value = { visual }
  notebook.openReadingDrawer(source.paper_id, visual.page_number ?? undefined, '')
}

async function onChipClick(paperId: number) {
  pendingReaderNav.value = null
  notebook.openReadingDrawer(paperId)
}

onMounted(async () => {
  const sessionId = route.params.id ? Number(route.params.id) : null
  if (sessionId) {
    await notebook.switchSession(sessionId)
  }
})
</script>

<template>
  <div
    class="notebook-view"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
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

    <div v-if="!notebook.activeSessionId" class="welcome-screen">
      <div class="welcome-spark">✦</div>
      <h2>欢迎使用探索中心</h2>
      <p>在左侧选择一条研究记录开始探索，或者上传文献获得智能分析。</p>
    </div>

    <template v-else>
      <div class="chat-stage">
        <div class="chat-body">
          <div class="chat-header">
            <SessionTitleBar />
            <ContextIsland @paper-click="onChipClick" />
          </div>
          <div v-if="notebook.isSwitchingSession" class="switch-loading">
            <span class="loading-pulse"></span>
            <span>加载对话中...</span>
          </div>
          <template v-else>
            <SuggestedQuestions />
            <MessageList @source-click="onSourceClick" @visual-click="onVisualClick" />
          </template>
        </div>
        <ChatInput
          class="chat-input-dock"
          @files-uploaded="onChatInputFilesUploaded"
          @paper-click="onChipClick"
        />
      </div>
    </template>

    <PaperReader
      v-if="readerPaper"
      ref="readerRef"
      :paper-id="readerPaper.id"
      :paper-title="readerPaper.title"
      @close="handleReaderClose"
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
}

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

.chat-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  --notebook-content-max-width: 860px;
  --notebook-content-gutter: 16px;
}

.chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  position: relative;
}

.chat-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 20px 6px;
  min-height: 36px;
}

.chat-input-dock {
  flex-shrink: 0;
}

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
</style>
