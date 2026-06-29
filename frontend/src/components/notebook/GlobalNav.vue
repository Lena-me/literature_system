<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const isExpanded = ref(false)

function toggleSidebar() {
  isExpanded.value = !isExpanded.value
}

const menuItems = [
  {
    label: '主页概览',
    path: '/dashboard',
    icon: `<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>`,
  },
  {
    label: '会话工作台',
    path: '/notebook',
    icon: `<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>`,
  },
  {
    label: '文献库',
    path: '/library',
    icon: `<path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>`,
  },
  {
    label: '研读报告',
    path: '/reports',
    icon: `<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>`,
  },
  {
    label: '学习档案',
    path: '/archive',
    icon: `<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>`,
  },
  {
    label: '个人档案',
    path: '/profile',
    icon: `<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>`,
  },
]

function isActive(path: string): boolean {
  if (path === '/dashboard') return route.path === '/dashboard' || route.path === '/'
  if (path === '/notebook') return route.path.startsWith('/notebook')
  return route.path === path
}

function go(path: string) {
  router.push(path)
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <aside class="global-nav" :class="{ expanded: isExpanded }">
    <!-- 顶部 -->
    <div class="nav-header">
      <button class="menu-toggle" @click="toggleSidebar" :title="isExpanded ? '收起' : '展开菜单'">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      <div class="brand-area">
        <svg class="brand-logo" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--academic-primary)" stroke-width="1.8">
          <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
        </svg>
        <span class="brand-text">文献智能解析</span>
      </div>
    </div>

    <!-- 菜单 -->
    <nav class="nav-items">
      <button
        v-for="item in menuItems"
        :key="item.label"
        :title="!isExpanded ? item.label : ''"
        class="nav-item"
        :class="{ active: isActive(item.path) }"
        @click="go(item.path)"
      >
        <svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="item.icon" />
        <span class="nav-label">{{ item.label }}</span>
        <div v-if="!isExpanded" class="nav-tooltip">{{ item.label }}</div>
      </button>
    </nav>

    <!-- 用户 -->
    <div class="user-area">
      <button class="user-btn" @click="go('/profile')" :title="!isExpanded ? '个人档案' : ''">
        <span class="user-avatar">{{ auth.user?.username?.slice(0, 1)?.toUpperCase() }}</span>
        <span class="user-name">{{ auth.user?.name || auth.user?.username }}</span>
      </button>
      <div v-if="!isExpanded" class="user-tooltip">{{ auth.user?.name || auth.user?.username }}</div>
    </div>
  </aside>
</template>

<style scoped>
.global-nav {
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

.global-nav.expanded {
  width: 256px;
  min-width: 256px;
}

.nav-header {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 60px;
  padding: 0 12px;
  border-bottom: 1px solid var(--academic-border);
  flex-shrink: 0;
}

.menu-toggle {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
  padding: 0;
}

.menu-toggle:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--academic-text-main);
}

.brand-area { display: flex; align-items: center; gap: 10px; overflow: hidden; }
.brand-logo { flex-shrink: 0; }

.brand-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--academic-text-main);
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.global-nav.expanded .brand-text { opacity: 1; }

.nav-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  padding: 12px 8px;
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  font-size: 14px;
  position: relative;
  font-family: inherit;
  color: var(--academic-text-muted);
}

.nav-item:hover { background: rgba(0, 0, 0, 0.04); color: var(--academic-text-main); }

.nav-item.active {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  font-weight: 600;
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: -4px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: var(--academic-primary);
}

.nav-icon { flex-shrink: 0; width: 20px; height: 20px; }

.nav-label {
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
  font-weight: 500;
}

.global-nav.expanded .nav-label { opacity: 1; }

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

.nav-item:hover .nav-tooltip { opacity: 1; }

.user-area {
  padding: 10px;
  border-top: 1px solid var(--academic-border);
  flex-shrink: 0;
  position: relative;
}

.user-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  color: var(--academic-text-body);
}

.user-btn:hover { background: rgba(0, 0, 0, 0.04); }

.user-avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: var(--academic-primary);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  flex-shrink: 0;
}

.user-name {
  font-size: 13px;
  color: var(--academic-text-body);
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s ease 0.1s;
}

.global-nav.expanded .user-name { opacity: 1; }

.user-tooltip {
  position: fixed;
  left: 70px;
  bottom: 20px;
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

.user-btn:hover + .user-tooltip,
.user-area:hover .user-tooltip { opacity: 1; }
</style>
