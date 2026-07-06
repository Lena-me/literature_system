<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import { adminApi } from '@/api/admin'

const loading = ref(true)
const data = ref<any>({})
const chartEl = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null

const health = computed(() => data.value.health || {})
const cards = computed(() => data.value.cards || {})
const trends = computed(() => data.value.trends || {})
const errorClusters = computed(() => data.value.error_clusters || [])
const errorClustersMeta = computed(() => data.value.error_clusters_meta || {})
const topUsers = computed(() => data.value.top_users || [])
const topUsersMeta = computed(() => data.value.top_users_meta || {})

const topUsersPeriodLabel = computed(() => {
  const map: Record<string, string> = {
    today: '今日',
    '7d': '近 7 日',
    lifetime: '累计估算',
    none: '',
  }
  return map[topUsersMeta.value.period] || ''
})

const errorSourceLabel = computed(() => {
  const map: Record<string, string> = {
    system_logs_24h: '近 24h 系统日志',
    system_logs_7d: '近 7 日系统日志',
    parse_tasks_24h: '近 24h 失败任务',
    parse_tasks_all: '历史失败任务',
    none: '',
  }
  return map[errorClustersMeta.value.source] || ''
})

const gaugeDasharray = computed(() => {
  const score = Math.min(100, Math.max(0, health.value.total_score ?? 0))
  const circumference = 2 * Math.PI * 42
  const filled = circumference * (score / 100)
  return `${filled} ${circumference}`
})

const healthTone = computed(() => {
  const s = health.value.total_score ?? 0
  if (s >= 90) return 'healthy'
  if (s >= 75) return 'warning'
  return 'critical'
})

const healthStatusLabel = computed(() => {
  const map: Record<string, string> = { healthy: '健康', warning: '预警', critical: '严重' }
  return map[health.value.status] || '未知'
})

const healthComponents = computed(() => [
  { key: 'parse', label: '解析', data: health.value.components?.parse },
  { key: 'model', label: '模型', data: health.value.components?.model },
  { key: 'infra', label: '基建', data: health.value.components?.infra },
])

function sparklinePoints(values: number[], w = 72, h = 24): string {
  const arr = values?.length ? values : [0]
  const max = Math.max(...arr, 1)
  const min = Math.min(...arr, 0)
  const range = max - min || 1
  return arr
    .map((v, i) => {
      const x = (i / Math.max(arr.length - 1, 1)) * w
      const y = h - ((v - min) / range) * (h - 4) - 2
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

function formatRate(rate: number) {
  return `${((rate || 0) * 100).toFixed(1)}%`
}

function formatTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n ?? 0)
}

async function load() {
  loading.value = true
  try {
    data.value = await adminApi.overview()
    setTimeout(renderChart, 50)
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartEl.value) return
  if (!chartInstance) chartInstance = echarts.init(chartEl.value)
  const dates = (trends.value.dates || []).map((d: string) => {
    const p = d.split('-')
    return `${p[1]}/${p[2]}`
  })
  chartInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['上传', '解析', '问答'], top: 0, right: 0, textStyle: { fontSize: 11 } },
    grid: { top: 32, right: 12, bottom: 24, left: 40 },
    xAxis: { type: 'category', data: dates, axisTick: { show: false } },
    yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
    series: [
      { name: '上传', type: 'line', smooth: true, data: trends.value.upload || [], symbol: 'none', lineStyle: { width: 2 } },
      { name: '解析', type: 'line', smooth: true, data: trends.value.parse || [], symbol: 'none', lineStyle: { width: 2 } },
      { name: '问答', type: 'line', smooth: true, data: trends.value.qa || [], symbol: 'none', lineStyle: { width: 2 } },
    ],
  })
}

function onResize() {
  chartInstance?.resize()
}

onMounted(() => {
  load()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chartInstance?.dispose()
})
</script>

<template>
  <div class="overview-page">
    <!-- 骨架屏 -->
    <template v-if="loading">
      <div class="metrics-grid">
        <div v-for="i in 4" :key="i" class="metric-card soft-card skeleton-card">
          <div class="sk-line sk-w60" />
          <div class="sk-line sk-w40 sk-lg" />
          <div class="sk-line sk-w80" />
        </div>
      </div>
      <div class="chart-card soft-card skeleton-card">
        <div class="sk-line sk-w30" />
        <div class="sk-chart" />
      </div>
      <div class="bottom-grid">
        <div v-for="i in 2" :key="i" class="panel soft-card skeleton-card">
          <div class="sk-line sk-w40" />
          <div v-for="j in 4" :key="j" class="sk-row" />
        </div>
      </div>
    </template>

    <template v-else>
      <div class="metrics-grid">
        <!-- 综合健康度 -->
        <div class="metric-card soft-card health-card" :class="healthTone">
          <div class="metric-head">
            <span class="metric-label">综合健康度</span>
            <span class="status-chip">{{ healthStatusLabel }}</span>
          </div>
          <div class="health-gauge-wrap">
            <svg viewBox="0 0 100 100" class="health-gauge">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#e5e7eb" stroke-width="8" />
              <circle
                cx="50" cy="50" r="42" fill="none"
                stroke="currentColor" stroke-width="8" stroke-linecap="round"
                transform="rotate(-90 50 50)"
                :stroke-dasharray="gaugeDasharray"
              />
            </svg>
            <div class="gauge-center">
              <span class="gauge-score">{{ health.total_score ?? '-' }}</span>
              <span class="gauge-unit">/ 100</span>
            </div>
          </div>
          <div class="component-bars">
            <div v-for="c in healthComponents" :key="c.key" class="component-row">
              <span class="component-label">{{ c.label }}</span>
              <div class="component-track">
                <div class="component-fill" :style="{ width: `${c.data?.score ?? 0}%` }" />
              </div>
              <span class="component-score">{{ c.data?.score ?? '-' }}</span>
            </div>
          </div>
        </div>

        <div class="metric-card soft-card">
          <div class="metric-head">
            <span class="metric-label">今日大模型调用</span>
            <svg width="72" height="24" viewBox="0 0 72 24"><path :d="sparklinePoints(cards.sparklines?.llm)" fill="none" stroke="#6366f1" stroke-width="1.5" /></svg>
          </div>
          <div class="metric-value">{{ cards.llm_today?.total ?? 0 }}</div>
          <div class="metric-sub">加权成功率 {{ formatRate(cards.llm_today?.success_rate) }} · Token {{ formatTokens(cards.llm_today?.total_tokens) }}</div>
        </div>

        <div class="metric-card soft-card">
          <div class="metric-head">
            <span class="metric-label">向量库规模</span>
            <svg width="72" height="24" viewBox="0 0 72 24"><path :d="sparklinePoints(cards.sparklines?.vector)" fill="none" stroke="#0ea5e9" stroke-width="1.5" /></svg>
          </div>
          <div class="metric-value">{{ cards.vector_total ?? 0 }}</div>
          <div class="metric-sub">Milvus 向量总数</div>
        </div>

        <div class="metric-card soft-card">
          <div class="metric-head">
            <span class="metric-label">排队解析任务</span>
            <svg width="72" height="24" viewBox="0 0 72 24"><path :d="sparklinePoints(cards.sparklines?.tasks)" fill="none" stroke="#f59e0b" stroke-width="1.5" /></svg>
          </div>
          <div class="metric-value">{{ cards.queued_tasks ?? 0 }}</div>
          <div class="metric-sub">queued + running</div>
        </div>
      </div>

      <div class="chart-card soft-card">
        <div class="section-head">
          <h3>核心业务趋势</h3>
          <el-button size="small" @click="load">刷新</el-button>
        </div>
        <div ref="chartEl" class="chart-box" />
      </div>

      <div class="bottom-grid">
        <div class="panel soft-card">
          <div class="section-head">
            <h3>智能聚类告警</h3>
            <span class="cluster-count">{{ errorClusters.length }} 类<span v-if="errorSourceLabel"> · {{ errorSourceLabel }}</span></span>
          </div>
          <div class="cluster-list">
            <div v-for="(item, idx) in errorClusters" :key="idx" class="cluster-item">
              <p class="cluster-summary">{{ item.summary }}</p>
              <span class="trigger-badge">🔥 {{ item.count }} 次触发</span>
            </div>
            <div v-if="!errorClusters.length" class="empty">近 24 小时无 ERROR 聚类</div>
          </div>
        </div>

        <div class="panel soft-card">
          <div class="section-head">
            <h3>资源消耗 TOP 3<span v-if="topUsersPeriodLabel" class="period-tag">{{ topUsersPeriodLabel }}</span></h3>
          </div>
          <div class="top-list">
            <div v-for="(u, idx) in topUsers" :key="u.id" class="top-item">
              <div class="top-rank">#{{ idx + 1 }}</div>
              <div class="top-body">
                <div class="top-name">{{ u.username }} <span class="uid">ID {{ u.id }}</span></div>
                <div class="token-row">
                  <span class="token-num">{{ formatTokens(u.tokens) }}</span>
                  <span class="token-label">Token 估算</span>
                </div>
                <div class="progress-track">
                  <div class="progress-fill" :style="{ width: `${u.consumption_pct}%` }" />
                </div>
                <div class="top-meta">上传 {{ u.uploads }} · 问答 {{ u.qa_calls }}</div>
              </div>
            </div>
            <div v-if="!topUsers.length" class="empty">今日暂无高消耗用户</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.overview-page {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  padding: 12px 14px;
}

.metric-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.metric-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.metric-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--academic-text-main);
  line-height: 1.2;
}

.metric-sub {
  margin-top: 3px;
  font-size: 11px;
  color: var(--academic-text-muted);
}

/* 健康度卡片 */
.health-card { color: #059669; }
.health-card.warning { color: #d97706; }
.health-card.critical { color: #dc2626; }

.status-chip {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 999px;
  background: currentColor;
  color: #fff;
  filter: brightness(1);
}
.health-card .status-chip { background: color-mix(in srgb, currentColor 15%, transparent); color: inherit; }

.health-gauge-wrap {
  position: relative;
  width: 88px;
  height: 88px;
  margin: 4px auto 6px;
}

.health-gauge { width: 100%; height: 100%; }

.gauge-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.gauge-score {
  font-size: 22px;
  font-weight: 800;
  color: var(--academic-text-main);
  line-height: 1;
}

.gauge-unit {
  font-size: 10px;
  color: var(--academic-text-muted);
}

.deduction-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
  font-size: 10px;
  color: var(--academic-text-muted);
}

.component-bars {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.component-row {
  display: grid;
  grid-template-columns: 28px 1fr 28px;
  align-items: center;
  gap: 6px;
  font-size: 10px;
}

.component-label {
  color: var(--academic-text-muted);
}

.component-track {
  height: 4px;
  background: #e5e7eb;
  border-radius: 999px;
  overflow: hidden;
}

.component-fill {
  height: 100%;
  background: currentColor;
  border-radius: 999px;
  transition: width 0.3s ease;
}

.component-score {
  text-align: right;
  font-weight: 600;
  color: var(--academic-text-main);
}

.period-tag {
  margin-left: 6px;
  font-size: 11px;
  font-weight: 500;
  color: var(--academic-text-muted);
}

.chart-card { padding: 12px 14px; }
.chart-box { height: 240px; }

.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.panel {
  padding: 12px 14px;
  min-height: 220px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-head h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.cluster-count {
  font-size: 11px;
  color: var(--academic-text-muted);
}

.cluster-list, .top-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow: auto;
}

.cluster-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--academic-canvas);
}

.cluster-summary {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--academic-text-body);
  flex: 1;
  min-width: 0;
  word-break: break-word;
}

.trigger-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 999px;
  background: #fee2e2;
  color: #dc2626;
}

.top-item {
  display: flex;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--academic-canvas);
}

.top-rank {
  font-size: 14px;
  font-weight: 800;
  color: var(--academic-primary);
  width: 24px;
}

.top-body { flex: 1; min-width: 0; }

.top-name {
  font-size: 13px;
  font-weight: 600;
}

.uid {
  font-weight: 400;
  font-size: 11px;
  color: var(--academic-text-muted);
}

.token-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-top: 2px;
}

.token-num {
  font-size: 18px;
  font-weight: 800;
  color: var(--academic-primary);
}

.token-label {
  font-size: 10px;
  color: var(--academic-text-muted);
}

.progress-track {
  height: 4px;
  background: #e5e7eb;
  border-radius: 999px;
  margin: 6px 0 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--academic-primary), #6366f1);
  border-radius: 999px;
  transition: width 0.4s ease;
}

.top-meta {
  font-size: 10px;
  color: var(--academic-text-muted);
}

.empty {
  text-align: center;
  padding: 20px;
  font-size: 12px;
  color: var(--academic-text-muted);
}

/* 骨架屏 */
.skeleton-card { animation: pulse 1.5s ease-in-out infinite; }
.sk-line {
  height: 12px;
  background: #e5e7eb;
  border-radius: 4px;
  margin-bottom: 8px;
}
.sk-lg { height: 28px; }
.sk-w30 { width: 30%; }
.sk-w40 { width: 40%; }
.sk-w60 { width: 60%; }
.sk-w80 { width: 80%; }
.sk-chart { height: 200px; background: #e5e7eb; border-radius: 8px; margin-top: 12px; }
.sk-row { height: 36px; background: #e5e7eb; border-radius: 6px; margin-bottom: 6px; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

@media (max-width: 1100px) {
  .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .bottom-grid { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .metrics-grid { grid-template-columns: 1fr; }
}
</style>
