<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/papers'
import { useNotebookStore } from '@/stores/notebook'
import { featuresApi } from '@/api/features'

const router = useRouter()
const auth = useAuthStore()
const paperStore = usePaperStore()
const notebook = useNotebookStore()
const user = auth.user!

const greetingTime = () => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '上午好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

const paperCount = ref(0)
const parsedCount = ref(0)
const sessionCount = ref(0)
const hotTopics = ref<string[]>([])

onMounted(async () => {
  await Promise.all([
    paperStore.load(),
    notebook.loadSessions(),
  ])

  paperCount.value = paperStore.list.length
  parsedCount.value = paperStore.list.filter(p => p.parse_status === 'completed').length
  sessionCount.value = notebook.sessions.length

  try {
    const hotspots = await featuresApi.hotspots()
    hotTopics.value = (hotspots as any)?.keywords || (hotspots as any)?.data?.keywords || []
  } catch { /* ignore */ }
})

function quickActions(action: string) {
  switch (action) {
    case 'new-session':
      notebook.createSession('新研究').then(s => {
        router.push(`/notebook/session/${s.id}`)
      })
      break
    case 'upload':
      router.push('/library')
      break
    case 'reports':
      router.push('/reports')
      break
    case 'compare':
      router.push('/compare')
      break
    case 'graph':
      router.push('/graph')
      break
  }
}
</script>

<template>
  <div class="dashboard-page slim-scroll">
    <!-- 欢迎区 -->
    <div class="welcome-section">
      <div class="greeting">
        <h1>{{ user.name || user.username }}，{{ greetingTime() }}</h1>
        <p>你的 AI 研读工作台已就绪</p>
      </div>
      <div class="avatar-lg">{{ user.username?.slice(0, 1)?.toUpperCase() }}</div>
    </div>

    <!-- 数据概览卡片 -->
    <div class="stats-row">
      <div class="stat-card" @click="quickActions('library')">
        <div class="stat-icon upload">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </div>
        <div class="stat-body">
          <b>{{ paperCount }}</b>
          <span>已上传文献</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon parsed">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <div class="stat-body">
          <b>{{ parsedCount }}</b>
          <span>已解析就绪</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon sessions">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
        </div>
        <div class="stat-body">
          <b>{{ sessionCount }}</b>
          <span>研究会话</span>
        </div>
      </div>
    </div>

    <!-- 快捷操作 -->
    <h3>快捷操作</h3>
    <div class="quick-actions">
      <button class="qa-card" @click="quickActions('new-session')">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        <span>发起新研究</span>
      </button>
      <button class="qa-card" @click="quickActions('upload')">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        <span>上传文献</span>
      </button>
      <button class="qa-card" @click="quickActions('compare')">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>
        <span>文献对比</span>
      </button>
      <button class="qa-card" @click="quickActions('reports')">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <span>查看报告</span>
      </button>
      <button class="qa-card" @click="quickActions('graph')">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20a8 8 0 100-16 8 8 0 000 16z M3.5 12h17 M12 3.5a15 15 0 010 17"/></svg>
        <span>知识图谱</span>
      </button>
    </div>

    <!-- 热门主题 -->
    <h3 v-if="hotTopics.length">热门研究主题</h3>
    <div v-if="hotTopics.length" class="topic-bar">
      <span v-for="t in hotTopics" :key="t" class="topic-chip">{{ t }}</span>
    </div>
  </div>
</template>

<style scoped>
.dashboard-page {
  height: 100%;
  overflow-y: auto;
  padding: 32px;
  max-width: 800px;
  margin: 0 auto;
  background: var(--academic-canvas);
}

/* ====== 欢迎区 ====== */
.welcome-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 28px;
}

.greeting h1 {
  margin: 0;
  font-size: 28px;
  color: var(--academic-text-main);
  font-weight: 700;
}

.greeting p {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--academic-text-muted);
}

.avatar-lg {
  width: 56px;
  height: 56px;
  border-radius: 18px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--academic-primary), var(--academic-primary-hover));
  color: #fff;
  font-size: 22px;
  font-weight: 800;
}

/* ====== 统计卡片 ====== */
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 28px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border-radius: 18px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: var(--shadow-soft);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-float);
  border-color: var(--academic-primary);
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.stat-icon.upload {
  background: rgba(37, 99, 235, 0.1);
  color: var(--academic-primary);
}

.stat-icon.parsed {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.stat-icon.sessions {
  background: rgba(99, 102, 241, 0.1);
  color: #6366F1;
}

.stat-body b {
  font-size: 22px;
  font-weight: 800;
  color: var(--academic-text-main);
  display: block;
}

.stat-body span {
  font-size: 12px;
  color: var(--academic-text-muted);
}

/* ====== 段落标题 ====== */
h3 {
  font-size: 15px;
  color: var(--academic-text-main);
  font-weight: 600;
  margin: 0 0 14px;
}

/* ====== 快捷操作 ====== */
.quick-actions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 28px;
}

.qa-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  border-radius: 18px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
  box-shadow: var(--shadow-soft);
}

.qa-card:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border-color: var(--academic-primary);
}

/* ====== 热门主题 ====== */
.topic-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.topic-chip {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border: 1px solid rgba(37, 99, 235, 0.15);
  font-weight: 500;
}
</style>
