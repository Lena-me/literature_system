<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useNotebookStore } from '@/stores/notebook'
import PaperLibraryPicker from '@/components/notebook/PaperLibraryPicker.vue'
import { useSessionPaperUpload } from '@/composables/useSessionPaperUpload'
import { parseStatusClass, parseStatusLabel } from '@/utils/parseStatus'

const emit = defineEmits<{ paperClick: [paperId: number] }>()

const notebook = useNotebookStore()
const pickerRef = ref<InstanceType<typeof PaperLibraryPicker> | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const showPanel = ref(false)
const islandRef = ref<HTMLElement | null>(null)

const { uploading, uploadChip, onFileInputChange } = useSessionPaperUpload()

const sourceCount = computed(() => notebook.activeSources.length)
const indicatorLabel = computed(() => {
  const n = sourceCount.value
  if (n === 0) return '未挂载文献'
  return `${n} 篇文献引用中`
})

function togglePanel() {
  showPanel.value = !showPanel.value
}

function closePanel() {
  showPanel.value = false
}

function openLibraryPicker() {
  closePanel()
  pickerRef.value?.openPicker()
}

function triggerLocalUpload() {
  fileInputRef.value?.click()
}

async function handleFilesSelected(e: Event) {
  await onFileInputChange(e)
}

function removePaper(paperId: number) {
  notebook.removeSource(paperId)
}

function onPaperClick(paperId: number) {
  emit('paperClick', paperId)
}

function onDocumentClick(e: MouseEvent) {
  if (!showPanel.value) return
  const target = e.target as Node
  if (islandRef.value?.contains(target)) return
  closePanel()
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))
</script>

<template>
  <div ref="islandRef" class="context-island">
    <button
      type="button"
      class="island-trigger"
      :class="{ active: showPanel, empty: sourceCount === 0 }"
      @click.stop="togglePanel"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
      <span>{{ indicatorLabel }}</span>
    </button>

    <Transition name="panel-fade">
      <div v-if="showPanel" class="island-panel" @click.stop>
        <div class="panel-head">
          <span class="panel-title">会话文献</span>
          <span class="panel-count">{{ sourceCount }} 篇</span>
        </div>

        <div v-if="sourceCount === 0" class="panel-empty">
          <p>当前会话尚未挂载文献</p>
          <p class="panel-hint">添加文献后，AI 将基于文献内容回答</p>
        </div>

        <div v-else class="panel-list slim-scroll">
          <div
            v-for="paper in notebook.activeSources"
            :key="paper.id"
            class="paper-card"
          >
            <button
              type="button"
              class="paper-main"
              :title="`${paper.title || paper.original_filename} · ${parseStatusLabel(paper.parse_status)}`"
              @click="onPaperClick(paper.id)"
            >
              <span
                class="status-dot"
                :class="parseStatusClass(paper.parse_status)"
                :title="parseStatusLabel(paper.parse_status)"
              />
              <span class="paper-text">
                <span class="paper-name">{{ paper.title || paper.original_filename }}</span>
              </span>
            </button>
            <button
              type="button"
              class="paper-remove"
              title="移出会话"
              @click="removePaper(paper.id)"
            >
              ×
            </button>
          </div>
        </div>

        <div v-if="uploadChip" class="panel-upload">
          <span class="upload-spinner" />
          <span>{{ uploadChip.filename }}</span>
        </div>

        <div class="panel-footer">
          <button type="button" class="add-btn primary" :disabled="uploading" @click="triggerLocalUpload">
            ↑ 上传本地文献
          </button>
          <button type="button" class="add-btn" @click="openLibraryPicker">
            从文献库添加
          </button>
        </div>
      </div>
    </Transition>

    <input
      ref="fileInputRef"
      type="file"
      hidden
      accept=".pdf"
      multiple
      @change="handleFilesSelected"
    />

    <PaperLibraryPicker ref="pickerRef" />
  </div>
</template>

<style scoped>
.context-island {
  position: relative;
  flex-shrink: 0;
}

.island-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgba(140, 130, 117, 0.35);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
  color: var(--academic-text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(74, 66, 58, 0.06);
  transition: all 0.18s ease;
}

.island-trigger:hover,
.island-trigger.active {
  border-color: rgba(166, 124, 82, 0.35);
  color: var(--academic-primary);
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 4px 14px rgba(166, 124, 82, 0.1);
}

.island-trigger.empty {
  border-style: dashed;
}

.island-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 320px;
  max-height: min(420px, 55vh);
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-surface);
  box-shadow: var(--shadow-float);
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-light);
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--academic-text-main);
}

.panel-count {
  font-size: 11px;
  color: var(--academic-text-muted);
  background: var(--academic-canvas);
  padding: 2px 8px;
  border-radius: 999px;
}

.panel-empty {
  padding: 24px 16px;
  text-align: center;
}

.panel-empty p {
  margin: 0;
  font-size: 13px;
  color: var(--academic-text-muted);
}

.panel-hint {
  margin-top: 6px !important;
  font-size: 12px !important;
  opacity: 0.85;
}

.panel-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.paper-card {
  display: flex;
  align-items: stretch;
  gap: 4px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-canvas);
  overflow: hidden;
}

.paper-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 10px 10px 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.paper-main:hover {
  background: var(--academic-primary-light);
}

.paper-main .status-dot {
  margin-top: 5px;
}

.paper-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.paper-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--academic-text-body);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.paper-remove {
  width: 36px;
  flex-shrink: 0;
  border: none;
  border-left: 1px solid var(--border-light);
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 16px;
  cursor: pointer;
  transition: all 0.12s;
}

.paper-remove:hover {
  background: rgba(239, 68, 68, 0.08);
  color: #ef4444;
}

.panel-footer {
  padding: 10px 12px;
  border-top: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel-upload {
  margin: 0 12px 8px;
  padding: 8px 12px;
  border-radius: var(--radius-lg);
  background: var(--academic-primary-light);
  border: 1px solid var(--border-light);
  font-size: 12px;
  color: var(--academic-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.upload-spinner {
  width: 8px;
  height: 8px;
  border: 2px solid rgba(166, 124, 82, 0.25);
  border-top-color: var(--academic-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.add-btn {
  width: 100%;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px dashed var(--academic-border-hover);
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.add-btn.primary {
  border-style: solid;
  border-color: rgba(166, 124, 82, 0.35);
  color: var(--academic-primary);
  background: var(--academic-primary-light);
}

.add-btn:hover:not(:disabled) {
  border-color: var(--academic-primary);
  color: var(--academic-primary);
  background: var(--academic-primary-light);
}

.add-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.panel-fade-enter-active,
.panel-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.panel-fade-enter-from,
.panel-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
