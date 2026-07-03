<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import * as echarts from 'echarts'
import 'echarts-wordcloud'
import StatCard from '@/components/common/StatCard.vue'
import { featuresApi } from '@/api/features'
import { PieChart, Cloudy, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'

const overview = ref<any>({ 
  paper_count:0, 
  report_count:0, 
  qa_count:0, 
  records:[], 
  recent_records:[],
  keyword_cloud: {},
  upload_heatmap: { months: [], data: {}, max_value: 1 }
})
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

const weekDays = ['日', '一', '二', '三', '四', '五', '六']

const now = new Date()
const currentMonth = ref<string>(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)

const showCalendar = ref(false)

const availableMonths = computed(() => {
  return overview.value.upload_heatmap?.months || []
})

const currentMonthIndex = computed(() => {
  return availableMonths.value.indexOf(currentMonth.value)
})

const canPrev = computed(() => currentMonthIndex.value > 0)
const canNext = computed(() => currentMonthIndex.value < availableMonths.value.length - 1)

function prevMonth() {
  if (canPrev.value) {
    currentMonth.value = availableMonths.value[currentMonthIndex.value - 1]
  }
}

function nextMonth() {
  if (canNext.value) {
    currentMonth.value = availableMonths.value[currentMonthIndex.value + 1]
  }
}

function selectMonth(month: string) {
  currentMonth.value = month
  showCalendar.value = false
}

const heatmapRows = computed(() => {
  const data = overview.value.upload_heatmap?.data || {}
  const monthData = data[currentMonth.value] || []
  
  const parts = currentMonth.value.split('-')
  const year = parseInt(parts[0])
  const m = parseInt(parts[1])
  const daysInMonth = new Date(year, m, 0).getDate()
  const firstDay = new Date(year, m - 1, 1).getDay()
  
  const allCells: { day: number | null; count: number; date: string | null }[] = []
  
  for (let i = 0; i < firstDay; i++) {
    allCells.push({ day: null, count: 0, date: null })
  }
  
  for (let day = 1; day <= daysInMonth; day++) {
    const count = monthData[day - 1] || 0
    allCells.push({ 
      day, 
      count, 
      date: `${year}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}` 
    })
  }
  
  const totalCells = Math.ceil(allCells.length / 7) * 7
  while (allCells.length < totalCells) {
    allCells.push({ day: null, count: 0, date: null })
  }
  
  const rows: { month: string; data: { day: number | null; count: number; date: string | null }[] }[] = []
  for (let i = 0; i < allCells.length; i += 7) {
    rows.push({ 
      month: currentMonth.value, 
      data: allCells.slice(i, i + 7) 
    })
  }
  
  return rows
})

const getCellColor = (day: number | null, count: number) => {
  if (day === null) return 'transparent'
  const maxValue = overview.value.upload_heatmap?.max_value || 1
  if (count === 0) return '#e8f4fd'
  if (count <= Math.ceil(maxValue * 0.25)) return '#a5d8ff'
  if (count <= Math.ceil(maxValue * 0.5)) return '#69c0ff'
  if (count <= Math.ceil(maxValue * 0.75)) return '#2f80ed'
  return '#1971c2'
}

const currentMonthUploads = computed(() => {
  const data = overview.value.upload_heatmap?.data || {}
  const monthData = data[currentMonth.value] || []
  return monthData.reduce((sum: number, count: number) => sum + count, 0)
})

const calendarYears = computed(() => {
  const years = new Set<string>()
  availableMonths.value.forEach((month: string) => {
    years.add(month.split('-')[0])
  })
  return Array.from(years).sort()
})

const monthsForYear = (year: string) => {
  const allMonths: string[] = []
  const now = new Date()
  const currentYear = now.getFullYear().toString()
  const currentMonth = now.getMonth() + 1
  const maxMonth = year === currentYear ? currentMonth : 12
  for (let i = 1; i <= maxMonth; i++) {
    allMonths.push(i.toString().padStart(2, '0'))
  }
  return allMonths
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
        <div class="card-header">
          <h3>文献上传热力图</h3>
          <div class="month-nav">
            <button 
              class="nav-btn" 
              :class="{ disabled: !canPrev }"
              @click="prevMonth"
              :disabled="!canPrev"
            >
              <ArrowLeft />
            </button>
            <button class="month-btn" @click="showCalendar = !showCalendar">
              {{ currentMonth }}
              <span class="nav-arrow">▼</span>
            </button>
            <button 
              class="nav-btn" 
              :class="{ disabled: !canNext }"
              @click="nextMonth"
              :disabled="!canNext"
            >
              <ArrowRight />
            </button>
          </div>
        </div>
        <div class="heatmap-container">
          <div class="heatmap-header">
            <div class="weekday-labels">
              <span v-for="day in weekDays" :key="day" class="weekday-label">{{ day }}</span>
            </div>
          </div>
          <div class="heatmap-body">
            <div v-for="(row, rowIndex) in heatmapRows" :key="rowIndex" class="heatmap-row">
              <div class="cells">
                <div 
                  v-for="(cell, idx) in row.data" 
                  :key="`${rowIndex}-${idx}`"
                  class="cell"
                  :class="{ empty: !cell.day }"
                  :style="{ backgroundColor: getCellColor(cell.day, cell.count) }"
                  :title="cell.date ? `${cell.date}: ${cell.count} 篇` : ''"
                ></div>
              </div>
            </div>
          </div>
          <div class="month-summary">
            <span class="summary-text">{{ currentMonth }} 共上传 {{ currentMonthUploads }} 篇文献</span>
          </div>
        </div>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="showCalendar" class="calendar-overlay" @click="showCalendar = false">
        <div class="calendar-popup" @click.stop>
          <div class="calendar-header">
            <h4>选择月份</h4>
            <button class="close-btn" @click="showCalendar = false">×</button>
          </div>
          <div class="calendar-content">
            <div v-for="year in calendarYears" :key="year" class="year-group">
              <div class="year-label">{{ year }}年</div>
              <div class="month-grid">
                <button 
                  v-for="month in monthsForYear(year)" 
                  :key="`${year}-${month}`"
                  class="month-cell"
                  :class="{ active: currentMonth === `${year}-${month}` }"
                  @click="selectMonth(`${year}-${month}`)"
                >
                  {{ parseInt(month) }}月
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
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
  display: flex;
  flex-direction: column;
}

.card-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card > div:last-child {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
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

.month-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.nav-btn {
  width: 32px;
  height: 32px;
  border: 1px solid var(--academic-border);
  border-radius: 6px;
  background: var(--academic-canvas);
  color: var(--academic-text-main);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn:hover:not(.disabled) {
  background: var(--academic-primary);
  color: #fff;
  border-color: var(--academic-primary);
}

.nav-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.month-btn {
  padding: 6px 16px;
  border: 1px solid var(--academic-border);
  border-radius: 6px;
  background: var(--academic-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.month-btn:hover {
  opacity: 0.9;
}

.nav-arrow {
  font-size: 10px;
  transition: transform 0.2s;
}

.heatmap-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}

.heatmap-header {
  display: flex;
}

.weekday-labels {
  display: flex;
  gap: 3px;
}

.weekday-label {
  width: 32px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--academic-text-muted);
}

.heatmap-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.heatmap-row {
  display: flex;
  align-items: center;
}

.cells {
  display: flex;
  gap: 3px;
}

.cell {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}

.cell:hover {
  transform: scale(1.2);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  z-index: 10;
}

.cell.empty {
  background: transparent;
  cursor: default;
}

.cell.empty:hover {
  transform: none;
  box-shadow: none;
}

.month-summary {
  text-align: center;
  padding-top: 8px;
}

.summary-text {
  font-size: 13px;
  color: var(--academic-text-muted);
}

.calendar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.calendar-popup {
  background: #fff;
  border-radius: 12px;
  width: 360px;
  max-height: 500px;
  overflow-y: hidden;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
}

.calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--academic-border);
}

.calendar-header h4 {
  margin: 0;
  font-size: 16px;
  color: var(--academic-text-main);
}

.close-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 20px;
  cursor: pointer;
  border-radius: 4px;
}

.close-btn:hover {
  background: var(--academic-canvas);
}

.calendar-content {
  padding: 16px;
  max-height: 430px;
  overflow-y: auto;
}

.year-group {
  margin-bottom: 16px;
}

.year-group:last-child {
  margin-bottom: 0;
}

.year-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin-bottom: 8px;
}

.month-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.month-cell {
  padding: 10px;
  border: 1px solid var(--academic-border);
  border-radius: 6px;
  background: var(--academic-canvas);
  color: var(--academic-text-main);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.month-cell:hover {
  border-color: var(--academic-primary);
  color: var(--academic-primary);
}

.month-cell.disabled {
  background: #f5f7fa;
  color: #bbb;
  border-color: #e8ecf0;
  cursor: not-allowed;
}

.month-cell.disabled:hover {
  border-color: #e8ecf0;
  color: #bbb;
}

.month-cell.active {
  background: var(--academic-primary);
  color: #fff;
  border-color: var(--academic-primary);
}
</style>
