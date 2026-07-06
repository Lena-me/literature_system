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
  const circumference = 2 * Math.PI * 36
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

function sparklinePoints(values: number[], w = 64, h = 20): string {
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
    legend: {
      data: ['上传', '解析', '问答'],
      top: 0,
      right: 0,
      textStyle: { fontSize: 11, color: '#64748b' },
      itemWidth: 12,
      itemHeight: 2,
    },
    grid: { top: 36, right: 8, bottom: 28, left: 44 },
    xAxis: {
      type: 'category',
      data: dates,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { type: 'dashed', color: '#f1f5f9' } },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
    },
    series: [
      { name: '上传', type: 'line', smooth: true, data: trends.value.upload || [], symbol: 'none', lineStyle: { width: 2, color: '#2563EB' }, itemStyle: { color: '#2563EB' } },
      { name: '解析', type: 'line', smooth: true, data: trends.value.parse || [], symbol: 'none', lineStyle: { width: 2, color: '#6366F1' }, itemStyle: { color: '#6366F1' } },
      { name: '问答', type: 'line', smooth: true, data: trends.value.qa || [], symbol: 'none', lineStyle: { width: 2, color: '#0891B2' }, itemStyle: { color: '#0891B2' } },
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
  <div class="admin-page">
    <!-- 骨架屏 -->
    <template v-if="loading">
      <section class="admin-metrics-bar">
        <div v-for="i in 4" :key="i" class="admin-metric">
          <div class="sk-line sk-w50" />
          <div class="sk-line sk-lg" />
          <div class="sk-line sk-w70" />
        </div>
      </section>
      <div class="admin-page-body">
        <div class="admin-section">
          <div class="sk-line sk-w30" />
          <div class="sk-chart" />
        </div>
        <div class="admin-split">
          <div v-for="i in 2" :key="i">
            <div class="sk-line sk-w40" />
            <div v-for="j in 4" :key="j" class="sk-row" />
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <!-- 通栏指标 -->
      <section class="admin-metrics-bar">
        <div class="admin-metric admin-metric--wide admin-metric--emerald health-metric" :class="healthTone">
          <div class="admin-metric-head">
            <span class="admin-metric-label">综合健康度</span>
            <span class="status-tag">{{ healthStatusLabel }}</span>
          </div>
          <div class="health-inline">
            <div class="health-gauge-wrap">
              <svg viewBox="0 0 80 80" class="health-gauge">
                <circle cx="40" cy="40" r="36" fill="none" stroke="#e2e8f0" stroke-width="6" />
                <circle
                  cx="40" cy="40" r="36" fill="none"
                  stroke="currentColor" stroke-width="6" stroke-linecap="round"
                  transform="rotate(-90 40 40)"
                  :stroke-dasharray="gaugeDasharray"
                />
              </svg>
              <div class="gauge-center">
                <span class="gauge-score">{{ health.total_score ?? '—' }}</span>
              </div>
            </div>
            <div class="component-bars">
              <div v-for="c in healthComponents" :key="c.key" class="component-row">
                <span class="component-label">{{ c.label }}</span>
                <div class="component-track">
                  <div class="component-fill" :style="{ width: `${c.data?.score ?? 0}%` }" />
                </div>
                <span class="component-score">{{ c.data?.score ?? '—' }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="admin-metric-divider" />

        <div class="admin-metric admin-metric--indigo">
          <div class="admin-metric-head">
            <span class="admin-metric-label">今日大模型调用</span>
            <svg width="64" height="20" viewBox="0 0 64 20" aria-hidden="true">
              <path :d="sparklinePoints(cards.sparklines?.llm)" fill="none" stroke="#6366f1" stroke-width="1.5" />
            </svg>
          </div>
          <div class="admin-metric-value is-accent">{{ cards.llm_today?.total ?? 0 }}</div>
          <div class="admin-metric-sub">
            加权成功率 {{ formatRate(cards.llm_today?.success_rate) }} · Token {{ formatTokens(cards.llm_today?.total_tokens) }}
          </div>
        </div>

        <div class="admin-metric-divider" />

        <div class="admin-metric admin-metric--cyan">
          <div class="admin-metric-head">
            <span class="admin-metric-label">向量库规模</span>
            <svg width="64" height="20" viewBox="0 0 64 20" aria-hidden="true">
              <path :d="sparklinePoints(cards.sparklines?.vector)" fill="none" stroke="#0891b2" stroke-width="1.5" />
            </svg>
          </div>
          <div class="admin-metric-value is-accent">{{ cards.vector_total ?? 0 }}</div>
          <div class="admin-metric-sub">Milvus 向量总数</div>
        </div>

        <div class="admin-metric-divider" />

        <div class="admin-metric admin-metric--amber">
          <div class="admin-metric-head">
            <span class="admin-metric-label">排队解析任务</span>
            <svg width="64" height="20" viewBox="0 0 64 20" aria-hidden="true">
              <path :d="sparklinePoints(cards.sparklines?.tasks)" fill="none" stroke="#d97706" stroke-width="1.5" />
            </svg>
          </div>
          <div class="admin-metric-value is-accent">{{ cards.queued_tasks ?? 0 }}</div>
          <div class="admin-metric-sub">排队中</div>
        </div>
      </section>

      <div class="admin-page-body">
        <!-- 趋势图 -->
        <section class="admin-section">
          <div class="admin-section-header">
            <h2 class="admin-section-title">核心业务趋势</h2>
            <el-button text type="primary" size="small" @click="load">刷新</el-button>
          </div>
          <div ref="chartEl" class="chart-box" />
        </section>

        <!-- 双栏列表 -->
        <div class="admin-split">
          <section class="admin-section">
            <div class="admin-section-header">
              <h2 class="admin-section-title is-amber">智能聚类告警</h2>
              <span class="admin-section-meta">
                {{ errorClusters.length }} 类<span v-if="errorSourceLabel"> · {{ errorSourceLabel }}</span>
              </span>
            </div>
            <div class="admin-flat-list">
              <div v-for="(item, idx) in errorClusters" :key="idx" class="admin-flat-row cluster-row">
                <p class="cluster-summary">{{ item.summary }}</p>
                <span class="trigger-count">{{ item.count }} 次</span>
              </div>
              <div v-if="!errorClusters.length" class="admin-empty">近 24 小时无 ERROR 聚类</div>
            </div>
          </section>

          <section class="admin-section">
            <div class="admin-section-header">
              <h2 class="admin-section-title is-violet">
                资源消耗 TOP 3
                <span v-if="topUsersPeriodLabel" class="period-tag">{{ topUsersPeriodLabel }}</span>
              </h2>
            </div>
            <div class="admin-flat-list">
              <div v-for="(u, idx) in topUsers" :key="u.id" class="admin-flat-row top-row">
                <div class="top-rank">{{ idx + 1 }}</div>
                <div class="top-body">
                  <div class="top-name">
                    {{ u.username || u.name || '未知用户' }}
                  </div>
                  <div class="top-stats">
                    <span class="token-num">{{ formatTokens(u.tokens) }}</span>
                    <span class="token-label">Token 估算</span>
                  </div>
                  <div class="progress-track">
                    <div class="progress-fill" :style="{ width: `${u.consumption_pct}%` }" />
                  </div>
                  <div class="top-meta">上传 {{ u.uploads }} · 问答 {{ u.qa_calls }}</div>
                </div>
              </div>
              <div v-if="!topUsers.length" class="admin-empty">今日暂无高消耗用户</div>
            </div>
          </section>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.health-metric {
  color: #059669;
}

.health-metric.warning {
  color: #d97706;
}

.health-metric.critical {
  color: #dc2626;
}

.status-tag {
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  background: color-mix(in srgb, currentColor 12%, transparent);
}

.health-inline {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-top: 0.25rem;
}

.health-gauge-wrap {
  position: relative;
  width: 72px;
  height: 72px;
  flex-shrink: 0;
}

.health-gauge {
  width: 100%;
  height: 100%;
}

.gauge-center {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}

.gauge-score {
  font-size: 1.25rem;
  font-weight: 600;
  color: #0f172a;
  letter-spacing: -0.02em;
}

.component-bars {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.component-row {
  display: grid;
  grid-template-columns: 2rem 1fr 2rem;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.6875rem;
}

.component-label {
  color: #64748b;
}

.component-track {
  height: 3px;
  background: #e2e8f0;
  overflow: hidden;
}

.component-fill {
  height: 100%;
  background: currentColor;
  transition: width 0.3s ease;
}

.component-score {
  text-align: right;
  font-weight: 600;
  color: #334155;
}

.chart-box {
  height: 280px;
  width: 100%;
}

.period-tag {
  margin-left: 0.375rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: #94a3b8;
}

.cluster-row {
  align-items: flex-start;
}

.cluster-summary {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: #334155;
  word-break: break-word;
}

.trigger-count {
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: #dc2626;
  font-variant-numeric: tabular-nums;
}

.top-row {
  align-items: flex-start;
  gap: 0.875rem;
}

.top-rank {
  width: 1.25rem;
  font-size: 0.875rem;
  font-weight: 700;
  color: var(--admin-indigo, #6366f1);
  font-variant-numeric: tabular-nums;
  padding-top: 0.125rem;
}

.top-body {
  flex: 1;
  min-width: 0;
}

.top-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
}

.top-stats {
  display: flex;
  align-items: baseline;
  gap: 0.375rem;
  margin-top: 0.125rem;
}

.token-num {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--admin-accent, #2563eb);
  letter-spacing: -0.02em;
}

.token-label {
  font-size: 0.6875rem;
  color: #94a3b8;
}

.progress-track {
  height: 3px;
  background: #e2e8f0;
  margin: 0.5rem 0 0.375rem;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--admin-accent, #2563eb), var(--admin-indigo, #6366f1));
  transition: width 0.35s ease;
}

.top-meta {
  font-size: 0.6875rem;
  color: #94a3b8;
}

/* 骨架屏 */
.sk-line {
  height: 10px;
  background: #e2e8f0;
  margin-bottom: 0.5rem;
}

.sk-lg {
  height: 24px;
  width: 40%;
}

.sk-w30 { width: 30%; }
.sk-w40 { width: 40%; }
.sk-w50 { width: 50%; }
.sk-w70 { width: 70%; }

.sk-chart {
  height: 280px;
  background: #f1f5f9;
  margin-top: 0.75rem;
}

.sk-row {
  height: 40px;
  background: #f1f5f9;
  margin-bottom: 0.5rem;
}

.admin-page:has(.sk-line) .admin-metrics-bar {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
</style>
