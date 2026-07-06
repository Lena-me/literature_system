<!-- frontend/src/layouts/AdminLayout.vue -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminApi } from '@/api/admin'
import '@/styles/admin.css'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const isExpanded = ref(true)
const mobileOpen = ref(false)
const systemPaused = ref(false)
const pauseLoading = ref(false)

const navItems = [
  { label: '运维总览', path: '/admin', exact: true, icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  { label: '用户与配额', path: '/admin/users', exact: false, icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857 M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857 M7 20H2v-2a3 3 0 015.356-1.857 M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0 M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' },
  { label: '模型配置', path: '/admin/models', exact: false, icon: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z' },
  { label: '解析任务', path: '/admin/tasks', exact: false, icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
  { label: '风控与审计', path: '/admin/ops', exact: false, icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
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
          <svg class="brand-logo" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--admin-accent, #2563eb)" stroke-width="1.6">
            <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
            <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
          </svg>
        </button>
        <span class="brand-text">管理控制台</span>
      </div>

      <nav class="nav-list">
        <button
          v-for="item in navItems"
          :key="item.label"
          :title="!isExpanded ? item.label : ''"
          class="nav-item"
          :class="{ active: isActive(item) }"
          @click="go(item.path)"
        >
          <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path :d="item.icon" />
          </svg>
          <span class="nav-label">{{ item.label }}</span>
          <div v-if="!isExpanded" class="nav-tooltip">{{ item.label }}</div>
        </button>
      </nav>

      <div class="sidebar-footer">
        <button class="logout-btn" @click="logout">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
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
      <header class="admin-page-header">
        <div class="header-primary">
          <button class="mobile-menu-btn" @click="mobileOpen = !mobileOpen">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
              <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <div>
            <h1 class="admin-page-header__title">{{ pageTitle }}</h1>
          </div>
        </div>

        <div class="admin-page-header__actions">
          <button
            class="pause-btn"
            :class="{ paused: systemPaused }"
            :disabled="pauseLoading"
            @click="toggleSystemPause"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
            </svg>
            <span class="pause-label">{{ systemPaused ? '恢复运行' : '全局暂停' }}</span>
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
  background: var(--admin-bg-subtle, #f8fafc);
}

.admin-sidebar {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--admin-bg-sidebar, #f9fbff);
  border-right: 1px solid var(--admin-border, #e2e8f0);
  z-index: 50;
  width: 64px;
  min-width: 64px;
  transition: width 0.25s ease, min-width 0.25s ease, transform 0.25s ease;
  overflow: hidden;
}

.admin-sidebar.expanded {
  width: 220px;
  min-width: 220px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 1rem 0.75rem;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}

.brand-toggle {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  cursor: pointer;
  flex-shrink: 0;
  padding: 0;
}

.brand-toggle:hover {
  background: var(--admin-accent-soft, #eff6ff);
}

.brand-text {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--academic-text-main, #0f172a);
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.05s;
}

.admin-sidebar.expanded .brand-text {
  opacity: 1;
}

.nav-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem 0.5rem;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  width: 100%;
  height: 38px;
  padding: 0 0.75rem;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  color: #64748b;
  position: relative;
  border-left: 2px solid transparent;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.nav-item:hover {
  background: var(--admin-accent-soft, #eff6ff);
  color: var(--admin-accent, #2563eb);
}

.nav-item.active {
  background: var(--admin-accent-soft, #eff6ff);
  color: var(--admin-accent-hover, #1d4ed8);
  font-weight: 600;
  border-left-color: var(--admin-accent, #2563eb);
}

.nav-icon {
  flex-shrink: 0;
}

.nav-label {
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.05s;
}

.admin-sidebar.expanded .nav-label {
  opacity: 1;
}

.sidebar-footer {
  padding: 0.75rem 0.5rem;
  border-top: 1px solid #e5e7eb;
}

.logout-btn {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  width: 100%;
  height: 38px;
  padding: 0 0.75rem;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  color: #64748b;
  position: relative;
  transition: background 0.15s ease, color 0.15s ease;
}

.logout-btn:hover {
  background: #fef2f2;
  color: #dc2626;
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
  background: #0f172a;
  color: #fff;
  font-size: 12px;
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
  background: var(--admin-bg, #fff);
}

.header-primary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.pause-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  height: 32px;
  padding: 0 0.75rem;
  border: 1px solid #fecaca;
  background: #fff;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  color: #dc2626;
  font-family: inherit;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.pause-btn:hover:not(:disabled) {
  background: #fef2f2;
}

.pause-btn.paused {
  border-color: #bbf7d0;
  color: #059669;
}

.pause-btn.paused:hover:not(:disabled) {
  background: #f0fdf4;
}

.pause-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.mobile-menu-btn {
  display: none;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  color: #64748b;
}

.admin-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--admin-bg, #fff);
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
    width: 220px !important;
    min-width: 220px !important;
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
    background: rgba(15, 23, 42, 0.24);
    z-index: 40;
  }

  .mobile-menu-btn {
    display: inline-flex;
  }

  .pause-label {
    display: none;
  }

  .admin-page-header {
    padding: 1rem 1.25rem;
  }
}
</style>
