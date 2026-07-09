<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useNotebookStore } from '@/stores/notebook'

const router = useRouter()
const route = useRoute()
const notebook = useNotebookStore()

const isExpanded = ref(true)
const searchQuery = ref('')
const editingId = ref<number | null>(null)
const editTitle = ref('')

function toggleSidebar() {
  isExpanded.value = !isExpanded.value
}

onMounted(() => {
  notebook.loadSessions()
})

async function handleNewSession() {
  await notebook.createSession()
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

function go(path: string) {
  router.push(path)
}

function isActive(path: string): boolean {
  if (path === '/dashboard') return route.path === '/dashboard' || route.path === '/'
  if (path === '/notebook') return route.path.startsWith('/notebook')
  return route.path === path
}

const primaryNavItems = [
  { label: '探索中心', path: '/dashboard', icon: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z' },
  { label: '文献资产', path: '/library', icon: 'M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z' },
  { label: '多维对比', path: '/compare', icon: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01' },
  { label: '知识图谱', path: '/graph', icon: 'M12 20a8 8 0 100-16 8 8 0 000 16z M3.5 12h17 M12 3.5a15 15 0 010 17' },
  { label: '研读报告', path: '/reports', icon: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z M14 2v6h6 M16 13H8 M16 17H8' },
]

const profileNavItem = {
  label: '个人档案',
  path: '/profile',
  icon: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2 M12 7a4 4 0 100-8 4 4 0 000 8z',
}
</script>

<template>
  <aside class="unified-sidebar" :class="{ expanded: isExpanded }">
    <div class="sidebar-header">
      <button class="brand-toggle" @click="toggleSidebar" :title="isExpanded ? '收起侧边栏' : '展开侧边栏'">
        <svg class="brand-logo" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--sidebar-accent)" stroke-width="1.8">
          <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
        </svg>
      </button>
      <span class="brand-text">睿识</span>
    </div>

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

    <nav class="primary-nav" aria-label="核心研究模块">
      <button
        v-for="item in primaryNavItems"
        :key="item.label"
        :title="!isExpanded ? item.label : ''"
        class="nav-item nav-item--primary"
        :class="{ active: isActive(item.path) }"
        @click="go(item.path)"
      >
        <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path :d="item.icon" />
        </svg>
        <span class="nav-label">{{ item.label }}</span>
        <div v-if="!isExpanded" class="nav-tooltip">{{ item.label }}</div>
      </button>
    </nav>

    <section class="history-section">
      <div v-show="isExpanded" class="search-box">
        <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索历史对话..."
          class="search-input"
        />
      </div>

      <div class="session-list slim-scroll">
        <div v-show="isExpanded" class="section-label section-label--history">近期研究记录</div>

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
              <div v-else class="session-title" @dblclick.stop="startRename(s.id, s.title)">
                {{ s.title }}
              </div>
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

        <div v-if="isExpanded && filteredSessions().length === 0" class="empty">
          <p>{{ searchQuery ? '无匹配记录' : '暂无研究记录' }}</p>
        </div>
      </div>
    </section>

    <footer class="profile-footer">
      <button
        :title="!isExpanded ? profileNavItem.label : ''"
        class="nav-item nav-item--profile"
        :class="{ active: isActive(profileNavItem.path) }"
        @click="go(profileNavItem.path)"
      >
        <svg class="nav-icon nav-icon--profile" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
          <path :d="profileNavItem.icon" />
        </svg>
        <span class="nav-label">{{ profileNavItem.label }}</span>
        <div v-if="!isExpanded" class="nav-tooltip">{{ profileNavItem.label }}</div>
      </button>
    </footer>
  </aside>
</template>

<style scoped>
.unified-sidebar {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-sidebar);
  border-right: none;
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

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 16px 8px;
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
  background: rgba(15, 23, 42, 0.05);
}

.brand-logo {
  flex-shrink: 0;
  pointer-events: none;
}

.brand-text {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--sidebar-text-main);
  white-space: nowrap;
  opacity: 0;
  width: 0;
  overflow: hidden;
  transition: opacity 0.2s ease 0.1s, width 0.2s ease;
}

.unified-sidebar.expanded .brand-text {
  opacity: 1;
  width: auto;
}

.cta-wrap {
  padding: 8px 12px 10px;
  flex-shrink: 0;
  position: relative;
}

.cta-btn {
  width: 100%;
  padding: 11px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--sidebar-border);
  background: rgba(255, 255, 255, 0.72);
  color: var(--sidebar-text-main);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: background 0.2s, color 0.2s, box-shadow 0.2s, border-color 0.2s;
  white-space: nowrap;
  box-shadow: none;
  font-family: inherit;
}

.cta-btn:hover {
  background: #ffffff;
  border-color: rgba(59, 130, 246, 0.45);
  color: var(--sidebar-text-main);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
}

.cta-btn:active {
  transform: scale(0.98);
}

.cta-label {
  opacity: 0;
  width: 0;
  overflow: hidden;
  transition: opacity 0.2s ease 0.1s, width 0.2s ease;
}

.unified-sidebar.expanded .cta-label {
  opacity: 1;
  width: auto;
}

.primary-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px 12px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--sidebar-border);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  margin-bottom: 0;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
  position: relative;
  text-align: left;
  overflow: hidden;
}

.nav-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 0;
  border-radius: 0 4px 4px 0;
  background: transparent;
  transition: height 0.2s ease, background 0.2s ease;
}

.nav-item--primary {
  font-size: 14px;
  font-weight: 500;
  color: var(--sidebar-text-muted);
}

.nav-item--primary .nav-icon {
  color: var(--sidebar-text-muted);
  transition: transform 0.2s ease, color 0.2s ease;
}

.nav-item--primary:hover {
  background: rgba(255, 255, 255, 0.4);
  color: var(--sidebar-text-main);
}

.nav-item--primary:hover .nav-icon {
  color: var(--sidebar-text-main);
}

.nav-item--primary.active {
  background: #ffffff;
  color: var(--sidebar-text-main);
  font-weight: 600;
  box-shadow:
    0 4px 12px rgba(15, 23, 42, 0.08),
    0 1px 3px rgba(15, 23, 42, 0.04);
  border-color: rgba(226, 232, 240, 0.6);
}

.nav-item--primary.active::before {
  height: 60%;
  background: var(--academic-primary);
}

.nav-item--primary.active .nav-icon {
  color: var(--academic-primary);
  transform: scale(1.05);
}

.nav-item--profile {
  font-size: 13px;
  font-weight: 500;
  color: var(--sidebar-text-muted);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  min-height: 36px;
  overflow: visible;
}

.nav-item--profile::before {
  display: none;
}

.nav-item--profile .nav-icon {
  width: 14px;
  height: 14px;
  display: block;
  overflow: visible;
  color: var(--sidebar-text-muted);
  transition: color 0.2s ease;
}

.nav-item--profile:hover {
  background: rgba(255, 255, 255, 0.35);
  color: var(--sidebar-text-main);
}

.nav-item--profile:hover .nav-icon {
  color: var(--sidebar-text-main);
}

.nav-item--profile.active {
  color: var(--sidebar-text-main);
  background: rgba(255, 255, 255, 0.72);
  border-color: rgba(226, 232, 240, 0.45);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
}

.nav-item--profile.active .nav-icon {
  color: var(--academic-primary);
}

.nav-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
}

.nav-label {
  white-space: nowrap;
  opacity: 0;
  width: 0;
  overflow: hidden;
  transition: opacity 0.2s ease 0.1s, width 0.2s ease;
}

.unified-sidebar.expanded .nav-label {
  opacity: 1;
  width: auto;
}

/* 折叠态：图标居中展示，避免文字占位把图标挤出可视区 */
.unified-sidebar:not(.expanded) .sidebar-header {
  justify-content: center;
  padding: 16px 8px 8px;
}

.unified-sidebar:not(.expanded) .cta-wrap {
  display: flex;
  justify-content: center;
  padding: 4px 8px 8px;
}

.unified-sidebar:not(.expanded) .cta-btn {
  width: 40px;
  height: 40px;
  padding: 0;
  gap: 0;
}

.unified-sidebar:not(.expanded) .primary-nav {
  align-items: center;
  padding: 4px 6px 10px;
}

.unified-sidebar:not(.expanded) .nav-item {
  width: 40px;
  height: 40px;
  padding: 0;
  justify-content: center;
  overflow: visible;
}

.unified-sidebar:not(.expanded) .nav-item--primary.active::before {
  height: 50%;
}

.unified-sidebar:not(.expanded) .profile-footer {
  display: flex;
  justify-content: center;
  padding: 10px 8px 14px;
}

.unified-sidebar:not(.expanded) .nav-item--profile {
  width: 40px;
  height: 40px;
  padding: 0;
  justify-content: center;
}

.unified-sidebar:not(.expanded) .session-item {
  justify-content: center;
  padding: 8px 6px;
}

.history-section {
  flex: 1;
  min-height: 0;
  max-height: 40%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.search-box {
  display: flex;
  align-items: center;
  position: relative;
  padding: 10px 12px 6px;
  flex-shrink: 0;
}

.search-icon {
  position: absolute;
  left: 24px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--sidebar-text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 8px 12px 8px 36px;
  line-height: normal;
  border-radius: 10px;
  border: none;
  background: var(--sidebar-bg-subtle);
  color: var(--sidebar-text-main);
  font-size: 12px;
  outline: none;
  transition: background 0.2s;
  box-sizing: border-box;
}

.search-input::placeholder {
  color: var(--sidebar-text-muted);
}

.search-input:focus {
  background: rgba(255, 255, 255, 0.9);
}

.session-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 8px 8px;
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}

.session-list:hover {
  scrollbar-color: rgba(148, 163, 184, 0.35) transparent;
}

.session-list::-webkit-scrollbar {
  width: 4px;
}

.session-list::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 4px;
}

.session-list:hover::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.35);
}

.section-label {
  padding: 8px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.section-label--history {
  color: var(--sidebar-text-muted);
  font-weight: 500;
  font-size: 11px;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 7px 10px 7px 12px;
  margin: 1px 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  gap: 6px;
  min-width: 0;
  position: relative;
}

.session-item:hover {
  background: var(--selected-bg-subtle);
}

.session-item.active {
  background: var(--selected-bg);
}

.session-item.active .session-title {
  color: var(--sidebar-text-main);
  font-weight: 500;
}

.session-content {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 12px;
  font-weight: 400;
  color: var(--sidebar-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.45;
}

.session-dot {
  flex-shrink: 0;
  color: var(--sidebar-text-muted);
  margin: 0 auto;
}

.delete-btn {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--sidebar-text-muted);
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
  border: 1px solid rgba(59, 130, 246, 0.5);
  background: #ffffff;
  color: var(--sidebar-text-main);
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
}

.empty {
  padding: 16px 12px;
  text-align: center;
  color: var(--sidebar-text-muted);
  font-size: 12px;
}

.profile-footer {
  margin-top: auto;
  padding: 10px 8px 14px;
  flex-shrink: 0;
  border-top: 1px solid var(--sidebar-border);
}

.nav-tooltip {
  position: fixed;
  left: 70px;
  padding: 6px 10px;
  background: var(--sidebar-text-main);
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
.nav-item:hover .nav-tooltip {
  opacity: 1;
}

.cta-tooltip {
  top: 90px;
}
</style>
