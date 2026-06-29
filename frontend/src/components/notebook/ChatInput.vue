<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useNotebookStore } from '@/stores/notebook'
import { papersApi } from '@/api/papers'
import { ElMessage } from 'element-plus'

const notebook = useNotebookStore()
const emit = defineEmits<{
  openLibraryPicker: []
  filesUploaded: [paperIds: number[]]
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const inputText = ref(notebook.draftInput)

// —— + 按钮 Popover ——
const showActionMenu = ref(false)
const actionBtnRef = ref<HTMLButtonElement | null>(null)

function toggleActionMenu() {
  showActionMenu.value = !showActionMenu.value
}

function closeActionMenu() {
  showActionMenu.value = false
}

// —— 文件上传 ——
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadChip = ref<{ filename: string; status: string } | null>(null)

function triggerFileUpload() {
  closeActionMenu()
  fileInputRef.value?.click()
}

function triggerLibraryPicker() {
  closeActionMenu()
  emit('openLibraryPicker')
}

async function handleFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return

  const uploadedIds: number[] = []
  for (const file of Array.from(files)) {
    uploading.value = true
    uploadChip.value = { filename: file.name, status: '上传中...' }
    try {
      const paper = await papersApi.upload(file)
      uploadedIds.push(paper.id)
      uploadChip.value = { filename: file.name, status: '解析中...' }
      // 添加到当前会话
      await notebook.addSources([paper.id])
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '上传失败'
      ElMessage.error(`${file.name}: ${msg}`)
    }
  }

  uploading.value = false
  uploadChip.value = null
  input.value = '' // 清空 input 以便重复选同一文件

  if (uploadedIds.length > 0) {
    emit('filesUploaded', uploadedIds)
    ElMessage.success(`已上传并挂载 ${uploadedIds.length} 篇文献`)
  }
}

// —— @ 提及状态 ——
const showMention = ref(false)
const mentionQuery = ref('')
const mentionPosition = ref({ top: 0, left: 0 })
const filteredMentionPapers = ref<{ id: number; title: string }[]>([])

// 同步草稿
watch(inputText, (val) => notebook.saveDraft(val))

// 检测 @ 输入
function onInput(e: Event) {
  const el = e.target as HTMLTextAreaElement
  const text = el.value
  const cursorPos = el.selectionStart || 0
  const textBeforeCursor = text.slice(0, cursorPos)

  const atMatch = textBeforeCursor.match(/@(\S*)$/)
  if (atMatch && atMatch.index !== undefined) {
    mentionQuery.value = atMatch[1] || ''
    const lines = textBeforeCursor.split('\n')
    const currentLine = lines[lines.length - 1] || ''
    const charWidth = 8
    const left = Math.min((currentLine.length) * charWidth + 20, 300)
    mentionPosition.value = { top: -180, left }
    showMention.value = true

    const q = mentionQuery.value.toLowerCase()
    filteredMentionPapers.value = notebook.activeSources
      .filter(p => (p.title || p.original_filename).toLowerCase().includes(q))
      .slice(0, 5)
      .map(p => ({ id: p.id, title: p.title || p.original_filename }))
  } else {
    showMention.value = false
  }
}

// 选中 @ 文献
function selectMention(paperId: number) {
  const el = textareaRef.value
  if (!el) return
  const text = el.value
  const cursorPos = el.selectionStart || 0
  const beforeAt = text.slice(0, cursorPos).replace(/@\S*$/, '')
  const afterCursor = text.slice(el.selectionEnd || cursorPos)
  inputText.value = beforeAt + afterCursor
  showMention.value = false
  nextTick(() => {
    el.focus()
    el.setSelectionRange(beforeAt.length, beforeAt.length)
  })
}

// 发送
async function send() {
  const text = inputText.value.trim()
  if (!text || notebook.isStreaming) return

  const mentionedMatch = text.match(/@(\d+)/g)
  const mentionedIds = mentionedMatch
    ? mentionedMatch.map(m => parseInt(m.slice(1))).filter(id => !isNaN(id))
    : null

  const cleanText = text.replace(/@\d+\s*/g, '').trim()
  if (!cleanText) return

  inputText.value = ''
  await notebook.sendMessage(cleanText, mentionedIds?.length ? mentionedIds : null)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (!showMention.value && !showActionMenu.value) {
      send()
    }
  }
}

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// 点击外部关闭 popover
function onBlurPopover() {
  setTimeout(() => {
    if (!actionBtnRef.value?.matches(':focus-within')) {
      showActionMenu.value = false
    }
  }, 150)
}
</script>

<template>
  <div class="chat-input-bar">
    <!-- 解析状态 Chip -->
    <Transition name="chip-fade">
      <div v-if="uploadChip" class="upload-status-chip">
        <span class="chip-spinner" />
        <span>{{ uploadChip.filename }}</span>
        <span class="chip-tag">{{ uploadChip.status }}</span>
      </div>
    </Transition>

    <div class="input-wrapper">
      <!-- @ 提及弹出菜单 -->
      <Transition name="mention-fade">
        <div v-if="showMention && filteredMentionPapers.length" class="mention-menu" :style="{ bottom: '100%', left: mentionPosition.left + 'px' }">
          <div class="mention-header">选择要 @ 的文献：</div>
          <div
            v-for="paper in filteredMentionPapers"
            :key="paper.id"
            class="mention-item"
            @click="selectMention(paper.id)"
          >
            📄 {{ paper.title }}
          </div>
        </div>
      </Transition>

      <!-- Action Popover 菜单 -->
      <Transition name="popover-fade">
        <div v-if="showActionMenu" class="action-popover" @mouseleave="closeActionMenu">
          <button class="action-item" @click="triggerFileUpload">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            <span>上传本地文献</span>
          </button>
          <button class="action-item" @click="triggerLibraryPicker">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
            <span>从文献库选择</span>
          </button>
        </div>
      </Transition>

      <!-- + 按钮 -->
      <button
        ref="actionBtnRef"
        class="plus-btn"
        @click="toggleActionMenu"
        @blur="onBlurPopover"
        title="添加文献"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
      </button>

      <!-- 隐藏文件输入 -->
      <input
        ref="fileInputRef"
        type="file"
        hidden
        accept=".pdf"
        multiple
        @change="handleFilesSelected"
      />

      <!-- 输入框 -->
      <textarea
        ref="textareaRef"
        v-model="inputText"
        class="chat-textarea"
        placeholder="输入你的科研问题... (Shift+Enter 换行，输入 @ 提及特定文献)"
        :rows="2"
        @input="autoResize(); onInput($event)"
        @keydown="onKeydown"
      />

      <!-- 发送按钮 -->
      <button
        class="send-btn"
        :class="{ loading: notebook.isStreaming || uploading }"
        :disabled="!inputText.trim() || notebook.isStreaming || uploading"
        @click="send"
      >
        <span v-if="notebook.isStreaming" class="spinner" />
        <span v-else class="send-arrow">↑</span>
      </button>
    </div>

    <div class="hint-text">
      {{ notebook.activeSources.length > 0
        ? `基于 ${notebook.activeSources.length} 篇文献回答 · 输入 @ 针对特定文献提问`
        : '直接对话模式 · 点击 ⊕ 上传文献获得更精准回答'
      }}
    </div>
  </div>
</template>

<style scoped>
.chat-input-bar {
  padding: 14px 20px 16px;
  background: var(--academic-panel);
  border-top: 1px solid var(--academic-border);
  flex-shrink: 0;
}

/* ===== 解析状态 Chip ===== */
.upload-status-chip {
  max-width: 780px;
  margin: 0 auto 8px;
  padding: 8px 16px;
  border-radius: 20px;
  background: var(--academic-primary-light);
  border: 1px solid rgba(37, 99, 235, 0.2);
  font-size: 13px;
  color: var(--academic-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.chip-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(37, 99, 235, 0.25);
  border-top-color: var(--academic-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.chip-tag {
  font-size: 11px;
  background: rgba(37, 99, 235, 0.1);
  padding: 2px 8px;
  border-radius: 8px;
  font-weight: 600;
}

.chip-fade-enter-active,
.chip-fade-leave-active {
  transition: all 0.25s ease;
}

.chip-fade-enter-from,
.chip-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* ===== 输入包裹 ===== */
.input-wrapper {
  max-width: 780px;
  margin: 0 auto;
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 8px 12px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 24px;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-shadow: var(--shadow-soft);
}

.input-wrapper:focus-within {
  border-color: var(--academic-primary);
  box-shadow: 0 4px 20px -2px rgba(37, 99, 235, 0.1), var(--shadow-soft);
}

/* ===== + 按钮 ===== */
.plus-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1.5px dashed var(--academic-border-hover);
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0;
  margin-bottom: 4px;
  transition: all 0.2s;
}

.plus-btn:hover {
  background: var(--academic-canvas);
  color: var(--academic-text-main);
  border-color: var(--academic-primary);
  border-style: solid;
}

/* ===== Action Popover ===== */
.action-popover {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 0;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 16px;
  padding: 6px;
  min-width: 200px;
  z-index: 25;
  box-shadow: var(--shadow-float);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.action-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 12px;
  border: none;
  background: transparent;
  color: var(--academic-text-body);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s;
  font-family: inherit;
  text-align: left;
}

.action-item:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.popover-fade-enter-active,
.popover-fade-leave-active {
  transition: all 0.15s ease;
}

.popover-fade-enter-from,
.popover-fade-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.96);
}

/* ===== 输入框 ===== */
.chat-textarea {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  padding: 8px 0;
  resize: none;
  line-height: 1.5;
  color: var(--academic-text-body);
  font-size: 14px;
  min-height: 24px;
  max-height: 160px;
  font-family: inherit;
}

.chat-textarea::placeholder {
  color: var(--academic-text-muted);
}

/* ===== 发送按钮 ===== */
.send-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--academic-primary);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0;
  margin-bottom: 4px;
  font-size: 16px;
  font-weight: 700;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  background: var(--academic-primary-hover);
  transform: scale(1.05);
}

.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.send-btn.loading {
  opacity: 0.6;
}

.send-arrow { line-height: 1; }

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ===== 提示文字 ===== */
.hint-text {
  text-align: center;
  font-size: 11px;
  color: var(--academic-text-muted);
  margin-top: 8px;
}

/* ===== @ 提及菜单 ===== */
.mention-menu {
  position: absolute;
  bottom: calc(100% + 8px);
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 14px;
  padding: 6px;
  min-width: 250px;
  max-width: 320px;
  max-height: 180px;
  overflow-y: auto;
  z-index: 20;
  box-shadow: var(--shadow-float);
}

.mention-header {
  padding: 8px 10px 6px;
  font-size: 11px;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.mention-item {
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 13px;
  color: var(--academic-text-body);
  cursor: pointer;
  transition: all 0.12s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mention-item:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.mention-fade-enter-active,
.mention-fade-leave-active {
  transition: all 0.15s ease;
}

.mention-fade-enter-from,
.mention-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
