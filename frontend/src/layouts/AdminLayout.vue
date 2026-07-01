<!-- frontend\src\layouts\AdminLayout.vue -->

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const isExpanded = ref(true)

function toggleSidebar() {
  isExpanded.value = !isExpanded.value
}

function logout() {
  auth.logout()
  router.push('/admin/login')
}

function go(path: string) {
  router.push(path)
}
</script>

<template>
  <main class="admin-layout">
    <aside class="admin-sidebar" :class="{ expanded: isExpanded }">
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
          v-for="item in [
            { label: '运维总览', path: '/admin', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
            { label: '用户与配额', path: '/admin/users', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857 M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857 M7 20H2v-2a3 3 0 015.356-1.857 M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0 M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' },
            { label: '模型配置', path: '/admin/models', icon: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z' },
            { label: '解析任务', path: '/admin/tasks', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
            { label: '向量库与日志', path: '/admin/ops', icon: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z' },
          ]"
          :key="item.label"
          :title="!isExpanded ? item.label : ''"
          class="nav-item"
          :class="{ active: $route.path === item.path }"
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

    <section class="admin-content">
      <router-view />
    </section>
  </main>
</template>

<style scoped>
.admin-layout {
  display: flex;
  height: 100vh;
  width: 100%;
  background: var(--academic-canvas);
  overflow: hidden;
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
  transition: width 0.3s ease, min-width 0.3s ease;
  overflow: hidden;
}

.admin-sidebar.expanded {
  width: 260px;
  min-width: 260px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 10px;
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
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.3px;
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
  justify-content: flex-start;
  gap: 10px;
  width: 100%;
  height: 44px;
  padding: 0 12px;
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

.nav-item:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.nav-item.active {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  font-weight: 600;
}

.nav-item.secondary {
  color: var(--academic-text-muted);
}

.nav-item.secondary:hover {
  color: var(--academic-text-body);
  background: rgba(0, 0, 0, 0.04);
}

.nav-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
}

.nav-label {
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.admin-sidebar.expanded .nav-label {
  opacity: 1;
}

.nav-divider {
  height: 1px;
  background: var(--academic-border);
  margin: 8px 8px;
}


.sidebar-footer {
  padding: 8px 4px;
  border-top: 1px solid var(--academic-border);
  flex-shrink: 0;
}

.logout-btn {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px; /* 和nav-item统一gap 10px */
  width: 100%;
  height: 44px;
  padding: 0 12px; /* 和上方菜单统一左内边距12px，图标对齐 */
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  font-size: 13px;
  color: var(--danger);
  position: relative;
}

.logout-btn svg {
  flex-shrink: 0;
}

.logout-btn:hover {
  background: rgba(239, 68, 68, 0.08);
}

.logout-label {
  white-space: nowrap;
  opacity: 0;
  visibility: hidden;
  display: none; /* 默认收起状态彻底移除占位 */
  transition: opacity 0.2s ease 0.1s, visibility 0.2s ease 0.1s;
}
/* 仅展开时恢复显示 */
.admin-sidebar.expanded .logout-label {
  display: inline-block;
  opacity: 1;
  visibility: visible;
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

.nav-item:hover .nav-tooltip {
  opacity: 1;
}
.logout-btn:hover .nav-tooltip {
  opacity: 1;
}

.admin-content {
  flex: 1;
  min-width: 0;
  height: 100vh;
  padding: 24px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}
</style>