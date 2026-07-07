<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/papers'
import { useNotebookStore } from '@/stores/notebook'
import { featuresApi } from '@/api/features'
import BentoActionCard from '@/components/dashboard/BentoActionCard.vue'

const router = useRouter()
const auth = useAuthStore()
const paperStore = usePaperStore()
const notebook = useNotebookStore()
const user = auth.user!

const displayName = computed(() => user.name || user.username)

const greetingInfo = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return { text: '夜深了', emoji: '🌙' }
  if (hour < 12) return { text: '上午好', emoji: '☀️' }
  if (hour < 14) return { text: '中午好', emoji: '🌤️' }
  if (hour < 18) return { text: '下午好', emoji: '🌤️' }
  return { text: '晚上好', emoji: '🌙' }
})

const bannerTone = computed(() => {
  const hour = new Date().getHours()
  return hour < 6 || hour >= 19 ? 'banner-tone-night' : 'banner-tone-day'
})

function sparklinePath(values: number[], w = 72, h = 28): string {
  const arr = values.length ? values : [2, 4, 3, 6, 5, 8, 7]
  const max = Math.max(...arr, 1)
  const min = Math.min(...arr, 0)
  const range = max - min || 1
  return arr
    .map((v, i) => {
      const x = (i / Math.max(arr.length - 1, 1)) * w
      const y = h - ((v - min) / range) * (h - 6) - 3
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
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
  parsedCount.value = paperStore.list.filter(
    p => p.parse_status === 'completed' || p.parse_status === 'indexed',
  ).length
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
    <!-- 沉浸式欢迎 Banner -->
    <section class="welcome-banner" :class="bannerTone">
      <div class="banner-mesh" aria-hidden="true" />

      <div class="welcome-section">
        <div class="greeting">
          <h1>{{ greetingInfo.text }}，{{ displayName }} {{ greetingInfo.emoji }}</h1>
          <p>你的专属科研引擎已就绪，今天想探索什么？</p>
        </div>
        <div class="avatar-wrap">
          <div class="avatar-halo" aria-hidden="true" />
          <div class="avatar-lg">{{ user.username?.slice(0, 1)?.toUpperCase() }}</div>
        </div>
      </div>

      <!-- 毛玻璃数据指标 -->
      <div class="stats-row">
        <div class="stat-card stat-card--primary" @click="quickActions('upload')">
          <div class="stat-card-head">
            <div class="stat-icon upload">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            </div>
            <svg class="stat-sparkline" width="56" height="20" viewBox="0 0 56 20" aria-hidden="true">
              <path :d="sparklinePath([2, 5, 3, 7, 4, 9, paperCount || 6], 56, 20)" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </div>
          <b class="stat-value">{{ paperCount }}</b>
          <span class="stat-label">已上传文献</span>
        </div>

        <div class="stat-card stat-card--success" @click="quickActions('upload')">
          <div class="stat-card-head">
            <div class="stat-icon parsed">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <svg class="stat-sparkline stat-sparkline--muted" width="56" height="20" viewBox="0 0 56 20" aria-hidden="true">
              <path :d="sparklinePath([1, 3, 2, 5, 4, 6, parsedCount || 3], 56, 20)" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </div>
          <b class="stat-value">{{ parsedCount }}</b>
          <span class="stat-label stat-label--live">
            <span class="pulse-dot" aria-hidden="true" />
            已解析就绪
          </span>
        </div>

        <div class="stat-card stat-card--neutral" @click="quickActions('new-session')">
          <div class="stat-card-head">
            <div class="stat-icon sessions">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
            </div>
            <svg class="stat-sparkline stat-sparkline--muted" width="56" height="20" viewBox="0 0 56 20" aria-hidden="true">
              <path :d="sparklinePath([3, 2, 4, 3, 5, 4, sessionCount || 2], 56, 20)" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </div>
          <b class="stat-value stat-value--muted">{{ sessionCount }}</b>
          <span class="stat-label">研究会话</span>
        </div>
      </div>
    </section>

    <!-- Bento 核心能力 -->
    <section class="capabilities-zone">
      <div class="section-head">
        <span class="section-eyebrow">Intelligence Suite</span>
        <h3>知识发现中枢</h3>
        <p>不只是阅读，更是知识的重组</p>
      </div>

      <div class="bento-grid">
      <!-- 主功能：文档解析 -->
      <BentoActionCard
        class="bento-parse"
        size="hero"
        tone="blue"
        badge="核心能力"
        title="智能文档解析"
        subtitle="AI 抽取结构、语义与关键信息"
        @click="quickActions('upload')"
      >
        <template #icon>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="8" y1="13" x2="16" y2="13" />
            <line x1="8" y1="17" x2="13" y2="17" />
          </svg>
        </template>
        <template #decor>
          <div class="decor-docs">
            <div class="doc-sheet doc-a" />
            <div class="doc-sheet doc-b" />
            <div class="doc-scan" />
          </div>
        </template>
      </BentoActionCard>

      <!-- 主功能：知识图谱 -->
      <BentoActionCard
        class="bento-graph"
        size="hero"
        tone="violet"
        badge="撒手锏"
        title="文献知识图谱"
        subtitle="可视化论文关联，发现方法与主题脉络"
        @click="quickActions('graph')"
      >
        <template #icon>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="6" cy="6" r="2.5" />
            <circle cx="18" cy="8" r="2.5" />
            <circle cx="12" cy="18" r="2.5" />
            <circle cx="19" cy="17" r="2" />
            <line x1="8" y1="7" x2="16" y2="8" />
            <line x1="7" y1="8" x2="11" y2="16" />
            <line x1="14" y1="17" x2="17" y2="17" />
          </svg>
        </template>
        <template #decor>
          <svg class="decor-graph" viewBox="0 0 200 200" fill="none">
            <circle cx="48" cy="52" r="10" fill="rgba(99,102,241,0.18)" stroke="rgba(99,102,241,0.35)" stroke-width="1.5" />
            <circle cx="130" cy="40" r="8" fill="rgba(99,102,241,0.12)" stroke="rgba(99,102,241,0.3)" stroke-width="1.5" />
            <circle cx="155" cy="110" r="12" fill="rgba(99,102,241,0.2)" stroke="rgba(99,102,241,0.4)" stroke-width="1.5" />
            <circle cx="72" cy="140" r="9" fill="rgba(99,102,241,0.14)" stroke="rgba(99,102,241,0.32)" stroke-width="1.5" />
            <circle cx="108" cy="88" r="14" fill="rgba(99,102,241,0.25)" stroke="rgba(99,102,241,0.45)" stroke-width="1.5" />
            <line x1="56" y1="58" x2="98" y2="82" stroke="rgba(99,102,241,0.28)" stroke-width="1.5" />
            <line x1="118" y1="86" x2="146" y2="104" stroke="rgba(99,102,241,0.28)" stroke-width="1.5" />
            <line x1="104" y1="98" x2="78" y2="132" stroke="rgba(99,102,241,0.28)" stroke-width="1.5" />
            <line x1="136" y1="46" x2="112" y2="78" stroke="rgba(99,102,241,0.22)" stroke-width="1.5" />
          </svg>
        </template>
      </BentoActionCard>

      <!-- 特色：文献对比（第二行左侧） -->
      <BentoActionCard
        class="bento-compare"
        size="hero"
        tone="emerald"
        badge="特色能力"
        title="多文献智能对比"
        subtitle="跨维度横向分析，快速定位差异与共识"
        @click="quickActions('compare')"
      >
        <template #icon>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
          </svg>
        </template>
        <template #decor>
          <div class="decor-compare">
            <div class="compare-panel panel-a">
              <span class="panel-label">Paper A</span>
              <div class="dim-bar" style="--w: 72%" />
              <div class="dim-bar" style="--w: 55%" />
              <div class="dim-bar" style="--w: 80%" />
            </div>
            <div class="compare-vs">
              <span>VS</span>
            </div>
            <div class="compare-panel panel-b">
              <span class="panel-label">Paper B</span>
              <div class="dim-bar" style="--w: 48%" />
              <div class="dim-bar" style="--w: 78%" />
              <div class="dim-bar" style="--w: 62%" />
            </div>
          </div>
        </template>
      </BentoActionCard>

      <!-- 辅助：发起研究 -->
      <BentoActionCard
        class="bento-session"
        size="compact"
        tone="indigo"
        title="发起新研究"
        subtitle="多轮 AI 问答"
        @click="quickActions('new-session')"
      >
        <template #icon>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </template>
        <template #decor>
          <div class="decor-session">
            <div class="session-bar session-bar-long" />
            <div class="session-bar session-bar-short" />
            <div class="session-input" />
          </div>
        </template>
      </BentoActionCard>

      <BentoActionCard
        class="bento-reports"
        size="compact"
        tone="amber"
        title="研读报告"
        subtitle="一键生成摘要"
        @click="quickActions('reports')"
      >
        <template #icon>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </template>
        <template #decor>
          <div class="decor-reports">
            <div class="report-sheet">
              <div class="report-heading" />
              <div class="report-line w90" />
              <div class="report-line w70" />
              <div class="report-line w55" />
            </div>
          </div>
        </template>
      </BentoActionCard>
      </div>
    </section>

    <!-- 热门主题 -->
    <div v-if="hotTopics.length" class="topics-section">
      <h3 class="topics-title">热门研究主题</h3>
      <div class="topic-bar">
        <span v-for="t in hotTopics" :key="t" class="topic-chip">{{ t }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 16px 24px 20px;
  max-width: 1040px;
  margin: 0 auto;
  background: var(--academic-canvas);
}

/* ====== 沉浸式 Banner ====== */
.welcome-banner {
  position: relative;
  flex-shrink: 0;
  border-radius: 20px;
  padding: 16px 18px 14px;
  margin-bottom: 20px;
  overflow: hidden;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.05),
    0 2px 4px -1px rgba(0, 0, 0, 0.03);
}

.banner-mesh {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.banner-tone-day .banner-mesh {
  background:
    radial-gradient(ellipse 82% 68% at 90% 10%, rgba(56, 189, 248, 0.28), transparent 66%),
    radial-gradient(ellipse 68% 58% at 10% 90%, rgba(99, 102, 241, 0.2), transparent 64%),
    radial-gradient(ellipse 48% 42% at 52% 42%, rgba(37, 99, 235, 0.08), transparent 72%),
    linear-gradient(160deg, #f8fafc 0%, #ffffff 55%, #f8fafc 100%);
}

.banner-tone-night .banner-mesh {
  background:
    radial-gradient(ellipse 78% 62% at 88% 14%, rgba(129, 140, 248, 0.26), transparent 68%),
    radial-gradient(ellipse 64% 54% at 12% 86%, rgba(99, 102, 241, 0.18), transparent 66%),
    radial-gradient(ellipse 44% 38% at 48% 38%, rgba(167, 139, 250, 0.1), transparent 72%),
    linear-gradient(160deg, #f1f5f9 0%, #ffffff 50%, #f8fafc 100%);
}

.welcome-section {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.greeting h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: #0f172a;
}

.greeting p {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.45;
  color: #64748b;
}

.avatar-wrap {
  position: relative;
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.avatar-halo {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 50px;
  height: 50px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.85), rgba(147, 197, 253, 0.55));
  filter: blur(5px);
  opacity: 0.75;
}

.banner-tone-night .avatar-halo {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.7), rgba(167, 139, 250, 0.45));
  opacity: 0.85;
}

.avatar-lg {
  position: relative;
  z-index: 1;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--academic-primary), var(--academic-primary-hover));
  color: #fff;
  font-size: 18px;
  font-weight: 800;
  box-shadow:
    0 0 0 2px rgba(255, 255, 255, 0.5),
    0 6px 18px rgba(37, 99, 235, 0.3);
}

/* ====== 统计卡片（与 Bento 统一） ====== */
.stats-row {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 10px 12px 12px;
  border-radius: 16px;
  background: #ffffff;
  border: none;
  cursor: pointer;
  transition: transform 0.22s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.22s ease;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.05),
    0 2px 4px -1px rgba(0, 0, 0, 0.03);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow:
    0 12px 28px -6px rgba(0, 0, 0, 0.1),
    0 4px 10px -2px rgba(0, 0, 0, 0.04);
}

.stat-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 2px;
}

.stat-icon {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  border: 1px solid rgba(15, 23, 42, 0.05);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.95),
    inset 0 -1px 2px rgba(15, 23, 42, 0.04);
}

.stat-icon.upload {
  background: rgba(37, 99, 235, 0.12);
  color: var(--academic-primary);
}

.stat-icon.parsed {
  background: rgba(16, 185, 129, 0.12);
  color: #059669;
}

.stat-icon.sessions {
  background: rgba(100, 116, 139, 0.1);
  color: #64748b;
}

.stat-sparkline {
  flex-shrink: 0;
  opacity: 0.55;
  color: #2563eb;
}

.stat-sparkline--muted {
  color: #94a3b8;
  opacity: 0.45;
}

.stat-value {
  font-size: 26px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.03em;
  color: #2563eb;
}

.stat-card--success .stat-value {
  color: #059669;
}

.stat-value--muted {
  color: #334155;
}

.stat-label {
  font-size: 11px;
  font-weight: 500;
  color: #94a3b8;
  letter-spacing: 0.01em;
}

.stat-label--live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5);
  animation: status-pulse 2s ease-in-out infinite;
}

@keyframes status-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.45);
    opacity: 1;
  }
  50% {
    box-shadow: 0 0 0 6px rgba(16, 185, 129, 0);
    opacity: 0.85;
  }
}

/* ====== 核心能力区块 ====== */
.capabilities-zone {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-head {
  margin-bottom: 0;
}

.section-eyebrow {
  display: inline-block;
  margin-bottom: 4px;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #6366f1;
}

.section-head h3 {
  font-size: 17px;
  color: #0f172a;
  font-weight: 800;
  letter-spacing: -0.025em;
  margin: 0 0 2px;
  line-height: 1.25;
}

.section-head p {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: #64748b;
  max-width: 36em;
}

.topics-section {
  flex-shrink: 0;
  margin-top: 16px;
}

.topics-title {
  font-size: 15px;
  color: var(--academic-text-main);
  font-weight: 600;
  margin: 0 0 14px;
}

/* ====== Bento Grid ====== */
.bento-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-template-rows: 1fr 1fr;
  gap: 12px;
  margin-bottom: 0;
}

.bento-grid > * {
  min-height: 0;
  height: 100%;
}

.bento-parse,
.bento-graph {
  grid-column: span 6;
  grid-row: 1;
}

.bento-compare {
  grid-column: span 6;
  grid-row: 2;
}

.bento-session,
.bento-reports {
  grid-column: span 3;
  grid-row: 2;
}

.bento-session :deep(.bento-content),
.bento-reports :deep(.bento-content) {
  padding: 18px 20px;
}

.bento-session :deep(.bento-compact-group),
.bento-reports :deep(.bento-compact-group) {
  max-width: 62%;
}

/* 装饰：文献对比 */
.decor-compare {
  position: absolute;
  top: 50%;
  right: 6%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  width: min(42%, 280px);
  height: min(72%, 132px);
}

.compare-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 10px 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.65);
  background: rgba(255, 255, 255, 0.42);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 6px 20px rgba(16, 185, 129, 0.1);
}

.panel-label {
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(5, 150, 105, 0.7);
}

.dim-bar {
  height: 5px;
  border-radius: 3px;
  width: var(--w, 60%);
  background: linear-gradient(90deg, rgba(16, 185, 129, 0.35), rgba(52, 211, 153, 0.65));
  animation: bar-pulse 3s ease-in-out infinite;
}

.panel-b .dim-bar {
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.35), rgba(16, 185, 129, 0.6));
  animation-delay: 0.6s;
}

.dim-bar:nth-child(3) { animation-delay: 0.2s; }
.dim-bar:nth-child(4) { animation-delay: 0.4s; }
.panel-b .dim-bar:nth-child(3) { animation-delay: 0.8s; }
.panel-b .dim-bar:nth-child(4) { animation-delay: 1s; }

@keyframes bar-pulse {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 1; }
}

.compare-vs {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(16, 185, 129, 0.2);
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.12);
}

.compare-vs span {
  font-size: 9px;
  font-weight: 800;
  color: #059669;
  letter-spacing: 0.04em;
}

/* 装饰：发起研究 */
.decor-session {
  position: absolute;
  top: 30px;
  right: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 72px;
  opacity: 0.82;
}

.session-bar {
  height: 8px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.16);
}

.session-bar-long {
  width: 100%;
}

.session-bar-short {
  width: 58%;
}

.session-input {
  width: 100%;
  height: 28px;
  margin-top: 2px;
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.07);
  border: 1px solid rgba(99, 102, 241, 0.12);
}

/* 装饰：研读报告 */
.decor-reports {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 72px;
  height: 88px;
  opacity: 0.82;
}

.report-sheet {
  width: 100%;
  height: 100%;
  padding: 10px 9px;
  border-radius: 10px;
  border: 1px solid rgba(245, 158, 11, 0.12);
  background: rgba(255, 255, 255, 0.55);
  box-shadow: 0 4px 14px rgba(245, 158, 11, 0.08);
  display: flex;
  flex-direction: column;
  gap: 5px;
  transform: rotate(2deg);
}

.report-heading {
  height: 7px;
  width: 72%;
  border-radius: 2px;
  background: rgba(245, 158, 11, 0.5);
}

.report-line {
  height: 3px;
  border-radius: 2px;
  background: rgba(245, 158, 11, 0.22);
}

.report-line.w90 { width: 90%; }
.report-line.w70 { width: 70%; }
.report-line.w55 { width: 55%; }

/* 装饰：文档解析 */
.decor-docs {
  position: absolute;
  top: 50%;
  right: 6%;
  transform: translateY(-50%);
  width: min(42%, 168px);
  height: min(72%, 148px);
}

.doc-sheet {
  position: absolute;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.65);
  background: rgba(255, 255, 255, 0.45);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 8px 32px rgba(37, 99, 235, 0.1);
}

.doc-a {
  inset: 18px 28px 28px 8px;
  transform: rotate(-6deg);
}

.doc-b {
  inset: 8px 8px 38px 32px;
  transform: rotate(4deg);
  background: rgba(255, 255, 255, 0.55);
}

.doc-b::before,
.doc-b::after,
.doc-a::before {
  content: '';
  position: absolute;
  left: 14px;
  height: 3px;
  border-radius: 2px;
  background: rgba(37, 99, 235, 0.15);
}

.doc-b::before { top: 16px; width: 56px; }
.doc-b::after { top: 26px; width: 40px; }
.doc-a::before { top: 20px; width: 48px; }

.doc-scan {
  position: absolute;
  left: 6px;
  right: 6px;
  top: 42%;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(37, 99, 235, 0.55), transparent);
  animation: scan-pulse 2.8s ease-in-out infinite;
}

@keyframes scan-pulse {
  0%, 100% { opacity: 0.35; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(6px); }
}

/* 装饰：知识图谱 */
.decor-graph {
  position: absolute;
  top: 50%;
  right: 2%;
  transform: translateY(-50%);
  width: min(44%, 172px);
  height: min(78%, 172px);
  opacity: 0.72;
  filter: drop-shadow(0 4px 16px rgba(99, 102, 241, 0.12));
}

.topic-chip {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--academic-primary);
  border: none;
  font-weight: 500;
  box-shadow: 0 1px 3px rgba(37, 99, 235, 0.06);
}

/* ====== 响应式 ====== */
@media (max-width: 860px) {
  .dashboard-page {
    padding: 24px 20px;
    max-width: 100%;
  }

  .welcome-banner {
    padding: 22px 20px 20px;
    margin-bottom: 40px;
    border-radius: 20px;
  }

  .greeting h1 {
    font-size: 22px;
  }

  .stat-value {
    font-size: 30px;
  }

  .bento-grid {
    flex: none;
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: auto;
    grid-auto-rows: minmax(140px, auto);
  }

  .bento-grid > * {
    height: auto;
  }

  .bento-parse,
  .bento-graph,
  .bento-compare {
    grid-column: span 2;
    grid-row: auto;
  }

  .bento-session,
  .bento-reports {
    grid-column: span 1;
    grid-row: auto;
  }

  .decor-compare {
    width: 160px;
    height: 90px;
    opacity: 0.75;
  }

  .decor-session,
  .decor-reports {
    opacity: 0.65;
    transform: scale(0.9);
    transform-origin: top right;
  }

  .decor-docs {
    width: 110px;
    height: 90px;
    opacity: 0.7;
  }

  .decor-graph {
    width: 140px;
    height: 140px;
    opacity: 0.6;
  }
}

@media (max-width: 520px) {
  .welcome-section {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .avatar-wrap {
    flex-direction: row;
    align-self: flex-end;
    gap: 8px;
  }

  .avatar-halo {
    top: -4px;
    left: 4px;
    transform: none;
  }

  .stats-row {
    grid-template-columns: 1fr;
  }

  .stat-value {
    font-size: 28px;
  }

  .bento-grid {
    flex: none;
    grid-template-columns: 1fr;
    grid-template-rows: auto;
    grid-auto-rows: minmax(130px, auto);
  }

  .bento-grid > * {
    height: auto;
  }

  .bento-parse,
  .bento-graph,
  .bento-compare,
  .bento-session,
  .bento-reports {
    grid-column: span 1;
    grid-row: auto;
  }

  .decor-compare,
  .decor-session,
  .decor-reports {
    display: none;
  }
}

/* ====== 热门主题 ====== */
.topic-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

</style>
