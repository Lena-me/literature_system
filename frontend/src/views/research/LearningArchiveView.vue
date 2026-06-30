<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import StatCard from '@/components/common/StatCard.vue'
import { featuresApi } from '@/api/features'

const overview = ref<any>({ paper_count:0, report_count:0, qa_count:0, records:[], recent_records:[] })
const chartRef = ref<HTMLDivElement | null>(null)

onMounted(async () => {
  overview.value = await featuresApi.overview()
  overview.value.records = overview.value.records || overview.value.recent_records || []
  setTimeout(render, 100)
})

function render() {
  if (!chartRef.value) return
  const chart = echarts.init(chartRef.value)
  const data = Object.entries(overview.value.keyword_cloud || { RAG:8, Agent:6, '文献解析':10, '方法复现':7, '数据集':6 })
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {},
    series: [{
      type: 'pie',
      radius: ['45%', '72%'],
      data: data.map(([name, value]) => ({ name, value })),
      label: {
        color: '#334155',
        fontSize: 13,
      },
      itemStyle: {
        borderColor: '#fff',
        borderWidth: 2,
      },
    }],
  })
}
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
        <h3>关键词分布</h3>
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

.card h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin-bottom: 16px;
}

.chart {
  height: 380px;
}

/* ===== 操作记录 ===== */
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
