<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useNotebookStore } from '@/stores/notebook'
import { papersApi } from '@/api/papers'
import type { Paper } from '@/types/domain'

const notebook = useNotebookStore()
const emit = defineEmits<{ chipClick: [paperId: number] }>()

// —— 文献选择器 ——
const showPicker = ref(false)
const paperSearchKeyword = ref('')
const availablePapers = ref<Paper[]>([])
const selectedPaperIds = ref<number[]>([])
const pickerLoading = ref(false)

async function openPicker() {
  selectedPaperIds.value = []
  paperSearchKeyword.value = ''
  await loadAvailablePapers()
  showPicker.value = true
}

async function loadAvailablePapers() {
  pickerLoading.value = true
  try {
    availablePapers.value = await papersApi.list({ keyword: paperSearchKeyword.value, limit: 30 })
  } finally {
    pickerLoading.value = false
  }
}

function togglePaperSelection(id: number) {
  const idx = selectedPaperIds.value.indexOf(id)
  if (idx >= 0) {
    selectedPaperIds.value.splice(idx, 1)
  } else {
    selectedPaperIds.value.push(id)
  }
}

async function confirmAddPapers() {
  if (selectedPaperIds.value.length === 0) {
    showPicker.value = false
    return
  }
  await notebook.addSources(selectedPaperIds.value)
  showPicker.value = false
  ElMessage.success(`已添加 ${selectedPaperIds.value.length} 篇文献`)
}

function removePaperFromSession(paperId: number) {
  notebook.removeSource(paperId)
}

function handleChipClick(paperId: number) {
  emit('chipClick', paperId)
}

defineExpose({ openPicker })
</script>

<template>
  <div class="source-bar">
    <!-- 文献筹码卡片 -->
    <div class="chips">
      <button
        v-for="paper in notebook.activeSources"
        :key="paper.id"
        class="chip"
        :class="{ 'parsed': paper.parse_status === 'completed' }"
        @click="handleChipClick(paper.id)"
        :title="`${paper.title}${paper.parse_status !== 'completed' ? ' (解析中...)' : ''}`"
      >
        <span class="chip-icon">📄</span>
        <span class="chip-text">{{ paper.title || paper.original_filename }}</span>
        <span v-if="paper.parse_status !== 'completed'" class="chip-status">{{ paper.parse_status }}</span>
        <button class="chip-remove" @click.stop="removePaperFromSession(paper.id)" title="移出会话">×</button>
      </button>

      <!-- 添加按钮 -->
      <button class="chip add-chip" @click="openPicker">
        <span class="plus">+</span>
        <span>添加文献</span>
      </button>
    </div>

    <!-- 文献数量提示 -->
    <div v-if="notebook.activeSources.length === 0" class="no-sources">
      <span>暂无挂载文献 — 你可以直接对话或添加文献以获得精准回答</span>
    </div>

    <!-- 文献选择弹窗 -->
    <Teleport to="body">
      <div v-if="showPicker" class="picker-overlay" @click.self="showPicker = false">
        <div class="picker-dialog">
          <div class="picker-head">
            <b>选择要挂载的文献</b>
            <button class="close-btn" @click="showPicker = false">✕</button>
          </div>

          <div class="picker-search">
            <input
              v-model="paperSearchKeyword"
              type="text"
              placeholder="搜索文献标题..."
              class="search-input"
              @keyup.enter="loadAvailablePapers"
            />
            <button class="search-btn" @click="loadAvailablePapers">搜索</button>
          </div>

          <div class="picker-list slim-scroll">
            <div v-if="pickerLoading" class="picker-loading">加载中...</div>
            <div
              v-for="paper in availablePapers"
              :key="paper.id"
              class="picker-item"
              :class="{ selected: selectedPaperIds.includes(paper.id) }"
              @click="togglePaperSelection(paper.id)"
            >
              <div class="check-box">
                <span v-if="selectedPaperIds.includes(paper.id)">✓</span>
              </div>
              <div class="paper-info">
                <div class="paper-title">{{ paper.title || paper.original_filename }}</div>
                <div class="paper-meta">
                  <span v-if="paper.authors">
                    {{ Array.isArray(paper.authors) ? paper.authors.slice(0, 2).join(', ') : paper.authors }}
                  </span>
                  <span>{{ paper.parse_status }}</span>
                </div>
              </div>
            </div>
            <div v-if="!pickerLoading && availablePapers.length === 0" class="picker-empty">
              {{ paperSearchKeyword ? '无匹配文献' : '暂无可用文献' }}
            </div>
          </div>

          <div class="picker-actions">
            <span class="selected-count">已选 {{ selectedPaperIds.length }} 篇</span>
            <button class="confirm-btn" :disabled="selectedPaperIds.length === 0" @click="confirmAddPapers">
              确认添加
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.source-bar {
  padding: 12px 20px;
  border-bottom: 1px solid var(--academic-border);
  min-height: 56px;
  display: flex;
  align-items: center;
  background: var(--academic-canvas);
}

.chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chip {
  padding: 6px 10px 6px 10px;
  border-radius: 20px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
  white-space: nowrap;
  max-width: 220px;
  box-shadow: var(--shadow-soft);
}

.chip:hover {
  background: var(--academic-primary-light);
  border-color: var(--academic-primary);
  color: var(--academic-primary);
}

.chip.parsed {
  border-color: #C7D2FE;
}

.chip-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.chip-text {
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.chip-status {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(245, 158, 11, 0.1);
  color: #D97706;
  flex-shrink: 0;
}

.chip-remove {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: var(--academic-border);
  color: var(--academic-text-muted);
  cursor: pointer;
  font-size: 12px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  transition: all 0.15s;
  padding: 0;
}

.chip:hover .chip-remove {
  background: rgba(239, 68, 68, 0.12);
  color: var(--danger);
}

.add-chip {
  border-style: dashed;
  border-color: var(--academic-border-hover);
  color: var(--academic-text-muted);
  background: transparent;
  font-weight: 500;
  padding: 6px 14px;
  box-shadow: none;
}

.add-chip:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border-color: var(--academic-primary);
}

.plus {
  font-size: 18px;
  font-weight: 300;
}

.no-sources {
  color: var(--academic-text-muted);
  font-size: 13px;
  padding: 4px 0;
}

/* ===== 选择器弹窗 ===== */
.picker-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.3);
  display: grid;
  place-items: center;
  z-index: 100;
  backdrop-filter: blur(4px);
}

.picker-dialog {
  width: 520px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  border-radius: 22px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  overflow: hidden;
  box-shadow: var(--shadow-float);
}

.picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid var(--academic-border);
}

.picker-head b {
  color: var(--academic-text-main);
  font-size: 16px;
}

.close-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-muted);
  cursor: pointer;
  font-size: 18px;
  display: grid;
  place-items: center;
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border-color: var(--academic-primary);
}

.picker-search {
  display: flex;
  gap: 8px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--academic-border);
}

.picker-search .search-input {
  flex: 1;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 14px;
  outline: none;
}

.picker-search .search-input:focus {
  border-color: var(--academic-primary);
  background: var(--academic-panel);
}

.search-btn {
  padding: 10px 18px;
  border-radius: 12px;
  border: 1px solid var(--academic-primary);
  background: var(--academic-panel);
  color: var(--academic-primary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.2s;
}

.search-btn:hover {
  background: var(--academic-primary);
  color: #fff;
}

.picker-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 16px;
  max-height: 350px;
}

.picker-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;
  margin: 2px 0;
}

.picker-item:hover {
  background: var(--academic-canvas);
}

.picker-item.selected {
  background: var(--academic-primary-light);
}

.check-box {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 2px solid var(--academic-border);
  display: grid;
  place-items: center;
  font-size: 13px;
  color: var(--academic-primary);
  flex-shrink: 0;
}

.picker-item.selected .check-box {
  border-color: var(--academic-primary);
  background: var(--academic-primary);
  color: #fff;
}

.paper-info {
  flex: 1;
  min-width: 0;
}

.paper-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--academic-text-body);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.paper-meta {
  font-size: 11px;
  color: var(--academic-text-muted);
  margin-top: 2px;
  display: flex;
  gap: 8px;
}

.picker-loading,
.picker-empty {
  text-align: center;
  padding: 30px;
  color: var(--academic-text-muted);
  font-size: 14px;
}

.picker-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-top: 1px solid var(--academic-border);
}

.selected-count {
  font-size: 13px;
  color: var(--academic-text-muted);
}

.confirm-btn {
  padding: 10px 22px;
  border-radius: 12px;
  border: none;
  background: var(--academic-primary);
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.confirm-btn:hover {
  background: var(--academic-primary-hover);
}

.confirm-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
