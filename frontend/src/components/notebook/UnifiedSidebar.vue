<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useNotebookStore } from '@/stores/notebook'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const notebook = useNotebookStore()
const auth = useAuthStore()

// ========== 展开/折叠（点击 Logo 书本图标切换） ==========
const isExpanded = ref(true)

function toggleSidebar() {
  isExpanded.value = !isExpanded.value
}

// ========== 搜索 ==========
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

// ========== 导航（底部工具栏 + 顶栏图标） ==========
function go(path: string) {
  router.push(path)
}

function isActive(path: string): boolean {
  if (path === '/dashboard') return route.path === '/dashboard' || route.path === '/'
  if (path === '/notebook') return route.path.startsWith('/notebook')
  return route.path === path
}
</script>

<template>
  <aside class="unified-sidebar" :class="{ expanded: isExpanded }">
    <!-- ========== Header: Logo（点击书本折叠/展开） ========== -->
    <div class="sidebar-header">
      <button class="brand-toggle" @click="toggleSidebar" :title="isExpanded ? '收起侧边栏' : '展开侧边栏'">
        <svg class="brand-logo" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--academic-primary)" stroke-width="1.8">
          <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
        </svg>
      </button>
      <span class="brand-text">文献智能解析</span>
    </div>

    <!-- ========== CTA 主按钮 ========== -->
    <div class="cta-wrap">
      <button class="cta-btn" @click="handleNewSession" :title="!isExpanded ? '发起新研究' : ''">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        <span class="cta-label">发起新研究</span>
      </button>
      <div v-if="!isExpanded" class="nav-tooltip cta-tooltip">发起新研究</div>
    </div>

    <!-- ========== 搜索框 ========== -->
    <div v-show="isExpanded" class="search-box">
      <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索历史对话..."
        class="search-input"
      />
    </div>

    <!-- ========== 历史记录区 ========== -->
    <div class="session-list slim-scroll">
      <div class="section-label">最近</div>

      <div
        v-for="s in filteredSessions()"
        :key="s.id"
        class="session-item"
        :class="{ active: s.id === notebook.activeSessionId }"
        :title="!isExpanded ? s.title : ''"
        @click="handleSelectSession(s.id)"
      >
        <template v-if="isExpanded">
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
          <button class="delete-btn" title="删除会话" @click.stop="handleDelete(s.id)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
          </button>
        </template>
        <template v-else>
          <svg class="session-dot" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
        </template>
        <div v-if="!isExpanded" class="nav-tooltip">{{ s.title }}</div>
      </div>

      <div v-if="filteredSessions().length === 0" class="empty">
        <p>{{ searchQuery ? '无匹配会话' : '暂无会话，点击上方按钮创建' }}</p>
      </div>
    </div>

    <!-- ========== 底部工具栏 ========== -->
    <div class="bottom-toolbar">
      <button
        v-for="item in [
          { label: '文献库', path: '/library', icon: 'M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z' },
          { label: '研读报告', path: '/reports', icon: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z M14 2v6h6 M16 13H8 M16 17H8' },
          { label: '知识图谱', path: '/graph', icon: 'M12 20a8 8 0 100-16 8 8 0 000 16z M3.5 12h17 M12 3.5a15 15 0 010 17' },
          { label: '学习档案', path: '/archive', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2 M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2 M9 14l2 2 4-4' },
          { label: '个人档案', path: '/profile', icon: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2 M12 7a4 4 0 100-8 4 4 0 000 8z' },
        ]"
        :key="item.label"
        :title="!isExpanded ? item.label : ''"
        class="toolbar-item"
        :class="{ active: isActive(item.path) }"
        @click="go(item.path)"
      >
        <svg class="toolbar-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path :d="item.icon" />
        </svg>
        <span class="toolbar-label">{{ item.label }}</span>
        <div v-if="!isExpanded" class="nav-tooltip">{{ item.label }}</div>
      </button>
    </div>
  </aside>
</template>

<style scoped>
/* ========== 整体容器 ========== */
.unified-sidebar {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--academic-canvas);
  border-right: 1px solid var(--academic-border);
  z-index: 50;
  width: 64px;
  min-width: 64px;
  transition: width 0.3s ease, min-width 0.3s ease;
  overflow: hidden;
}

.unified-sidebar.expanded {
  width: 280px;
  min-width: 280px;
}

/* ========== Logo Header ========== */
.sidebar-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--academic-border);
  flex-shrink: 0;
}

.brand-toggle {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  cursor: pointer;
  flex-shrink: 0;
  padding: 0;
  transition: background 0.15s;
}

.brand-toggle:hover {
  background: rgba(0, 0, 0, 0.05);
}

.brand-logo {
  flex-shrink: 0;
  pointer-events: none;
}

.brand-text {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--academic-text-main);
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.unified-sidebar.expanded .brand-text { opacity: 1; }

/* ========== CTA 主按钮 ========== */
.cta-wrap {
  padding: 12px;
  flex-shrink: 0;
  position: relative;
}

.cta-btn {
  width: 100%;
  padding: 11px 10px;
  border-radius: 999px;
  border: none;
  background: var(--academic-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
  font-family: inherit;
}

.cta-btn:hover {
  background: var(--academic-primary-hover);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
  transform: translateY(-1px);
}

.cta-btn:active {
  transform: scale(0.97);
}

.cta-label {
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.unified-sidebar.expanded .cta-label { opacity: 1; }

/* ========== 搜索框 ========== */
.search-box {
  display: flex;
  align-items: center;
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
  padding: 8px 12px 8px 36px;
  line-height: normal;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
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
}

/* ========== 历史记录区 ========== */
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
  position: relative;
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

.preview { display: inline; }

.session-dot {
  flex-shrink: 0;
  color: var(--academic-text-muted);
  margin: 0 auto;
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

.session-item:hover .delete-btn { opacity: 1; }
.delete-btn:hover { background: rgba(239, 68, 68, 0.1); color: var(--danger); }

.edit-row { padding: 2px 0; }

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

/* ========== 底部工具栏 ========== */
.bottom-toolbar {
  padding: 8px;
  border-top: 1px solid var(--academic-border);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toolbar-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 9px 12px;
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  font-size: 13px;
  color: var(--academic-text-muted);
  position: relative;
}

.toolbar-item:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.toolbar-item.active {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  font-weight: 600;
}

.toolbar-icon { flex-shrink: 0; width: 18px; height: 18px; }

.toolbar-label {
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.unified-sidebar.expanded .toolbar-label { opacity: 1; }

/* ========== Tooltip ========== */
.nav-tooltip {
  position: fixed;
  left: 70px;
  padding: 6px 10px;
  background: var(--academic-text-main);
  color: #fff;
  font-size: 12px;
  border-radius: 6px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 1000;
}

.session-item:hover .nav-tooltip,
.cta-wrap:hover .nav-tooltip,
.toolbar-item:hover .nav-tooltip {
  opacity: 1;
}

.cta-tooltip {
  top: 90px;
}
</style>
