<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/papers'
import { featuresApi } from '@/api/features'
import { authApi } from '@/api/auth'
import * as echarts from 'echarts'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'

const router = useRouter()
const auth = useAuthStore()
const store = usePaperStore()
const user = auth.user!

const paperCount = ref(0)
const completedCount = ref(0)
const learningOverview = ref<any>(null)
const learningDuration = ref<any>(null)

const showPhoneModal = ref(false)
const showEmailModal = ref(false)
const showUsernameModal = ref(false)
const editUsername = ref('')

const usernameError = ref('')

const overview = ref<any>({ 
  paper_count:0, 
  report_count:0, 
  qa_count:0, 
  records:[], 
  recent_records:[],
  keyword_cloud: {},
  upload_heatmap: { months: [], data: {}, max_value: 1 },
  knowledge_domains: { count: 0, top_domains: [], tag_frequency: {}, cross_domain_rate: 0, total_papers: 0, cross_domain_papers: 0, sub_domain_granularity: 0 },
  deep_research_outputs: { reports: 0, comparisons: 0, graphs: 0 },
  question_traceability: { unique_paper_sources: 0 },
  keyword_evolution: { years: [], keywords: [] },
  recommended_domain: ''
})

const chartRef = ref<HTMLDivElement | null>(null)
const chartInstance = ref<echarts.ECharts | null>(null)

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

function validateUsername() {
  const name = editUsername.value.trim()
  if (!name) {
    usernameError.value = '请输入用户名'
    return false
  }
  if (name.length < 2) {
    usernameError.value = '用户名至少需要2个字符'
    return false
  }
  if (name.length > 20) {
    usernameError.value = '用户名最多20个字符'
    return false
  }
  usernameError.value = ''
  return true
}

function maskPhone(phone: string): string {
  if (!phone || phone.length < 7) return phone
  return phone.slice(0, 3) + '****' + phone.slice(-4)
}

async function updateUsername() {
  if (!validateUsername()) return
  const newName = editUsername.value.trim()
  try {
    await authApi.updateProfile({ username: newName })
    auth.user!.username = newName
    showUsernameModal.value = false
    editUsername.value = ''
    usernameError.value = ''
  } catch (error: any) {
    usernameError.value = error.response?.data?.detail || '修改失败'
  }
}

function renderStreamgraph() {
  if (!chartRef.value) return
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
  chartInstance.value = echarts.init(chartRef.value)

  const evolution = overview.value.keyword_evolution || { years: ['2024', '2025', '2026'], keywords: [] }
  const years = evolution.years
  const keywords = evolution.keywords.slice(0, 8)

  const series: any[] = keywords.map((kw: { keyword: string; data: { year: string; value: number }[] }, index: number) => ({
    name: kw.keyword,
    type: 'line',
    stack: 'total',
    smooth: true,
    lineStyle: { width: 0 },
    showSymbol: false,
    areaStyle: {
      opacity: 0.8,
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: colors[index % colors.length] },
        { offset: 1, color: colors[index % colors.length] + '20' }
      ])
    },
    emphasis: {
      focus: 'series'
    },
    data: kw.data.map((d: any) => d.value)
  }))

  chartInstance.value.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: {
          backgroundColor: '#6a7985'
        }
      },
      formatter: (params: any) => {
        let result = `<div style="font-weight:bold;margin-bottom:8px;">${years[params[0].dataIndex]}</div>`
        let total = 0
        params.forEach((p: any) => {
          total += p.value
          if (p.value > 0) {
            result += `<div style="display:flex;justify-content:space-between;gap:20px;margin:4px 0;">
              <span style="color:${p.color};">● ${p.seriesName}</span>
              <span style="font-weight:bold;">${p.value}</span>
            </div>`
          }
        })
        result += `<div style="border-top:1px solid #eee;margin-top:8px;padding-top:8px;font-weight:bold;">总计: ${total}</div>`
        return result
      }
    },
    legend: {
      data: keywords.map((kw: { keyword: string; data: { year: string; value: number }[] }) => kw.keyword),
      bottom: 0,
      textStyle: {
        fontSize: 12,
        color: '#64748b'
      },
      itemWidth: 12,
      itemHeight: 12
    },
    grid: {
      left: '3%',
      right: '4%',
      top: '8%',
      bottom: '20%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: years,
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#64748b', fontSize: 13 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
      axisLabel: { color: '#94a3b8', fontSize: 12 }
    },
    series
  })
}

// ============ 知识域覆盖雷达图模态框 ============
const showDomainModal = ref(false)
const selectedDomainIndex = ref(0)
const radarChartRef = ref<HTMLDivElement | null>(null)
const radarChartInstance = ref<echarts.ECharts | null>(null)

const domainList = computed(() => overview.value.knowledge_domains?.top_domains || [])
const selectedDomain = computed(() => domainList.value[selectedDomainIndex.value] || null)
const crossDomainRate = computed(() => overview.value.knowledge_domains?.cross_domain_rate || 0)
const crossDomainPapers = computed(() => overview.value.knowledge_domains?.cross_domain_papers || 0)
const totalDomainPapers = computed(() => overview.value.knowledge_domains?.total_papers || 0)
const subDomainGranularity = computed(() => overview.value.knowledge_domains?.sub_domain_granularity || 0)

function openDomainModal() {
  showDomainModal.value = true
  selectedDomainIndex.value = 0
  setTimeout(renderRadarChart, 100)
}

function selectDomain(index: number) {
  selectedDomainIndex.value = index
  setTimeout(renderRadarChart, 50)
}

function renderRadarChart() {
  if (!radarChartRef.value) return
  if (radarChartInstance.value) {
    radarChartInstance.value.dispose()
  }
  radarChartInstance.value = echarts.init(radarChartRef.value)

  const domain = selectedDomain.value
  if (!domain || !domain.sub_domains || domain.sub_domains.length === 0) {
    radarChartInstance.value.setOption({
      backgroundColor: 'transparent',
      title: {
        text: '暂无子领域数据',
        left: 'center',
        top: 'center',
        textStyle: { color: '#94a3b8', fontSize: 14, fontWeight: 'normal' }
      }
    })
    return
  }

  // 取前 8 个子领域，避免雷达图过于拥挤
  const subDomains = domain.sub_domains.slice(0, 8)
  const totalSubFreq = subDomains.reduce((sum: number, s: any) => sum + s.frequency, 0)

  // 计算每个子领域的相对占比（百分比）
  const indicators = subDomains.map((s: any) => ({
    name: s.name,
    max: 100
  }))

  const values = subDomains.map((s: any) => {
    const ratio = totalSubFreq > 0 ? (s.frequency / totalSubFreq) * 100 : 0
    return Number(ratio.toFixed(1))
  })

  // 主色：顶级学科频次越高用越饱和的蓝色
  const radarColors = ['#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316']
  const color = radarColors[selectedDomainIndex.value % radarColors.length]

  radarChartInstance.value.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const name = params.name
        const val = params.value
        let html = `<div style="font-weight:bold;margin-bottom:6px;color:${color};">${domain.name}</div>`
        if (Array.isArray(val)) {
          val.forEach((v: number, i: number) => {
            html += `<div style="display:flex;justify-content:space-between;gap:20px;margin:3px 0;">
              <span>${indicators[i].name}</span>
              <span style="font-weight:bold;">${v}%</span>
            </div>`
          })
        }
        return html
      }
    },
    radar: {
      indicator: indicators,
      shape: 'polygon',
      splitNumber: 5,
      center: ['50%', '52%'],
      radius: '68%',
      axisName: {
        color: '#475569',
        fontSize: 12,
        fontWeight: 500,
        formatter: (name: string) => {
          // 标签名过长则换行
          return name.length > 6 ? name.slice(0, 6) + '\n' + name.slice(6) : name
        }
      },
      splitLine: {
        lineStyle: { color: '#e2e8f0' }
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(99, 102, 241, 0.02)', 'rgba(99, 102, 241, 0.05)']
        }
      },
      axisLine: {
        lineStyle: { color: '#cbd5e1' }
      }
    },
    series: [{
      name: domain.name,
      type: 'radar',
      data: [{
        value: values,
        name: domain.name,
        areaStyle: {
          color: new echarts.graphic.RadialGradient(0.5, 0.5, 1, [
            { offset: 0, color: color + '40' },
            { offset: 1, color: color + '10' }
          ])
        },
        lineStyle: { color: color, width: 2 },
        itemStyle: { color: color },
        label: {
          show: false,
        }
      }]
    }]
  })
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
  const currentMonthNum = now.getMonth() + 1
  const maxMonth = year === currentYear ? currentMonthNum : 12
  for (let i = 1; i <= maxMonth; i++) {
    allMonths.push(i.toString().padStart(2, '0'))
  }
  return allMonths
}

onMounted(async () => {
  await store.load()
  paperCount.value = store.list.length
  completedCount.value = store.list.filter(p => p.parse_status === 'completed').length

  try {
    learningOverview.value = await featuresApi.overview()
  } catch { /* ignore */ }

  try {
    learningDuration.value = await authApi.getAllLearningDuration()
  } catch { /* ignore */ }

  try {
    overview.value = await featuresApi.overview()
    overview.value.records = overview.value.records || overview.value.recent_records || []
    setTimeout(renderStreamgraph, 100)
  } catch { /* ignore */ }
})

watch(() => overview.value.keyword_evolution, () => {
  setTimeout(renderStreamgraph, 50)
})

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="profile-page">
    <div class="main-content">
      <div class="learning-archive">
        <h2 class="page-title">学习档案</h2>

        <div class="stats-row-new">
          <div class="stat-card-new domain-card clickable" @click="openDomainModal">
            <div class="stat-header">
              <div class="stat-icon domain-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"/>
                  <line x1="12" y1="22" x2="12" y2="15.5"/>
                  <polyline points="22 8.5 12 15.5 2 8.5"/>
                  <polyline points="2 15.5 12 8.5 22 15.5"/>
                  <line x1="12" y1="2" x2="12" y2="8.5"/>
                </svg>
              </div>
              <div class="stat-title">知识域覆盖</div>
              <div class="click-hint">点击查看 →</div>
            </div>
            <div class="domain-stats-row">
              <div class="domain-stat-main">
                <div class="stat-value-large">{{ overview.knowledge_domains?.count || 0 }}</div>
                <div class="stat-label-large">顶级学科</div>
              </div>
              <div class="domain-stat-divider"></div>
              <div class="domain-stat-side">
                <div class="domain-side-value">{{ subDomainGranularity }}</div>
                <div class="domain-side-label">子领域细分</div>
              </div>
              <div class="domain-stat-divider"></div>
              <div class="domain-stat-side">
                <div class="domain-side-value">{{ (crossDomainRate * 100).toFixed(1) }}%</div>
                <div class="domain-side-label">跨学科触达</div>
              </div>
            </div>
            <div class="domain-list">
              <div v-for="domain in (overview.knowledge_domains?.top_domains || []).slice(0, 3)" :key="domain.name" class="domain-item">
                <span class="domain-dot"></span>
                <span class="domain-name">{{ domain.name }}</span>
                <span class="domain-freq">{{ domain.frequency }}篇 · {{ domain.sub_domain_count }}子领域</span>
              </div>
            </div>
          </div>

          <div class="stat-card-new output-card">
            <div class="stat-header">
              <div class="stat-icon output-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                  <polyline points="10 9 9 9 8 9"/>
                </svg>
              </div>
              <div class="stat-title">深度科研产出</div>
            </div>
            <div class="output-grid">
              <div class="output-item">
                <span class="output-icon-text">📝</span>
                <span class="output-value">{{ overview.deep_research_outputs?.reports || 0 }}</span>
                <span class="output-label">研读报告</span>
              </div>
              <div class="output-item">
                <span class="output-icon-text">🧠</span>
                <span class="output-value">{{ overview.deep_research_outputs?.comparisons || 0 }}</span>
                <span class="output-label">对比卡片</span>
              </div>
              <div class="output-item">
                <span class="output-icon-text">🗺️</span>
                <span class="output-value">{{ overview.deep_research_outputs?.graphs || 0 }}</span>
                <span class="output-label">知识图谱</span>
              </div>
            </div>
          </div>

          <div class="stat-card-new trace-card">
            <div class="stat-header">
              <div class="stat-icon trace-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/>
                  <circle cx="12" cy="12" r="4"/>
                  <line x1="12" y1="2" x2="12" y2="6"/>
                  <line x1="12" y1="18" x2="12" y2="22"/>
                  <line x1="4.93" y1="4.93" x2="7.07" y2="7.07"/>
                  <line x1="16.93" y1="16.93" x2="19.07" y2="19.07"/>
                  <line x1="2" y1="12" x2="6" y2="12"/>
                  <line x1="18" y1="12" x2="22" y2="12"/>
                  <line x1="6.01" y1="17.99" x2="4.99" y2="19.01"/>
                  <line x1="17.99" y1="6.01" x2="19.01" y2="4.99"/>
                </svg>
              </div>
              <div class="stat-title">提问溯源性</div>
            </div>
            <div class="stat-value-large">{{ overview.question_traceability?.unique_paper_sources || 0 }}</div>
            <div class="stat-label-large">来源</div>
            <div class="trace-chart">
              <div class="trace-ring">
                <div class="ring-inner"></div>
              </div>
            </div>
          </div>
        </div>

        <section class="grid2">
          <div class="card">
            <div class="card-header">
              <h3>知识域演进河流图</h3>
            </div>
            <div ref="chartRef" class="chart" />
            <div v-if="overview.recommended_domain" class="recommended-domain">
              <div class="recommend-icon">💡</div>
              <div class="recommend-content">
                <div class="recommend-label">AI推荐关联</div>
                <div class="recommend-domain">{{ overview.recommended_domain }}</div>
              </div>
            </div>
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
      </div>

      <div class="profile-sidebar">
        <div class="profile-card">
          <div class="avatar-circle">{{ user.username?.slice(0, 1)?.toUpperCase() }}</div>
          <div class="profile-info">
            <h2>{{ user.name || user.username }}</h2>
            <div class="meta-row">
              <span v-if="user.email">{{ user.email }}</span>
              <span v-if="user.phone">{{ maskPhone(user.phone) }}</span>
              <span>注册时间 {{ user.created_at ? new Date(user.created_at).toLocaleDateString('zh-CN') : '-' }}</span>
            </div>
          </div>
          <button class="logout-btn" @click="logout">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            退出登录
          </button>
        </div>

        <div class="section">
          <h3>学习概览</h3>
        </div>

        <div class="stats-row">
          <div class="stat-card-small">
            <div class="stat-value">{{ paperCount }}</div>
            <div class="stat-label">上传文献</div>
          </div>
          <div class="stat-card-small">
            <div class="stat-value">{{ completedCount }}</div>
            <div class="stat-label">已解析</div>
          </div>
        </div>

        <div v-if="learningOverview || learningDuration" class="section">
          <div class="overview-grid">
            <div class="kv"><span>连续学习</span><b>{{ learningOverview?.streak_days || 0 }} 天</b></div>
            <div class="kv"><span>今日学习</span><b>{{ learningDuration?.today || learningOverview?.today_minutes || 0 }} 分钟</b></div>
          </div>
        </div>

        <div class="section">
          <h3>帐号信息</h3>
          <div class="info-list">
            <div class="info-row">
              <span>用户名</span>
              <div class="info-right">
                <b>{{ user.username }}</b>
                <button class="edit-btn" @click="editUsername = user.username; showUsernameModal = true" title="编辑用户名">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
                </button>
              </div>
            </div>
            <div class="info-row">
              <span>邮箱</span>
              <div class="info-right">
                <b>{{ user.email || '未设置' }}</b>
                <button class="arrow-btn" @click="showEmailModal = true">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </button>
              </div>
            </div>
            <div class="info-row">
              <span>手机</span>
              <div class="info-right">
                <b>{{ user.phone ? maskPhone(user.phone) : '未设置' }}</b>
                <button class="arrow-btn" @click="showPhoneModal = true">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showPhoneModal" class="modal-overlay" @click="showPhoneModal = false">
        <div class="modal-content" @click.stop>
          <h4>手机号码</h4>
          <p>{{ maskPhone(user.phone || '') }}</p>
          <button class="modal-close" @click="showPhoneModal = false">关闭</button>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showEmailModal" class="modal-overlay" @click="showEmailModal = false">
        <div class="modal-content" @click.stop>
          <h4>邮箱</h4>
          <p>{{ user.email || '未设置' }}</p>
          <button class="modal-close" @click="showEmailModal = false">关闭</button>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showUsernameModal" class="modal-overlay" @click="showUsernameModal = false">
        <div class="modal-content" @click.stop>
          <h4>编辑用户名</h4>
          <input v-model="editUsername" type="text" class="modal-input" placeholder="请输入用户名" maxlength="20" @input="validateUsername" />
          <span v-if="usernameError" class="modal-error">{{ usernameError }}</span>
          <div class="modal-actions">
            <button class="modal-cancel" @click="showUsernameModal = false">取消</button>
            <button class="modal-confirm" @click="updateUsername">确认</button>
          </div>
        </div>
      </div>
    </Teleport>

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

    <Teleport to="body">
      <div v-if="showDomainModal" class="domain-modal-overlay" @click="showDomainModal = false">
        <div class="domain-modal-popup" @click.stop>
          <div class="domain-modal-header">
            <div class="domain-modal-title">
              <span class="domain-modal-icon">🎯</span>
              <div>
                <h4>知识域覆盖详情</h4>
                <p>基于 {{ totalDomainPapers }} 篇文献的学科标签分析</p>
              </div>
            </div>
            <button class="close-btn" @click="showDomainModal = false">×</button>
          </div>

          <div class="domain-modal-body">
            <aside class="domain-sidebar">
              <div class="sidebar-title">顶级学科</div>
              <button
                v-for="(domain, index) in domainList"
                :key="domain.name"
                class="domain-side-item"
                :class="{ active: selectedDomainIndex === index }"
                @click="selectDomain(index)"
              >
                <div class="domain-side-name">{{ domain.name }}</div>
                <div class="domain-side-meta">
                  <span>{{ domain.frequency }}篇</span>
                  <span class="dot-sep">·</span>
                  <span>{{ domain.sub_domain_count }}子领域</span>
                </div>
              </button>
            </aside>

            <section class="domain-main">
              <div v-if="selectedDomain" class="radar-section">
                <div class="radar-header">
                  <h5>{{ selectedDomain.name }} · 子领域分布</h5>
                </div>
                <div ref="radarChartRef" class="radar-chart"></div>

                <div class="sub-domain-table">
                  <div class="table-header">
                    <span>子领域</span>
                    <span>频次</span>
                    <span>占比</span>
                  </div>
                  <div
                    v-for="sub in selectedDomain.sub_domains"
                    :key="sub.name"
                    class="table-row"
                  >
                    <span class="sub-name">{{ sub.name }}</span>
                    <span class="sub-freq">{{ sub.frequency }}</span>
                    <span class="sub-ratio">{{ ((sub.frequency / selectedDomain.sub_domains.reduce((s: number, x: any) => s + x.frequency, 0)) * 100).toFixed(1) }}%</span>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <div class="domain-modal-footer">
            <div class="footer-stat">
              <span class="footer-label">顶级学科数</span>
              <span class="footer-value">{{ overview.knowledge_domains?.count || 0 }}</span>
            </div>
            <div class="footer-stat">
              <span class="footer-label">子领域细分</span>
              <span class="footer-value">{{ subDomainGranularity }}</span>
            </div>
            <div class="footer-stat">
              <span class="footer-label">跨学科触达率</span>
              <span class="footer-value">{{ (crossDomainRate * 100).toFixed(1) }}%</span>
              <span class="footer-sub">({{ crossDomainPapers }}/{{ totalDomainPapers }} 篇)</span>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.profile-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.main-content {
  flex: 1;
  display: flex;
  gap: 24px;
  padding: 24px 32px;
  overflow-y: auto;
}

.learning-archive {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.profile-sidebar {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--academic-text-main);
  margin: 0;
}

.stats-row-new {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stat-card-new {
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 18px;
  padding: 24px;
}

.stat-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.domain-icon {
  background: linear-gradient(135deg, #6366f115, #8b5cf615);
  color: #6366f1;
}

.output-icon {
  background: linear-gradient(135deg, #ec489915, #f43f5e15);
  color: #ec4899;
}

.trace-icon {
  background: linear-gradient(135deg, #22c55e15, #14b8a615);
  color: #22c55e;
}

.stat-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--academic-text-main);
}

.stat-value-large {
  font-size: 42px;
  font-weight: 800;
  color: var(--academic-primary);
  margin-bottom: 4px;
}

.stat-label-large {
  font-size: 13px;
  color: var(--academic-text-muted);
  margin-bottom: 16px;
}

.domain-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.domain-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.domain-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--academic-primary);
  flex-shrink: 0;
}

.domain-name {
  font-size: 13px;
  color: var(--academic-text-body);
}

.domain-freq {
  font-size: 11px;
  color: var(--academic-text-muted);
  background: var(--academic-canvas);
  padding: 2px 6px;
  border-radius: 4px;
}

.clickable {
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
  position: relative;
}

.clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.15);
  border-color: var(--academic-primary);
}

.click-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--academic-primary);
  font-weight: 600;
  opacity: 0.7;
}

.clickable:hover .click-hint {
  opacity: 1;
}

.domain-stats-row {
  display: flex;
  align-items: stretch;
  gap: 12px;
  margin-bottom: 16px;
}

.domain-stat-main {
  flex: 0 0 auto;
}

.domain-stat-side {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.domain-stat-divider {
  width: 1px;
  background: var(--academic-border);
  margin: 4px 0;
}

.domain-side-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--academic-text-main);
  line-height: 1.2;
}

.domain-side-label {
  font-size: 11px;
  color: var(--academic-text-muted);
  margin-top: 2px;
}

.output-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.output-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  background: var(--academic-canvas);
  border-radius: 12px;
}

.output-icon-text {
  font-size: 20px;
}

.output-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--academic-text-main);
}

.output-label {
  font-size: 11px;
  color: var(--academic-text-muted);
}

.trace-chart {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}

.trace-ring {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: conic-gradient(#22c55e 60%, #e2e8f0 60%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.ring-inner {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--academic-panel);
}

.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  flex: 1;
  min-height: 0;
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

.chart {
  height: 340px;
  flex: 1;
  min-height: 0;
}

.recommended-domain {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border-radius: 12px;
  margin-top: 12px;
}

.recommend-icon {
  font-size: 20px;
}

.recommend-content {
  flex: 1;
}

.recommend-label {
  font-size: 12px;
  color: #92400e;
  margin-bottom: 2px;
}

.recommend-domain {
  font-size: 14px;
  font-weight: 600;
  color: #78350f;
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

.profile-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px;
  border-radius: 22px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  box-shadow: var(--shadow-soft);
}

.avatar-circle {
  width: 64px;
  height: 64px;
  border-radius: 20px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--academic-primary), var(--academic-primary-hover));
  color: #fff;
  font-size: 26px;
  font-weight: 800;
  flex-shrink: 0;
}

.profile-info {
  text-align: center;
}

.profile-info h2 {
  margin: 0;
  font-size: 20px;
  color: var(--academic-text-main);
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--academic-text-muted);
  justify-content: center;
}

.logout-btn {
  padding: 10px 18px;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s;
  flex-shrink: 0;
}

.logout-btn:hover {
  background: rgba(239, 68, 68, 0.06);
  color: var(--danger);
  border-color: var(--danger);
}

.section {
  margin-bottom: 8px;
}

.section h3 {
  font-size: 15px;
  color: var(--academic-text-main);
  margin: 0 0 12px;
  font-weight: 600;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 8px;
}

.stat-card-small {
  padding: 16px;
  border-radius: 14px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  text-align: center;
  box-shadow: var(--shadow-soft);
}

.stat-value {
  font-size: 24px;
  font-weight: 800;
  color: var(--academic-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--academic-text-muted);
  margin-top: 4px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.kv {
  padding: 14px 18px;
  border-radius: 14px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
}

.kv span {
  font-size: 12px;
  color: var(--academic-text-muted);
  display: block;
}

.kv b {
  font-size: 18px;
  color: var(--academic-text-main);
  margin-top: 2px;
  display: block;
}

.info-list {
  border-radius: 16px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  overflow: hidden;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid var(--academic-border);
}

.info-row:last-child {
  border-bottom: none;
}

.info-row span {
  font-size: 13px;
  color: var(--academic-text-muted);
}

.info-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-right b {
  font-size: 13px;
  color: var(--academic-text-body);
  font-weight: 500;
}

.edit-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.edit-btn:hover {
  color: var(--academic-primary);
  background: var(--academic-primary-light);
}

.arrow-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.arrow-btn:hover {
  color: var(--academic-primary);
  background: var(--academic-primary-light);
}

.modal-overlay {
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

.modal-content {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  min-width: 280px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
}

.modal-content h4 {
  margin: 0 0 16px;
  font-size: 16px;
  color: var(--academic-text-main);
}

.modal-content p {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--academic-text-body);
}

.modal-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  font-size: 14px;
  margin-bottom: 8px;
  box-sizing: border-box;
}

.modal-error {
  display: block;
  color: #ef4444;
  font-size: 12px;
  margin-bottom: 16px;
}

.modal-input:focus {
  outline: none;
  border-color: var(--academic-primary);
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.modal-close, .modal-cancel {
  padding: 8px 16px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: #fff;
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
}

.modal-close:hover, .modal-cancel:hover {
  background: var(--academic-canvas);
}

.modal-confirm {
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: var(--academic-primary);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.modal-confirm:hover {
  background: var(--academic-primary-hover);
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

.month-cell.active {
  background: var(--academic-primary);
  color: #fff;
  border-color: var(--academic-primary);
}

/* ============ 知识域覆盖雷达图模态框 ============ */
.domain-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: domainFadeIn 0.2s ease;
}

@keyframes domainFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.domain-modal-popup {
  background: #fff;
  border-radius: 18px;
  width: 880px;
  max-width: 92vw;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.25);
  overflow: hidden;
  animation: domainSlideUp 0.25s ease;
}

@keyframes domainSlideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.domain-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--academic-border);
  background: linear-gradient(135deg, #6366f108, #8b5cf608);
}

.domain-modal-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.domain-modal-icon {
  font-size: 28px;
}

.domain-modal-title h4 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--academic-text-main);
}

.domain-modal-title p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--academic-text-muted);
}

.domain-modal-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.domain-sidebar {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--academic-border);
  padding: 16px 12px;
  overflow-y: auto;
  background: #fafbfc;
}

.sidebar-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0 8px 12px;
}

.domain-side-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  margin-bottom: 6px;
  transition: all 0.15s;
  font-family: inherit;
}

.domain-side-item:hover {
  background: #fff;
  border-color: var(--academic-border);
}

.domain-side-item.active {
  background: #fff;
  border-color: var(--academic-primary);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.12);
}

.domain-side-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--academic-text-main);
}

.domain-side-item.active .domain-side-name {
  color: var(--academic-primary);
}

.domain-side-meta {
  font-size: 11px;
  color: var(--academic-text-muted);
  display: flex;
  gap: 4px;
  align-items: center;
}

.dot-sep {
  opacity: 0.6;
}

.domain-main {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

.radar-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.radar-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.radar-header h5 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--academic-text-main);
}

.radar-hint {
  font-size: 11px;
  color: var(--academic-text-muted);
}

.radar-chart {
  width: 100%;
  height: 360px;
}

.sub-domain-table {
  border: 1px solid var(--academic-border);
  border-radius: 10px;
  overflow: hidden;
  font-size: 13px;
}

.table-header,
.table-row {
  display: grid;
  grid-template-columns: 1fr 80px 80px;
  padding: 10px 14px;
  align-items: center;
}

.table-header {
  background: #f8fafc;
  font-size: 11px;
  font-weight: 700;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.table-row {
  border-top: 1px solid var(--academic-border);
  color: var(--academic-text-body);
}

.table-row:hover {
  background: #f8fafc;
}

.sub-name {
  font-weight: 500;
  color: var(--academic-text-main);
}

.sub-freq {
  color: var(--academic-text-body);
  text-align: right;
}

.sub-ratio {
  color: var(--academic-primary);
  font-weight: 600;
  text-align: right;
}

.domain-modal-footer {
  display: flex;
  gap: 0;
  padding: 16px 24px;
  border-top: 1px solid var(--academic-border);
  background: #fafbfc;
}

.footer-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 16px;
  border-right: 1px solid var(--academic-border);
}

.footer-stat:last-child {
  border-right: none;
}

.footer-label {
  font-size: 11px;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.footer-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--academic-primary);
  line-height: 1.2;
}

.footer-sub {
  font-size: 11px;
  color: var(--academic-text-muted);
}
</style>