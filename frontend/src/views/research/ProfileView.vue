<script setup lang="ts">
import { onMounted, ref, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/papers'
import { featuresApi } from '@/api/features'
import { authApi } from '@/api/auth'
import * as echarts from 'echarts'
import MarkdownIt from 'markdown-it'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'

const md = new MarkdownIt({ breaks: true, html: false })

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
const showPasswordModal = ref(false)
const sidebarCollapsed = ref(false)
const heatmapMode = ref<'upload' | 'focus'>('upload')
const reportLoading = ref(false)
const reportLoadingText = ref('正在生成报告...')
const monthlyReportData = ref<any>(null)
const reportSummaryRef = ref<HTMLElement | null>(null)
const loadingPhrases = [
  'AI 正在翻阅你本月挑灯夜读的文献...',
  '正在分析你的知识图谱结构...',
  '复盘本月科研问答记录中...',
  '提炼你的研究脉络与进展...',
  '正在生成个性化学习建议...',
  '马上就好，AI正在推敲措辞...',
]
const editUsername = ref('')
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordError = ref('')
const usernameError = ref('')

const overview = ref<any>({ 
  paper_count:0, 
  report_count:0, 
  qa_count:0, 
  records:[], 
  recent_records:[],
  keyword_cloud: {},
  upload_heatmap: { months: [], data: {}, max_value: 1 },
  focus_heatmap: { months: [], data: {}, max_value: 1 },
  knowledge_domains: { count: 0, top_domains: [], tag_frequency: {}, cross_domain_rate: 0, total_papers: 0, cross_domain_papers: 0, sub_domain_granularity: 0 },
  deep_research_outputs: { reports: 0, comparisons: 0, graphs: 0 },
  question_traceability: { unique_paper_sources: 0 },
  keyword_evolution: { years: [], keywords: [] },
  recommended_domain: ''
})

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

async function updatePassword() {
  if (!oldPassword.value) {
    passwordError.value = '请输入旧密码'
    return
  }
  if (!newPassword.value) {
    passwordError.value = '请输入新密码'
    return
  }
  if (newPassword.value.length < 6) {
    passwordError.value = '新密码长度至少为6位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = '两次输入的密码不一致'
    return
  }
  passwordError.value = ''
  try {
    await authApi.changePassword({ old_password: oldPassword.value, new_password: newPassword.value })
    showPasswordModal.value = false
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (error: any) {
    passwordError.value = error.response?.data?.detail || '修改失败'
  }
}

// ============ 学科覆盖雷达图模态框 ============
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

  const subDomains = domain.sub_domains.slice(0, 8)
  const maxFreq = Math.max(...subDomains.map((s: any) => s.frequency), 1)

  const radarColors = ['#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316']
  const color = domain.is_interdisciplinary ? '#8b5cf6' : radarColors[selectedDomainIndex.value % radarColors.length]

  if (domain.is_interdisciplinary) {
    const count = subDomains.length
    const allSubDomains = subDomains

    const minF = Math.min(...allSubDomains.map((s: any) => s.frequency))
    const maxF = maxFreq
    const freqRange = maxF - minF || 1

    const scatterData = allSubDomains.map((sd: any, i: number) => {
      const baseAngle = (i / count) * 360
      const angleJitter = (Math.random() - 0.5) * 40
      const angle = (baseAngle + angleJitter + 360) % 360

      const freqRatio = (sd.frequency - minF) / freqRange
      const radiusBase = 75 - freqRatio * 50
      const stagger = (i % 3) * 4
      const radius = Math.max(22, Math.min(78, radiusBase + stagger))

      const size = Math.max(6, Math.min(18, sd.frequency * 2.5 + 6))

      return {
        value: [radius, angle],
        name: sd.name,
        symbolSize: size,
        frequency: sd.frequency,
        papers: sd.papers || []
      }
    })

    radarChartInstance.value.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          const name = params.name
          if (!name || name === '用户') return ''
          const data = params.data || {}
          const freq = data.frequency
          const papers: string[] = data.papers || []
          let html = `<div style="font-weight:600;font-size:13px;margin-bottom:4px;">${name}</div>`
          if (freq != null) {
            html += `<div style="color:#8b5cf6;font-weight:600;font-size:12px;margin-bottom:${papers.length > 0 ? '6px' : '0'};">${freq}篇</div>`
          }
          if (papers.length > 0) {
            const list = papers.slice(0, 8).map((t: string) =>
              `<div style="padding:2px 0;font-size:12px;color:#475569;border-bottom:1px solid #f1f5f9;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">· ${t}</div>`
            ).join('')
            html += `<div style="margin-top:2px;">${list}</div>`
          }
          return html
        }
      },
      polar: {
        center: ['50%', '50%'],
        radius: '88%',
        axisLine: {
          show: true,
          lineStyle: { color: '#e2e8f0', width: 1 }
        },
        splitLine: {
          show: true,
          lineStyle: { color: '#e2e8f0', type: 'dashed', width: 1 }
        },
        splitArea: {
          show: true,
          areaStyle: {
            color: ['rgba(139, 92, 246, 0.02)', 'rgba(139, 92, 246, 0.04)', 'rgba(139, 92, 246, 0.06)', 'rgba(139, 92, 246, 0.08)', 'rgba(139, 92, 246, 0.1)']
          }
        }
      },
      angleAxis: {
        type: 'value',
        min: 0,
        max: 360,
        show: false
      },
      radiusAxis: {
        type: 'value',
        min: 0,
        max: 100,
        show: false
      },
      series: [
        {
          name: '用户',
          type: 'scatter',
          coordinateSystem: 'polar',
          data: [{
            value: [0, 0],
            name: '用户',
            symbol: 'circle',
            symbolSize: 18,
            itemStyle: {
              color: '#8b5cf6',
              borderColor: '#fff',
              borderWidth: 3,
              shadowBlur: 10,
              shadowColor: 'rgba(139, 92, 246, 0.4)'
            },
            label: {
              show: true,
              formatter: '用户',
              color: '#8b5cf6',
              fontSize: 11,
              fontWeight: 600,
              offset: [0, 14]
            }
          }],
          z: 20
        },
        {
          name: domain.name,
          type: 'scatter',
          coordinateSystem: 'polar',
          data: scatterData,
          symbol: 'circle',
          itemStyle: {
            color: '#8b5cf6',
            borderColor: '#fff',
            borderWidth: 2,
            shadowBlur: 8,
            shadowColor: 'rgba(139, 92, 246, 0.4)'
          },
          label: {
            show: true,
            position: 'bottom',
            formatter: (params: any) => params.name,
            color: '#475569',
            fontSize: 11,
            fontWeight: 500,
            distance: 4
          },
          emphasis: {
            scale: true,
            itemStyle: {
              shadowBlur: 18,
              shadowColor: 'rgba(139, 92, 246, 0.6)',
              borderWidth: 3
            },
            label: {
              fontSize: 12,
              fontWeight: 600
            }
          },
          z: 10
        }
      ]
    })
    return
  }

  const indicators = subDomains.map((s: any) => ({
    name: s.name,
    max: maxFreq
  }))

  const values = subDomains.map((s: any) => s.frequency)

  if (indicators.length < 3) {
    const placeholders = ['基础理论', '应用技术', '交叉研究']
    let added = 0
    for (const ph of placeholders) {
      if (indicators.length >= 3) break
      if (!indicators.find((i: any) => i.name === ph)) {
        indicators.push({ name: ph, max: maxFreq })
        values.push(0)
        added++
      }
    }
  }

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
            if (i >= subDomains.length) return
            html += `<div style="display:flex;justify-content:space-between;gap:20px;margin:3px 0;">
              <span>${indicators[i].name}</span>
              <span style="font-weight:bold;">${v}篇</span>
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

const currentHeatmap = computed(() => 
  heatmapMode.value === 'upload' 
    ? overview.value.upload_heatmap 
    : overview.value.focus_heatmap
)

const heatmapRows = computed(() => {
  const data = currentHeatmap.value?.data || {}
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
  const maxValue = currentHeatmap.value?.max_value || 1
  if (count === 0) return '#e8f4fd'
  if (count <= Math.ceil(maxValue * 0.25)) return '#a5d8ff'
  if (count <= Math.ceil(maxValue * 0.5)) return '#69c0ff'
  if (count <= Math.ceil(maxValue * 0.75)) return '#2f80ed'
  return '#1971c2'
}

const currentMonthTotal = computed(() => {
  const data = currentHeatmap.value?.data || {}
  const monthData = data[currentMonth.value] || []
  return monthData.reduce((sum: number, count: number) => sum + count, 0)
})

const heatmapUnit = computed(() => heatmapMode.value === 'upload' ? '篇' : '分钟')

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
  } catch { /* ignore */ }
})

const renderedReportSummary = computed(() => {
  const summary = monthlyReportData.value?.summary
  if (!summary) return ''
  try {
    return md.render(summary)
  } catch {
    return summary.replace(/\n/g, '<br/>')
  }
})

async function generateMonthlyReport() {
  reportLoading.value = true
  monthlyReportData.value = null

  // 滚动加载文案
  const phraseInterval = setInterval(() => {
    const idx = Math.floor(Math.random() * loadingPhrases.length)
    reportLoadingText.value = loadingPhrases[idx]
  }, 2000)
  reportLoadingText.value = loadingPhrases[0]

  try {
    const result = await featuresApi.monthlyReport(currentMonth.value)
    monthlyReportData.value = result
    await nextTick()
    if (reportSummaryRef.value) {
      reportSummaryRef.value.scrollTop = 0
    }
  } catch (error: any) {
    console.error('生成月度报告失败:', error)
    monthlyReportData.value = {
      summary: '报告生成失败：' + (error?.response?.data?.detail || error?.message || '未知错误'),
    }
  } finally {
    clearInterval(phraseInterval)
    reportLoading.value = false
  }
}

function exportReport(format: 'md' | 'txt') {
  const summary = monthlyReportData.value?.summary
  if (!summary) return
  const month = monthlyReportData.value?.month || currentMonth.value

  let content: string
  let mimeType: string
  let ext: string
  if (format === 'md') {
    content = summary
    mimeType = 'text/markdown'
    ext = 'md'
  } else {
    // strip markdown for txt
    content = summary.replace(/[#*_`>~\[\]()|]/g, '')
    mimeType = 'text/plain'
    ext = 'txt'
  }

  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `月度科研学习报告_${month}.${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

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
              <div class="stat-title">学科覆盖</div>
              <div class="click-hint">点击查看 →</div>
            </div>
            <div class="domain-stats-row">
              <div class="domain-stat-main">
                <div class="stat-value-large">{{ overview.knowledge_domains?.count || 0 }}</div>
                <div class="stat-label-large">学科领域</div>
              </div>
              <div class="domain-stat-divider"></div>
              <div class="domain-stat-side">
                <div class="domain-side-value">{{ subDomainGranularity }}</div>
                <div class="domain-side-label">子领域细分</div>
              </div>
              <div class="domain-stat-divider"></div>
              <div class="domain-stat-side">
                <div class="domain-side-value">{{ (crossDomainRate * 100).toFixed(1) }}%</div>
                <div class="domain-side-label">领域跨度</div>
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
                <span class="output-value">{{ overview.deep_research_outputs?.reports || 0 }}</span>
                <span class="output-label">研读报告</span>
              </div>
              <div class="output-item">
                <span class="output-value">{{ overview.deep_research_outputs?.comparisons || 0 }}</span>
                <span class="output-label">对比卡片</span>
              </div>
              <div class="output-item">
                <span class="output-value">{{ overview.deep_research_outputs?.graphs || 0 }}</span>
                <span class="output-label">知识图谱</span>
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
              <div class="stat-title">学习成果</div>
            </div>
            <div class="output-grid">
              <div class="output-item">
                <span class="output-value">{{ learningDuration?.today || learningOverview?.today_minutes || 0 }}</span>
                <span class="output-label">今日专注时长</span>
              </div>
              <div class="output-item">
                <span class="output-value">{{ overview.knowledge_domains?.core_papers || 0 }}</span>
                <span class="output-label">累计解析文献</span>
              </div>
              <div class="output-item">
                <span class="output-value">{{ overview.knowledge_domains?.count || 0 }}</span>
                <span class="output-label">学科覆盖</span>
              </div>
            </div>
          </div>
        </div>

        <section class="grid2">
          <div class="card monthly-report-card">
            <div class="card-header">
              <div class="header-top">
                <h3>月度科研学习报告</h3>
                <div v-if="monthlyReportData?.summary" class="report-header-actions">
                  <button class="export-btn" @click="exportReport('md')">导出 MD</button>
                  <button class="export-btn" @click="exportReport('txt')">导出 TXT</button>
                </div>
              </div>
            </div>
            <div class="monthly-report-body">
              <p class="report-desc">综合本月上传文献、研读报告、知识图谱、问答数据，自动生成 AI 总结</p>

              <!-- 未生成状态 -->
              <div v-if="!monthlyReportData?.summary && !reportLoading" class="report-empty-state">
                <!-- 数据源概览 -->
                <div class="report-sources">
                  <div class="report-source-item">
                    <span class="source-icon">📄</span>
                    <span class="source-value">{{ monthlyReportData?.paper_count ?? overview.paper_count ?? 0 }}篇</span>
                    <span class="source-label">上传文献</span>
                  </div>
                  <div class="report-source-item">
                    <span class="source-icon">📊</span>
                    <span class="source-value">{{ monthlyReportData?.report_count ?? overview.report_count ?? 0 }}份</span>
                    <span class="source-label">研读报告</span>
                  </div>
                  <div class="report-source-item">
                    <span class="source-icon">🔗</span>
                    <span class="source-value">{{ monthlyReportData?.graph_count ?? overview.deep_research_outputs?.graphs ?? 0 }}个</span>
                    <span class="source-label">知识图谱</span>
                  </div>
                  <div class="report-source-item">
                    <span class="source-icon">💬</span>
                    <span class="source-value">{{ monthlyReportData?.qa_count ?? overview.qa_count ?? 0 }}次</span>
                    <span class="source-label">AI问答</span>
                  </div>
                </div>

                <!-- 生成按钮 -->
                <button
                  class="generate-report-btn"
                  :disabled="reportLoading"
                  @click="generateMonthlyReport"
                >
                  <svg v-if="reportLoading" class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10" opacity="0.25" />
                    <path d="M12 2a10 10 0 019.95 9" />
                  </svg>
                  {{ reportLoading ? reportLoadingText : '生成本月报告' }}
                </button>
              </div>

              <!-- 加载状态 -->
              <div v-else-if="reportLoading" class="report-loading">
                <svg class="spinner-large" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10" opacity="0.25" />
                  <path d="M12 2a10 10 0 019.95 9" />
                </svg>
                <p class="loading-text">{{ reportLoadingText }}</p>
              </div>

              <!-- AI总结结果 -->
              <div v-else class="report-summary">
                <div class="report-summary-content" ref="reportSummaryRef" v-html="renderedReportSummary"></div>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <div class="header-top">
                <h3>热力图</h3>
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
            </div>
            <div class="heatmap-container">
              <div class="heatmap-toggle">
                <button 
                  class="toggle-btn" 
                  :class="{ active: heatmapMode === 'upload' }"
                  @click="heatmapMode = 'upload'"
                >文献上传</button>
                <button 
                  class="toggle-btn" 
                  :class="{ active: heatmapMode === 'focus' }"
                  @click="heatmapMode = 'focus'"
                >专注时间</button>
              </div>
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
                      :title="cell.date ? `${cell.date}: ${cell.count} ${heatmapUnit}` : ''"
                    ></div>
                  </div>
                </div>
              </div>
              <div class="month-summary">
                <span class="summary-text">{{ currentMonth }} 共{{ heatmapMode === 'upload' ? '上传' : '专注' }} {{ currentMonthTotal }} {{ heatmapUnit }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="profile-sidebar" :class="{ collapsed: sidebarCollapsed }">
        <button class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开' : '收起'">
          <svg v-if="sidebarCollapsed" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </button>

        <div class="sidebar-content">
          <div class="profile-card">
            <div class="avatar-wrapper">
              <div class="avatar-box">{{ user.username?.slice(0, 1)?.toUpperCase() }}</div>
            </div>
            <div class="profile-info">
              <h2>{{ user.name || user.username }}</h2>
              <div class="research-tags">
                <span v-for="tag in overview.research_interests?.slice(0, 3) || []" :key="tag" class="research-tag">{{ tag }}</span>
              </div>
            </div>
          </div>

          <div class="sidebar-section">
            <h3>账号设置</h3>
            <div class="settings-list">
              <div class="settings-item" @click="editUsername = user.username; showUsernameModal = true">
                <span class="settings-label">用户名</span>
                <div class="settings-right">
                  <span>{{ user.username }}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
                </div>
              </div>
              <div class="settings-item" @click="showEmailModal = true">
                <span class="settings-label">邮箱</span>
                <div class="settings-right">
                  <span>{{ user.email || '未设置' }}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </div>
              </div>
              <div class="settings-item" @click="showPhoneModal = true">
                <span class="settings-label">手机</span>
                <div class="settings-right">
                  <span>{{ user.phone ? maskPhone(user.phone) : '未设置' }}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </div>
              </div>
              <div class="settings-item" @click="showPasswordModal = true">
                <span class="settings-label">修改密码</span>
                <div class="settings-right">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </div>
              </div>
              <div class="settings-item logout-item" @click="logout">
                <span class="settings-label">退出登录</span>
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
      <div v-if="showPasswordModal" class="modal-overlay" @click.self="showPasswordModal = false">
        <div class="modal-content" @click.stop>
          <h4>修改密码</h4>
          <div class="pwd-field">
            <label>旧密码</label>
            <input v-model="oldPassword" type="password" class="modal-input" placeholder="请输入旧密码" />
          </div>
          <div class="pwd-field">
            <label>新密码</label>
            <input v-model="newPassword" type="password" class="modal-input" placeholder="请输入新密码（至少6位）" />
          </div>
          <div class="pwd-field">
            <label>确认新密码</label>
            <input v-model="confirmPassword" type="password" class="modal-input" placeholder="请再次输入新密码" />
          </div>
          <span v-if="passwordError" class="modal-error">{{ passwordError }}</span>
          <div class="modal-actions">
            <button class="modal-cancel" @click="showPasswordModal = false">取消</button>
            <button class="modal-confirm" @click="updatePassword">确认修改</button>
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
              <div>
                <h4>学科覆盖详情</h4>
                <p>基于 {{ totalDomainPapers }} 篇文献的学科标签分析</p>
              </div>
            </div>
            <button class="close-btn" @click="showDomainModal = false">×</button>
          </div>

          <div class="domain-modal-body">
            <aside class="domain-sidebar">
              <div class="sidebar-title">学科领域</div>
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
                    <span class="header-right">频次</span>
                    <span class="header-right">占比</span>
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
              <span class="footer-label">领域跨度</span>
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
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
  align-self: flex-start;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.profile-sidebar.collapsed {
  width: 44px;
  gap: 0;
}

.sidebar-toggle {
  align-self: flex-end;
  padding: 8px;
  border: none;
  background: var(--academic-panel);
  border-radius: 8px;
  color: var(--academic-text-muted);
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.sidebar-toggle:hover {
  color: var(--academic-primary);
  background: var(--academic-border);
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 1200px;
  opacity: 1;
  overflow: hidden;
  transition: max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1),
              opacity 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.profile-sidebar.collapsed .sidebar-content {
  max-height: 0;
  opacity: 0;
  margin: 0;
  gap: 0;
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
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

/* ============ 月度科研学习报告 ============ */
.monthly-report-card .card-header {
  margin-bottom: 12px;
}

.report-header-actions {
  display: flex;
  gap: 8px;
}

.report-header-actions .export-btn {
  padding: 5px 14px;
  font-size: 12px;
}

.monthly-report-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  flex: 1;
  min-height: 0;
  justify-content: flex-start !important;
}

.report-desc {
  margin: 0;
  font-size: 13px;
  color: var(--academic-text-muted);
  line-height: 1.6;
  flex-shrink: 0;
}

.report-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  flex: 1;
  min-height: 0;
}

.report-sources {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  width: 100%;
}

.report-source-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 14px 8px;
  border-radius: 12px;
  background: var(--academic-canvas);
}

.source-icon {
  font-size: 22px;
}

.source-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--academic-text-main);
}

.source-label {
  font-size: 11px;
  color: var(--academic-text-muted);
}

.generate-report-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 32px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--academic-primary), var(--academic-primary-hover));
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 14px rgba(139, 92, 246, 0.3);
}

.generate-report-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(139, 92, 246, 0.4);
}

.generate-report-btn:disabled {
  opacity: 0.7;
  cursor: wait;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.report-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.spinner-large {
  animation: spin 1s linear infinite;
  color: var(--academic-primary);
  width: 36px;
  height: 36px;
}

.loading-text {
  margin: 0;
  font-size: 13px;
  color: var(--academic-text-muted);
  text-align: center;
  line-height: 1.6;
}

.report-summary {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.report-summary-content {
  font-size: 13px;
  color: var(--academic-text-body);
  line-height: 1.8;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 16px;
  background: var(--academic-canvas);
  border-radius: 10px;
  scrollbar-width: thin;
  scrollbar-color: var(--academic-border) transparent;
}

.report-summary-content::-webkit-scrollbar {
  width: 6px;
}

.report-summary-content::-webkit-scrollbar-track {
  background: transparent;
}

.report-summary-content::-webkit-scrollbar-thumb {
  background: var(--academic-border);
  border-radius: 3px;
}

.report-summary-content::-webkit-scrollbar-thumb:hover {
  background: var(--academic-text-muted);
}

.report-summary-content :deep(h2) {
  font-size: 15px;
  font-weight: 700;
  color: var(--academic-text-main);
  margin: 0 0 10px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--academic-primary);
  display: inline-block;
}

.report-summary-content :deep(h2):first-child {
  margin-top: 0;
}

.report-summary-content :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin: 14px 0 6px;
}

.report-summary-content :deep(h3):first-child {
  margin-top: 0;
}

.report-summary-content :deep(p) {
  margin: 8px 0;
  text-align: justify;
}

.report-summary-content :deep(ul),
.report-summary-content :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.report-summary-content :deep(li) {
  margin: 4px 0;
}

.report-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.export-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 18px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.export-btn:hover {
  border-color: var(--academic-primary);
  color: var(--academic-primary);
  background: rgba(139, 92, 246, 0.06);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(139, 92, 246, 0.1);
}

.heatmap-toggle {
  display: inline-flex;
  gap: 4px;
}

.toggle-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
}

.toggle-btn:hover {
  color: var(--academic-text-main);
}

.toggle-btn.active {
  background: var(--academic-primary);
  color: #fff;
  box-shadow: 0 4px 12px rgba(139, 92, 246, 0.35);
  transform: translateY(-1px);
}

.month-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.nav-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--academic-text-main);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn:hover:not(.disabled) {
  background: rgba(139, 92, 246, 0.1);
}

.nav-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.month-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  background: #fff;
  color: var(--academic-text-main);
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
  gap: 12px;
  align-items: center;
  padding: 16px;
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
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 24px;
  border-radius: 22px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}



.avatar-wrapper {
  position: relative;
  z-index: 1;
}

.avatar-box {
  width: 64px;
  height: 64px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--academic-primary), var(--academic-primary-hover));
  color: #fff;
  font-size: 26px;
  font-weight: 800;
  border: 3px solid var(--academic-panel);
  box-shadow: 0 4px 16px rgba(139, 92, 246, 0.3);
}

.profile-info {
  position: relative;
  z-index: 1;
  text-align: center;
}

.profile-info h2 {
  margin: 0;
  font-size: 20px;
  color: var(--academic-text-main);
}

.research-tags {
  display: flex;
  flex-wrap: nowrap;
  justify-content: center;
  gap: 5px;
  margin-top: 6px;
  overflow: hidden;
}

.research-tag {
  padding: 4px 10px;
  border-radius: 20px;
  white-space: nowrap;
  flex-shrink: 0;
  background-color: #f5f6fa;
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  color: var(--academic-text-body);
  font-size: 11px;
  font-weight: 500;
}

.sidebar-section {
  margin-top: 14px;
  padding: 16px 20px;
  border-radius: 16px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
}

.sidebar-section h3 {
  font-size: 14px;
  color: var(--academic-text-main);
  margin: 0 0 10px;
  font-weight: 600;
}

.settings-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.settings-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 0;
  cursor: pointer;
  transition: background 0.15s;
}

.settings-item:not(:last-child) {
  border-bottom: 1px solid var(--academic-border);
}

.settings-item:hover {
  background: rgba(139, 92, 246, 0.04);
  margin: 0 -16px;
  padding-left: 16px;
  padding-right: 16px;
  border-radius: 8px;
}

.settings-icon {
  font-size: 16px;
}

.settings-label {
  flex: 1;
  font-size: 13px;
  color: var(--academic-text-body);
}

.settings-right {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--academic-text-muted);
}

.logout-item {
  color: var(--danger);
}

.logout-item .settings-label {
  color: var(--danger);
}

.sidebar-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  margin-bottom: 8px;
}

.sidebar-stat-item {
  padding: 8px 8px;
  border-radius: 10px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  text-align: center;
}

.sidebar-stat-value {
  display: block;
  font-size: 19px;
  font-weight: 700;
  color: var(--academic-primary);
  line-height: 1.2;
}

.sidebar-stat-label {
  display: block;
  font-size: 10px;
  color: var(--academic-text-muted);
  margin-top: 1px;
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
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: modalFadeIn 0.2s ease;
}

@keyframes modalFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-content {
  background: #fff;
  border-radius: 16px;
  padding: 28px 32px;
  min-width: 420px;
  max-width: 480px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.18);
  animation: modalSlideUp 0.25s ease;
}

@keyframes modalSlideUp {
  from { transform: translateY(12px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.modal-content h4 {
  margin: 0 0 20px;
  font-size: 18px;
  color: var(--academic-text-main);
  font-weight: 700;
}

.modal-content p {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--academic-text-body);
}

.modal-input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid var(--academic-border);
  border-radius: 10px;
  font-size: 14px;
  margin-bottom: 10px;
  box-sizing: border-box;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.modal-textarea {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid var(--academic-border);
  border-radius: 10px;
  font-size: 14px;
  margin-bottom: 10px;
  box-sizing: border-box;
  resize: vertical;
  transition: border-color 0.2s, box-shadow 0.2s;
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
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.modal-textarea:focus {
  outline: none;
  border-color: var(--academic-primary);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 8px;
}

.modal-close, .modal-cancel {
  padding: 10px 22px;
  border: 1px solid var(--academic-border);
  border-radius: 10px;
  background: #fff;
  color: var(--academic-text-body);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.modal-close:hover, .modal-cancel:hover {
  background: var(--academic-canvas);
  border-color: #cbd5e1;
}

.modal-confirm {
  padding: 10px 22px;
  border: none;
  border-radius: 10px;
  background: var(--academic-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.modal-confirm:hover {
  background: var(--academic-primary-hover);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
}

.pwd-field {
  margin-bottom: 12px;
}

.pwd-field label {
  display: block;
  font-size: 13px;
  color: var(--academic-text-body);
  margin-bottom: 6px;
  font-weight: 500;
}

.pwd-field .modal-input {
  margin-bottom: 0;
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
  border: none;
  border-radius: 6px;
  background: var(--academic-canvas);
  color: var(--academic-text-main);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.month-cell:hover {
  background: rgba(139, 92, 246, 0.08);
  color: var(--academic-primary);
}

.month-cell.active {
  background: var(--academic-primary);
  color: #fff;
}

/* ============ 学科覆盖雷达图模态框 ============ */
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
  padding: 12px 14px;
  align-items: center;
  min-height: 44px;
}

.table-header {
  background: #f8fafc;
  font-size: 11px;
  font-weight: 700;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.header-right {
  text-align: right;
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
  display: flex;
  align-items: center;
  min-height: 24px;
}

.sub-freq {
  color: var(--academic-text-body);
  text-align: right;
  line-height: 24px;
}

.sub-ratio {
  color: var(--academic-primary);
  font-weight: 600;
  text-align: right;
  line-height: 24px;
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
