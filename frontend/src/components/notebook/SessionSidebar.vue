<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useNotebookStore } from '@/stores/notebook'

const notebook = useNotebookStore()
const searchQuery = ref('')
const editingId = ref<number | null>(null)
const editTitle = ref('')

onMounted(() => {
  notebook.loadSessions()
})

async function handleNewSession() {
  await notebook.createSession('新会话')
  ElMessage.success('新会话已创建')
}

async function handleSelectSession(id: number) {
  await notebook.switchSession(id)
}

function startRename(id: number, currentTitle: string) {
  editingId.value = id
  editTitle.value = currentTitle
  nextTick(() => {
    const el = document.querySelector('.inline-title-input') as HTMLInputElement
    el?.focus()
    el?.select()
  })
}

async function finishRename(id: number) {
  if (editTitle.value.trim()) {
    await notebook.renameSession(id, editTitle.value.trim())
  }
  editingId.value = null
}

function cancelRename() {
  editingId.value = null
}

async function handleDelete(id: number) {
  await notebook.deleteSession(id)
  ElMessage.success('会话已删除')
}

const filteredSessions = () => {
  const q = searchQuery.value.toLowerCase().trim()
  if (!q) return notebook.sessions
  return notebook.sessions.filter(s => s.title.toLowerCase().includes(q))
}
</script>

<template>
  <aside class="session-sidebar" :class="{ collapsed: !notebook.isSidebarOpen }">
    <!-- 头部 -->
    <div class="sidebar-head">
      <span class="title">
        <svg class="title-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
        会话
      </span>
      <button class="collapse-btn" @click="notebook.toggleSidebar()" title="收起侧边栏">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
    </div>

    <!-- 新建按钮 -->
    <button class="new-session-btn" @click="handleNewSession">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      <span>发起新研究</span>
    </button>

    <!-- 搜索框 -->
    <div class="search-box">
      <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索历史对话..."
        class="search-input"
      />
    </div>

    <!-- 会话列表 -->
    <div class="session-list slim-scroll">
      <div v-if="notebook.domains.length" class="domain-section">
        <div class="section-label">知识域</div>
        <div v-for="d in notebook.domains" :key="d.id" class="domain-item">{{ d.name }}</div>
      </div>

      <div class="section-label">最近</div>

      <div
        v-for="s in filteredSessions()"
        :key="s.id"
        class="session-item"
        :class="{ active: s.id === notebook.activeSessionId }"
        @click="handleSelectSession(s.id)"
      >
        <div class="session-content">
          <div v-if="editingId === s.id" class="edit-row" @click.stop>
            <input
              v-model="editTitle"
              class="inline-title-input"
              @keyup.enter="finishRename(s.id)"
              @keyup.escape="cancelRename()"
              @blur="finishRename(s.id)"
            />
          </div>
          <template v-else>
            <div class="session-title" @dblclick.stop="startRename(s.id, s.title)">
              {{ s.title }}
            </div>
            <div class="session-meta">
              <span>{{ s.paper_count }} 篇文献</span>
              <span v-if="s.last_message_preview" class="preview"> · {{ s.last_message_preview }}</span>
            </div>
          </template>
        </div>

        <button
          class="delete-btn"
          title="删除会话"
          @click.stop="handleDelete(s.id)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
        </button>
      </div>

      <div v-if="filteredSessions().length === 0" class="empty">
        <p>{{ searchQuery ? '无匹配会话' : '暂无会话，点击上方按钮创建' }}</p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.session-sidebar {
  width: 260px;
  min-width: 260px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--academic-panel);
  border-right: 1px solid var(--academic-border);
  overflow-y: auto;
  overflow-x: hidden;
  transition: width 0.3s ease, min-width 0.3s ease;
  z-index: 40;
}

.session-sidebar.collapsed {
  width: 0;
  min-width: 0;
  border-right: none;
}

.session-sidebar.collapsed > * {
  white-space: nowrap;
  overflow: hidden;
}

/* ====== 头部 ====== */
.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 16px 10px;
  flex-shrink: 0;
}

.title {
  font-size: 15px;
  font-weight: 700;
  color: var(--academic-text-main);
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.title-icon {
  color: var(--academic-text-muted);
}

.collapse-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: all 0.15s;
  flex-shrink: 0;
}

.collapse-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--academic-text-main);
}

/* ====== 新建按钮 ====== */
.new-session-btn {
  margin: 0 12px 12px;
  padding: 10px;
  border-radius: 999px;
  border: none;
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}

.new-session-btn:hover {
  background: #DBEAFE;
}

/* ====== 搜索框 ====== */
.search-box {
  position: relative;
  padding: 0 12px 8px;
  flex-shrink: 0;
}

.search-icon {
  position: absolute;
  left: 24px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--academic-text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 9px 14px 9px 34px;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.search-input::placeholder {
  color: var(--academic-text-muted);
}

.search-input:focus {
  border-color: var(--academic-primary);
  background: var(--academic-panel);
}

/* ====== 会话列表 ====== */
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px 16px;
}

.section-label {
  padding: 10px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 9px 10px;
  margin: 1px 0;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
  gap: 6px;
  min-width: 0;
}

.session-item:hover {
  background: var(--academic-primary-light);
}

.session-item.active {
  background: var(--academic-primary-light);
}

.session-item.active .session-title {
  color: var(--academic-primary);
  font-weight: 600;
}

.session-content {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--academic-text-body);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.session-meta {
  font-size: 11px;
  color: var(--academic-text-muted);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview {
  display: inline;
}

.delete-btn {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  opacity: 0;
  transition: all 0.15s;
  flex-shrink: 0;
  padding: 0;
}

.session-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--danger);
}

.edit-row {
  padding: 2px 0;
}

.inline-title-input {
  width: 100%;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--academic-primary);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}

.empty {
  padding: 30px 16px;
  text-align: center;
  color: var(--academic-text-muted);
  font-size: 13px;
}

.domain-section {
  margin-bottom: 6px;
}

.domain-item {
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  color: var(--academic-text-body);
  cursor: pointer;
  transition: all 0.15s;
}

.domain-item:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}
</style>
