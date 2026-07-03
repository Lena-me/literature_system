<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import 'echarts-wordcloud'
import StatCard from '@/components/common/StatCard.vue'
import { featuresApi } from '@/api/features'
import { PieChart, Cloudy } from '@element-plus/icons-vue'

const overview = ref<any>({ paper_count:0, report_count:0, qa_count:0, records:[], recent_records:[] })
const chartRef = ref<HTMLDivElement | null>(null)
const chartInstance = ref<echarts.ECharts | null>(null)
const displayMode = ref<'pie' | 'wordcloud'>('pie')

const colors = [
  '#6366f1',
  '#8b5cf6',
  '#ec4899',
  '#f43f5e',
  '#f97316',
  '#eab308',
  '#22c55e',
  '#14b8a6',
  '#06b6d4',
  '#3b82f6',
]

function getSortedKeywords(limit: number): [string, number][] {
  const keywordCloud = overview.value.keyword_cloud || { RAG:8, Agent:6, '文献解析':10, '方法复现':7, '数据集':6, '知识图谱':9, '实验复现':5, '数据分析':4 }
  const data = Object.entries(keywordCloud) as [string, number][]
  return data
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
}

function renderPieChart() {
  if (!chartRef.value) return
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
  chartInstance.value = echarts.init(chartRef.value)
  const data = getSortedKeywords(6)
  chartInstance.value.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} 次',
    },
    series: [{
      type: 'pie',
      radius: ['45%', '72%'],
      data: data.map(([name, value], index) => ({ 
        name, 
        value,
        itemStyle: {
          color: colors[index % colors.length],
          borderColor: '#fff',
          borderWidth: 2,
        }
      })),
      label: {
        color: '#334155',
        fontSize: 13,
      },
    }],
  })
}

function renderWordCloud() {
  if (!chartRef.value) return
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
  chartInstance.value = echarts.init(chartRef.value)
  const data = getSortedKeywords(10)
  const maxValue = Math.max(...data.map(d => d[1]))
  chartInstance.value.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} 次',
    },
    series: [{
      type: 'wordCloud',
      gridSize: 6,
      sizeRange: [6, 50],
      rotationRange: [-45, 45],
      rotationStep: 15,
      shape: 'circle',
      width: chartRef.value.clientWidth,
      height: chartRef.value.clientHeight,
      drawOutOfBound: false,
      textStyle: {
        fontFamily: 'Microsoft YaHei, sans-serif',
        fontWeight: 'bold',
        color: () => colors[Math.floor(Math.random() * colors.length)],
      },
      emphasis: {
        focus: 'self',
        textStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, 0.3)',
        },
      },
      data: data.map(([name, value], index) => ({
        name,
        value,
        textStyle: {
          fontSize: 8 + (value / maxValue) * 35,
          color: colors[index % colors.length],
        },
      })),
    }],
  })
}

function render() {
  if (displayMode.value === 'pie') {
    renderPieChart()
  } else {
    renderWordCloud()
  }
}

onMounted(async () => {
  overview.value = await featuresApi.overview()
  overview.value.records = overview.value.records || overview.value.recent_records || []
  setTimeout(render, 100)
})

watch(displayMode, () => {
  setTimeout(render, 50)
})
</script>

<template>
  <div class="archive">
    <h2 class="page-title">学习档案</h2>

    <div class="stats">
      <StatCard label="文献阅读数量" :value="overview.paper_count" />
      <StatCard label="报告生成数量" :value="overview.report_count" />
      <StatCard label="问答次数" :value="overview.qa_count" />
    </div>

    <section class="grid2">
      <div class="card">
        <div class="card-header">
          <h3>关键词分布</h3>
          <div class="mode-switch">
            <button 
              class="switch-btn" 
              :class="{ active: displayMode === 'pie' }"
              @click="displayMode = 'pie'"
            >
              <PieChart class="icon" />
              <span>环形图</span>
            </button>
            <button 
              class="switch-btn" 
              :class="{ active: displayMode === 'wordcloud' }"
              @click="displayMode = 'wordcloud'"
            >
              <Cloudy class="icon" />
              <span>词云</span>
            </button>
          </div>
        </div>
        <div ref="chartRef" class="chart" />
      </div>
      <div class="card">
        <h3>历史操作记录</h3>
        <div class="records-list">
          <div v-for="r in overview.records" :key="r.id" class="record-item">
            <span class="record-event">{{ r.event_type }}</span>
            <span class="record-meta">paper {{ r.paper_id || '-' }}</span>
            <span class="record-time">{{ r.created_at }}</span>
          </div>
          <div v-if="!overview.records?.length" class="empty-hint">暂无操作记录</div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.archive {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 24px 32px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--academic-text-main);
  margin-bottom: 24px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.card {
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 16px;
  padding: 22px;
  min-height: 440px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin: 0;
}

.mode-switch {
  display: flex;
  background: var(--academic-canvas);
  border-radius: 8px;
  padding: 4px;
}

.switch-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn:hover {
  color: var(--academic-text-main);
}

.switch-btn.active {
  background: var(--academic-primary);
  color: #fff;
}

.switch-btn .icon {
  width: 16px;
  height: 16px;
}

.chart {
  height: 380px;
}

.records-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 380px;
  overflow-y: auto;
}

.record-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--academic-canvas);
  font-size: 13px;
}

.record-event {
  color: var(--academic-primary);
  font-weight: 600;
}

.record-meta {
  color: var(--academic-text-muted);
}

.record-time {
  margin-left: auto;
  color: var(--academic-text-muted);
  font-size: 12px;
}

.empty-hint {
  color: var(--academic-text-muted);
  font-size: 14px;
  text-align: center;
  padding: 60px 20px;
}
</style>
