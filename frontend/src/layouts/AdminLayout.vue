<!-- frontend/src/layouts/AdminLayout.vue -->

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminApi } from '@/api/admin'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const isExpanded = ref(true)
const mobileOpen = ref(false)
const searchKeyword = ref('')
const systemPaused = ref(false)
const pauseLoading = ref(false)

const navItems = [
  { label: '运维总览', path: '/admin', exact: true, icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  { label: '用户与配额', path: '/admin/users', exact: false, icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857 M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857 M7 20H2v-2a3 3 0 015.356-1.857 M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0 M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' },
  { label: '模型配置', path: '/admin/models', exact: false, icon: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z' },
  { label: '解析任务', path: '/admin/tasks', exact: false, icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
  { label: '向量库与日志', path: '/admin/ops', exact: false, icon: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z' },
]

const pageTitle = computed(() => {
  const item = navItems.find(n => (n.exact ? route.path === n.path : route.path.startsWith(n.path)))
  return item?.label || '管理控制台'
})

function isActive(item: (typeof navItems)[number]) {
  return item.exact ? route.path === item.path : route.path.startsWith(item.path)
}

function toggleSidebar() {
  isExpanded.value = !isExpanded.value
}

function logout() {
  auth.logout()
  router.push('/admin/login')
}

function go(path: string) {
  mobileOpen.value = false
  router.push(path)
}

function handleSearch() {
  const kw = searchKeyword.value.trim()
  if (!kw) return
  router.push({ path: '/admin/users', query: { keyword: kw } })
}

async function loadPauseState() {
  try {
    const res = await adminApi.systemPauseState()
    systemPaused.value = !!res.paused
  } catch {
    systemPaused.value = false
  }
}

async function toggleSystemPause() {
  const next = !systemPaused.value
  const title = next ? '确认全局暂停系统？' : '确认恢复系统运行？'
  const message = next
    ? '暂停后新任务与部分业务请求将被拦截，请谨慎操作。'
    : '恢复后系统将正常接受新请求。'
  try {
    await ElMessageBox.confirm(message, title, {
      type: 'warning',
      confirmButtonText: next ? '确认暂停' : '确认恢复',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  pauseLoading.value = true
  try {
    const res = await adminApi.setSystemPause(next)
    systemPaused.value = !!res.paused
    ElMessage.success(res.message || (next ? '系统已暂停' : '系统已恢复'))
  } finally {
    pauseLoading.value = false
  }
}

onMounted(loadPauseState)
</script>

<template>
  <div class="admin-layout">
    <div v-if="mobileOpen" class="sidebar-overlay" @click="mobileOpen = false" />

    <aside class="admin-sidebar" :class="{ expanded: isExpanded, 'mobile-open': mobileOpen }">
      <div class="sidebar-header">
        <button class="brand-toggle" @click="toggleSidebar" :title="isExpanded ? '收起侧边栏' : '展开侧边栏'">
          <svg class="brand-logo" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--academic-primary)" stroke-width="1.8">
            <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
            <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
          </svg>
        </button>
        <span class="brand-text">管理控制台</span>
      </div>

      <div class="nav-list">
        <button
          v-for="item in navItems"
          :key="item.label"
          :title="!isExpanded ? item.label : ''"
          class="nav-item"
          :class="{ active: isActive(item) }"
          @click="go(item.path)"
        >
          <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path :d="item.icon" />
          </svg>
          <span class="nav-label">{{ item.label }}</span>
          <div v-if="!isExpanded" class="nav-tooltip">{{ item.label }}</div>
        </button>
      </div>

      <div class="sidebar-footer">
        <button class="logout-btn" @click="logout">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          <span class="logout-label">退出登录</span>
          <div v-if="!isExpanded" class="nav-tooltip">退出登录</div>
        </button>
      </div>
    </aside>

    <div class="admin-main">
      <header class="admin-header">
        <div class="header-left">
          <button class="mobile-menu-btn" @click="mobileOpen = !mobileOpen">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <h2 class="header-title">{{ pageTitle }}</h2>
        </div>

        <div class="header-center">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索用户（用户名 / ID / 手机号）"
            clearable
            class="global-search"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </template>
          </el-input>
        </div>

        <div class="header-right">
          <button
            class="emergency-btn"
            :class="{ paused: systemPaused }"
            :disabled="pauseLoading"
            @click="toggleSystemPause"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
            </svg>
            {{ systemPaused ? '恢复系统运行' : '全局熔断 / 暂停系统' }}
          </button>
        </div>
      </header>

      <main class="admin-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.admin-layout {
  display: flex;
  height: 100vh;
  width: 100%;
  overflow: hidden;
  background: #eef0f3;
}

.admin-sidebar {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--academic-panel);
  border-right: 1px solid var(--academic-border);
  z-index: 50;
  width: 64px;
  min-width: 64px;
  transition: width 0.3s ease, min-width 0.3s ease, transform 0.3s ease;
  overflow: hidden;
}

.admin-sidebar.expanded {
  width: 240px;
  min-width: 240px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 10px;
  border-bottom: 1px solid var(--academic-border);
  flex-shrink: 0;
}

.brand-toggle {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  cursor: pointer;
  flex-shrink: 0;
  padding: 0;
}

.brand-toggle:hover {
  background: rgba(0, 0, 0, 0.05);
}

.brand-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--academic-text-main);
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.admin-sidebar.expanded .brand-text {
  opacity: 1;
}

.nav-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  font-size: 13px;
  color: var(--academic-text-muted);
  position: relative;
}

.nav-item:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.nav-item.active {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  font-weight: 600;
  box-shadow: inset 3px 0 0 var(--academic-primary);
}

.nav-icon {
  flex-shrink: 0;
}

.nav-label {
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.admin-sidebar.expanded .nav-label {
  opacity: 1;
}

.sidebar-footer {
  padding: 8px 4px;
  border-top: 1px solid var(--academic-border);
}

.logout-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  color: var(--danger);
  position: relative;
}

.logout-btn:hover {
  background: rgba(239, 68, 68, 0.08);
}

.logout-label {
  display: none;
  white-space: nowrap;
}

.admin-sidebar.expanded .logout-label {
  display: inline-block;
}

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

.nav-item:hover .nav-tooltip,
.logout-btn:hover .nav-tooltip {
  opacity: 1;
}

.admin-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.admin-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: var(--academic-panel);
  border-bottom: 1px solid var(--academic-border);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 140px;
}

.header-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--academic-text-main);
}

.header-center {
  flex: 1;
  max-width: 420px;
}

.global-search :deep(.el-input__wrapper) {
  border-radius: 8px;
}

.header-right {
  margin-left: auto;
}

.emergency-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  color: #fff;
  background: linear-gradient(135deg, #dc2626, #b91c1c);
  box-shadow: 0 0 0 1px rgba(220, 38, 38, 0.3), 0 4px 14px rgba(220, 38, 38, 0.35);
  animation: pulse-emergency 2s ease-in-out infinite;
}

.emergency-btn.paused {
  background: linear-gradient(135deg, #059669, #047857);
  box-shadow: 0 0 0 1px rgba(5, 150, 105, 0.3), 0 4px 14px rgba(5, 150, 105, 0.25);
  animation: none;
}

.emergency-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

@keyframes pulse-emergency {
  0%, 100% { box-shadow: 0 0 0 1px rgba(220, 38, 38, 0.3), 0 4px 14px rgba(220, 38, 38, 0.35); }
  50% { box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.2), 0 4px 20px rgba(220, 38, 38, 0.5); }
}

.mobile-menu-btn {
  display: none;
  width: 36px;
  height: 36px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  align-items: center;
  justify-content: center;
}

.admin-content {
  flex: 1;
  min-height: 0;
  padding: 16px;
  overflow: auto;
  background: #eef0f3;
  box-sizing: border-box;
}

.sidebar-overlay {
  display: none;
}

@media (max-width: 960px) {
  .admin-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    transform: translateX(-100%);
    width: 240px !important;
    min-width: 240px !important;
  }

  .admin-sidebar.mobile-open {
    transform: translateX(0);
  }

  .admin-sidebar .nav-label,
  .admin-sidebar .brand-text,
  .admin-sidebar .logout-label {
    opacity: 1;
    display: inline-block;
  }

  .sidebar-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.35);
    z-index: 40;
  }

  .mobile-menu-btn {
    display: inline-flex;
  }

  .header-center {
    max-width: none;
    flex: 1;
  }

  .emergency-btn span {
    display: none;
  }
}
</style>
