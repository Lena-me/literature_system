<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useNotebookStore } from '@/stores/notebook'
import PaperLibraryPicker from '@/components/notebook/PaperLibraryPicker.vue'
import { useSessionPaperUpload } from '@/composables/useSessionPaperUpload'
import { parseStatusClass, parseStatusLabel } from '@/utils/parseStatus'

const notebook = useNotebookStore()
const emit = defineEmits<{
  filesUploaded: [paperIds: number[]]
  paperClick: [paperId: number]
}>()

const pickerRef = ref<InstanceType<typeof PaperLibraryPicker> | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const inputText = ref(notebook.draftInput)

const { uploading, uploadChip, onFileInputChange } = useSessionPaperUpload()

const showActionMenu = ref(false)
const actionBtnRef = ref<HTMLButtonElement | null>(null)
const popoverStyle = ref({ top: '0px', left: '0px' })
const showMention = ref(false)
const mentionQuery = ref('')
const mentionPosition = ref({ top: 0, left: 0 })
const filteredMentionPapers = ref<{ id: number; title: string }[]>([])

watch(inputText, val => notebook.saveDraft(val))

watch(
  () => notebook.editingMessageId,
  id => {
    if (id) {
      inputText.value = notebook.draftInput
      nextTick(autoResize)
    }
  },
)

function updatePopoverPosition() {
  const btn = actionBtnRef.value
  if (!btn) return
  const rect = btn.getBoundingClientRect()
  popoverStyle.value = {
    top: `${rect.top - 8}px`,
    left: `${rect.left}px`,
  }
}

function toggleActionMenu() {
  showActionMenu.value = !showActionMenu.value
  if (showActionMenu.value) nextTick(updatePopoverPosition)
}

function closeActionMenu() {
  showActionMenu.value = false
}

function triggerFileUpload() {
  closeActionMenu()
  fileInputRef.value?.click()
}

function triggerLibraryPicker() {
  closeActionMenu()
  pickerRef.value?.openPicker()
}

async function handleFilesSelected(e: Event) {
  const uploadedIds = await onFileInputChange(e)
  if (uploadedIds.length > 0) emit('filesUploaded', uploadedIds)
}

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
    const left = Math.min(currentLine.length * charWidth + 20, 300)
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
    if (!showMention.value && !showActionMenu.value) send()
  }
}

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

function onBlurPopover() {
  setTimeout(() => {
    if (!actionBtnRef.value?.matches(':focus-within')) showActionMenu.value = false
  }, 150)
}

function removeAttachment(paperId: number) {
  notebook.removeSource(paperId)
}

function openPaper(paperId: number) {
  emit('paperClick', paperId)
}
</script>

<template>
  <div class="input-dock">
    <div class="dock-shell">
      <!-- 附件胶囊区：仅展示已挂载文献 -->
      <div v-if="notebook.activeSources.length || uploadChip" class="attachment-strip">
        <div class="attachment-scroll">
          <Transition name="chip-fade">
            <span v-if="uploadChip" class="attach-pill upload-pill">
              <span class="chip-spinner" />
              <span class="pill-text">{{ uploadChip.filename }}</span>
            </span>
          </Transition>

          <button
            v-for="paper in notebook.activeSources"
            :key="paper.id"
            type="button"
            class="attach-pill"
            :title="`${paper.title || paper.original_filename} · ${parseStatusLabel(paper.parse_status)}`"
            @click="openPaper(paper.id)"
          >
            <span
              class="status-dot"
              :class="parseStatusClass(paper.parse_status)"
              :title="parseStatusLabel(paper.parse_status)"
            />
            <span class="pill-text">{{ paper.title || paper.original_filename }}</span>
            <span
              role="button"
              tabindex="0"
              class="pill-remove"
              title="移出会话"
              @click.stop="removeAttachment(paper.id)"
              @keydown.enter.stop.prevent="removeAttachment(paper.id)"
              @keydown.space.stop.prevent="removeAttachment(paper.id)"
            >
              ×
            </span>
          </button>
        </div>
      </div>

      <div class="input-row">
        <Transition name="mention-fade">
          <div
            v-if="showMention && filteredMentionPapers.length"
            class="mention-menu"
            :style="{ bottom: '100%', left: mentionPosition.left + 'px' }"
          >
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

        <button
          ref="actionBtnRef"
          type="button"
          class="plus-btn"
          title="添加文献"
          @click="toggleActionMenu"
          @blur="onBlurPopover"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>

        <Teleport to="body">
          <Transition name="popover-fade">
            <div
              v-if="showActionMenu"
              class="action-popover"
              :style="popoverStyle"
              @mouseleave="closeActionMenu"
            >
              <button type="button" class="action-item" :disabled="uploading" @mousedown.prevent @click="triggerFileUpload">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                <span>上传本地文献</span>
              </button>
              <button type="button" class="action-item" @mousedown.prevent @click="triggerLibraryPicker">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
                <span>从文献库选择</span>
              </button>
            </div>
          </Transition>
        </Teleport>

        <input
          ref="fileInputRef"
          type="file"
          hidden
          accept=".pdf"
          multiple
          @change="handleFilesSelected"
        />

        <textarea
          ref="textareaRef"
          v-model="inputText"
          class="chat-textarea"
          placeholder="输入消息，或使用 @ 引用知识库已有文献"
          rows="1"
          @input="autoResize(); onInput($event)"
          @keydown="onKeydown"
        />

        <button
          v-if="notebook.isStreaming"
          type="button"
          class="stop-btn"
          title="停止生成"
          @click="notebook.stopStreaming()"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <rect x="7" y="7" width="10" height="10" rx="1.5" />
          </svg>
        </button>
        <button
          v-else
          type="button"
          class="send-btn"
          :class="{ loading: uploading }"
          :disabled="!inputText.trim() || uploading"
          @click="send"
        >
          <span class="send-arrow">↑</span>
        </button>
      </div>
    </div>

    <PaperLibraryPicker ref="pickerRef" />
  </div>
</template>

<style scoped>
.input-dock {
  flex-shrink: 0;
  padding: 0;
  background: transparent;
  position: sticky;
  bottom: 0;
  z-index: 100;
}

.upload-status-chip {
  display: none;
}

.chip-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(166, 124, 82, 0.25);
  border-top-color: var(--academic-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.chip-tag {
  font-size: 11px;
  background: rgba(166, 124, 82, 0.1);
  padding: 2px 8px;
  border-radius: 8px;
  font-weight: 600;
}

.dock-shell {
  max-width: 860px;
  margin: 0 auto;
  border-radius: 20px 20px 0 0;
  border: 1px solid var(--border-light);
  border-bottom: none;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.04);
  overflow: visible;
  transition: all 0.3s ease;
}

.dock-shell:focus-within {
  background: rgba(255, 255, 255, 0.95);
  border-color: rgba(196, 154, 108, 0.45);
  box-shadow: 0 -10px 40px rgba(166, 124, 82, 0.08);
}

.attachment-strip {
  padding: 10px 12px 0;
  background: transparent;
  border-bottom: 1px dashed var(--border-light);
  border-radius: 20px 20px 0 0;
  overflow: hidden;
}

.attach-pill.upload-pill {
  border: 1px solid var(--border-light);
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.attach-pill.upload-pill .chip-spinner {
  width: 8px;
  height: 8px;
  border: 2px solid rgba(166, 124, 82, 0.25);
  border-top-color: var(--academic-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.attachment-scroll {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 10px;
  scrollbar-width: thin;
}

.attach-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  max-width: 220px;
  padding: 6px 10px 6px 12px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-canvas);
  font-size: 12px;
  color: var(--text-primary);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  transition: border-color 0.12s, background 0.12s;
}

.attach-pill:hover {
  border-color: rgba(196, 154, 108, 0.4);
  background: var(--academic-primary-light);
}

.pill-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.pill-remove {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  transition: all 0.12s;
}

.pill-remove:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.input-row {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 0 0 20px 20px;
  background: var(--academic-panel);
}

.plus-btn {
  width: 36px;
  height: 36px;
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
  margin-bottom: 2px;
  transition: all 0.2s;
}

.plus-btn:hover {
  background: var(--academic-canvas);
  color: var(--academic-text-main);
  border-color: var(--academic-primary);
  border-style: solid;
}

.action-popover {
  position: fixed;
  transform: translateY(-100%);
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 16px;
  padding: 6px;
  min-width: 200px;
  z-index: 4000;
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

.action-item:hover:not(:disabled) {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.action-item:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.chat-textarea {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  padding: 8px 4px;
  resize: none;
  line-height: 1.55;
  color: var(--academic-text-body);
  font-size: 15px;
  min-height: 24px;
  max-height: 160px;
  font-family: inherit;
}

.chat-textarea::placeholder {
  color: var(--academic-text-muted);
}

.send-btn,
.stop-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0;
  margin-bottom: 2px;
  transition: all 0.2s;
}

.send-btn {
  background: var(--academic-primary);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
}

.send-btn:hover:not(:disabled) {
  background: var(--academic-primary-hover);
  transform: scale(1.05);
}

.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.stop-btn {
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  color: var(--text-secondary);
}

.stop-btn:hover {
  background: var(--bg-canvas);
  border-color: rgba(196, 154, 108, 0.4);
  color: var(--text-primary);
}

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

.chip-fade-enter-active,
.chip-fade-leave-active,
.popover-fade-enter-active,
.popover-fade-leave-active,
.mention-fade-enter-active,
.mention-fade-leave-active {
  transition: all 0.15s ease;
}

.chip-fade-enter-from,
.chip-fade-leave-to,
.popover-fade-enter-from,
.popover-fade-leave-to,
.mention-fade-enter-from,
.mention-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
