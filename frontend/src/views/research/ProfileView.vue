<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/papers'
import { featuresApi } from '@/api/features'
import { authApi } from '@/api/auth'
import { resolveAvatarUrl } from '@/utils/avatar'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import { CHART_COLORS } from '@/utils/graphColors'
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
const showPasswordModal = ref(false)
const heatmapMode = ref<'upload' | 'focus'>('upload')
const heatmapTooltip = ref({ visible: false, x: 0, y: 0, text: '' })
const reportLoading = ref(false)
const reportLoadingText = ref('正在生成报告...')
const monthlyReportData = ref<any>(null)
const reportSummaryRef = ref<HTMLElement | null>(null)
const loadingPhrases = [
  'AI 正在翻阅你最近挑灯夜读的文献...',
  '正在分析你的知识图谱结构...',
  '复盘近期科研问答记录中...',
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
const avatarInputRef = ref<HTMLInputElement | null>(null)
const avatarUploading = ref(false)
const avatarVersion = ref(0)

const avatarDisplayUrl = computed(() =>
  resolveAvatarUrl(auth.user, avatarVersion.value || undefined),
)

function triggerAvatarUpload() {
  if (avatarUploading.value) return
  avatarInputRef.value?.click()
}

async function onAvatarSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  if (!['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) {
    ElMessage.warning('仅支持 JPG、PNG、WebP、GIF 格式')
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.warning('头像不能超过 2MB')
    return
  }

  avatarUploading.value = true
  try {
    const res = await authApi.uploadAvatar(file)
    if (auth.user) auth.user.avatar_url = res.avatar_url
    avatarVersion.value = Date.now()
    ElMessage.success('头像已更新')
  } catch {
    /* 错误由 http 拦截器提示 */
  } finally {
    avatarUploading.value = false
  }
}

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

// ============ 学科覆盖雷达图 ============
const showDomainModal = ref(false)
const modalDomainIndex = ref(0)
const mainRoseChartRef = ref<HTMLDivElement | null>(null)
const mainRoseChartInstance = ref<echarts.ECharts | null>(null)
const mainSubRadarChartRef = ref<HTMLDivElement | null>(null)
const mainSubRadarChartInstance = ref<echarts.ECharts | null>(null)
const modalRadarChartRef = ref<HTMLDivElement | null>(null)
const modalRadarChartInstance = ref<echarts.ECharts | null>(null)

const domainList = computed(() => overview.value.knowledge_domains?.top_domains || [])
const crossDomainRate = computed(() => overview.value.knowledge_domains?.cross_domain_rate || 0)
const crossDomainPapers = computed(() => overview.value.knowledge_domains?.cross_domain_papers || 0)
const totalDomainPapers = computed(() => overview.value.knowledge_domains?.total_papers || 0)
const subDomainGranularity = computed(() => overview.value.knowledge_domains?.sub_domain_granularity || 0)

const primaryCoverageDomains = computed(() =>
  domainList.value.filter((d: any) => !d.is_interdisciplinary),
)

function getEffectiveSubDomains(domain: any) {
  if (!domain?.sub_domains?.length) return []
  return domain.sub_domains.filter((s: any) => !s.is_primary_only)
}

function shouldShowSubDomainRadar(domain: any) {
  if (!domain || domain.is_interdisciplinary || domain.is_coverage_overview) return false
  return getEffectiveSubDomains(domain).length >= 3
}

/** 左侧列表：仅保留有效子领域 ≥3 的一级学科，其余归入「领域分布」 */
const radarSidebarDomains = computed(() =>
  domainList.value.filter((d: any) =>
    !d.is_interdisciplinary && getEffectiveSubDomains(d).length >= 3,
  ),
)

const sidebarDomainList = computed(() => {
  const radarItems = radarSidebarDomains.value
  const backendFallback = domainList.value.find((d: any) => d.is_interdisciplinary)
  const hasNonRadarPrimaries = primaryCoverageDomains.value.some(
    (d: any) => !radarItems.some((r: any) => r.name === d.name),
  )

  if (!hasNonRadarPrimaries && !backendFallback) return radarItems

  if (backendFallback) return [...radarItems, backendFallback]

  return [...radarItems, {
    name: '领域分布',
    frequency: primaryCoverageDomains.value.reduce((sum: number, d: any) => sum + (d.frequency || 0), 0),
    is_interdisciplinary: true,
    is_coverage_overview: true,
    sub_domains: [],
    sub_domain_count: primaryCoverageDomains.value.length,
  }]
})

const primaryDomain = computed(() => radarSidebarDomains.value[0] || sidebarDomainList.value[0] || null)

const topRadarDomain = computed(() => {
  if (!radarSidebarDomains.value.length) return null
  return [...radarSidebarDomains.value].sort((a: any, b: any) => b.frequency - a.frequency)[0]
})

const roseLegendDomains = computed(() =>
  primaryCoverageDomains.value.slice(0, 4).map((d: any, i: number) => ({
    name: d.name,
    frequency: d.frequency,
    color: CHART_COLORS[i % CHART_COLORS.length],
  })),
)

const modalSelectedDomain = computed(() => radarSidebarDomains.value[modalDomainIndex.value] || null)

const modalChartTitle = computed(() => {
  if (!modalSelectedDomain.value) return '子领域分布'
  return `${modalSelectedDomain.value.name} · 子领域分布`
})

const coverageOverviewItem = computed(() =>
  sidebarDomainList.value.find((d: any) => !shouldShowSubDomainRadar(d)) || null,
)

function openDomainModal() {
  if (!radarSidebarDomains.value.length) return
  showDomainModal.value = true
  modalDomainIndex.value = 0
}

function selectModalDomain(index: number) {
  modalDomainIndex.value = index
}

watch([showDomainModal, modalDomainIndex], ([open]) => {
  if (!open) return
  nextTick(() => renderModalRadarChart())
})

function initChart(el: HTMLDivElement | null, instanceRef: { value: echarts.ECharts | null }) {
  if (!el) return null
  if (instanceRef.value) {
    instanceRef.value.dispose()
    instanceRef.value = null
  }
  instanceRef.value = echarts.init(el, undefined, { renderer: 'canvas' })
  return instanceRef.value
}

function formatRadarAxisName(name: string, charsPerLine = 4): string {
  if (name.length <= charsPerLine) return name
  const lines: string[] = []
  for (let i = 0; i < name.length; i += charsPerLine) {
    lines.push(name.slice(i, i + charsPerLine))
  }
  return lines.join('\n')
}

function renderRoseChart(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  instance: any,
  domains: Array<{ name: string; frequency: number }>,
  isCompact: boolean,
) {
  if (!domains.length) {
    instance.setOption({
      backgroundColor: 'transparent',
      title: {
        text: '暂无数据',
        left: 'center',
        top: 'center',
        textStyle: { color: 'var(--text-tertiary)', fontSize: 12, fontWeight: 'normal' },
      },
    })
    return
  }

  const sorted = [...domains].sort((a, b) => b.frequency - a.frequency)

  instance.setOption({
    color: [...CHART_COLORS],
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => `${p.name}<br/><span style="color:#2563eb;font-weight:600">${p.value} 篇 · ${p.percent}%</span>`,
    },
    series: [{
      type: 'pie',
      roseType: 'area',
      radius: isCompact ? ['14%', '76%'] : [26, 96],
      center: ['50%', '50%'],
      itemStyle: {
        borderRadius: 5,
        borderColor: '#fff',
        borderWidth: 2,
      },
      label: { show: false },
      labelLine: { show: false },
      emphasis: {
        scale: true,
        scaleSize: 6,
      },
      data: sorted.map((d, i) => ({
        name: d.name,
        value: d.frequency,
        itemStyle: { color: CHART_COLORS[i % CHART_COLORS.length] },
      })),
      animationDuration: 600,
      animationEasing: 'cubicOut',
    }],
  })
}

function buildRadarOption(domain: any, isCompact: boolean) {
  const color = '#2563eb'
  const subDomains = getEffectiveSubDomains(domain).slice(0, 8)
  if (!subDomains.length) return null

  const maxFreq = Math.max(...subDomains.map((s: any) => s.frequency), 1)
  const indicators = subDomains.map((s: any) => ({ name: s.name, max: maxFreq }))
  const values = subDomains.map((s: any) => s.frequency)

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
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
      },
    },
    radar: {
      indicator: indicators,
      shape: 'polygon',
      splitNumber: 4,
      center: ['50%', isCompact ? '53%' : '52%'],
      radius: isCompact ? '50%' : '64%',
      nameGap: isCompact ? 10 : 8,
      axisName: {
        color: '#64748b',
        fontSize: isCompact ? 11 : 11,
        fontWeight: 500,
        lineHeight: 15,
        padding: [2, 4],
        formatter: (name: string) => formatRadarAxisName(name, isCompact ? 4 : 5),
      },
      splitLine: { lineStyle: { color: '#e2e8f0' } },
      splitArea: { show: true, areaStyle: { color: ['#fff', '#f8fafc'] } },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    series: [{
      name: domain.name,
      type: 'radar',
      data: [{
        value: values,
        name: domain.name,
        areaStyle: { color: 'rgba(37, 99, 235, 0.12)' },
        lineStyle: { color, width: 2 },
        itemStyle: { color, borderColor: '#fff', borderWidth: 2 },
        symbolSize: isCompact ? 5 : 6,
        label: { show: false },
      }],
    }],
  }
}

function renderDomainRadar(instance: any, domain: any, isCompact: boolean) {
  const option = domain && shouldShowSubDomainRadar(domain)
    ? buildRadarOption(domain, isCompact)
    : null

  if (!option) {
    instance.setOption({
      backgroundColor: 'transparent',
      title: {
        text: '暂无足够子领域',
        subtext: '需 3 个及以上子方向',
        left: 'center',
        top: 'center',
        textStyle: { color: 'var(--text-tertiary)', fontSize: 12, fontWeight: 'normal' },
        subtextStyle: { color: '#cbd5e1', fontSize: 11 },
      },
    })
    return
  }

  instance.setOption(option)
}

function renderMainPanoramaCharts() {
  const rose = initChart(mainRoseChartRef.value, mainRoseChartInstance)
  if (rose) renderRoseChart(rose, primaryCoverageDomains.value, true)

  const radar = initChart(mainSubRadarChartRef.value, mainSubRadarChartInstance)
  if (radar) renderDomainRadar(radar, topRadarDomain.value, true)

  nextTick(() => {
    observeChartContainers()
    handleChartResize()
  })
}

let chartResizeObserver: ResizeObserver | null = null

function observeChartContainers() {
  chartResizeObserver?.disconnect()
  chartResizeObserver = new ResizeObserver(() => handleChartResize())
  if (mainRoseChartRef.value) chartResizeObserver.observe(mainRoseChartRef.value)
  if (mainSubRadarChartRef.value) chartResizeObserver.observe(mainSubRadarChartRef.value)
}

function renderModalRadarChart() {
  const instance = initChart(modalRadarChartRef.value, modalRadarChartInstance)
  if (!instance) return
  renderDomainRadar(instance, modalSelectedDomain.value, false)
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
  const year = parseInt(parts[0], 10)
  const m = parseInt(parts[1], 10)
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
      date: `${year}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
    })
  }

  const totalCells = Math.ceil(allCells.length / 7) * 7
  while (allCells.length < totalCells) {
    allCells.push({ day: null, count: 0, date: null })
  }

  const rows: { data: { day: number | null; count: number; date: string | null }[] }[] = []
  for (let i = 0; i < allCells.length; i += 7) {
    rows.push({ data: allCells.slice(i, i + 7) })
  }

  return rows
})

const getCellColor = (day: number | null, count: number) => {
  if (day === null) return 'transparent'
  const maxValue = currentHeatmap.value?.max_value || 1

  if (heatmapMode.value === 'focus') {
    if (count === 0) return '#ecfdf5'
    if (count <= Math.ceil(maxValue * 0.25)) return '#d1fae5'
    if (count <= Math.ceil(maxValue * 0.5)) return '#6ee7b7'
    if (count <= Math.ceil(maxValue * 0.75)) return '#10b981'
    return '#0f766e'
  }

  if (count === 0) return '#eff6ff'
  if (count <= Math.ceil(maxValue * 0.25)) return '#dbeafe'
  if (count <= Math.ceil(maxValue * 0.5)) return '#93c5fd'
  if (count <= Math.ceil(maxValue * 0.75)) return '#3b82f6'
  return '#1d4ed8'
}

const currentMonthTotal = computed(() => {
  const data = currentHeatmap.value?.data || {}
  const monthData = data[currentMonth.value] || []
  return monthData.reduce((sum: number, count: number) => sum + count, 0)
})

const heatmapUnit = computed(() => heatmapMode.value === 'upload' ? '篇' : '分钟')

const heroMetrics = computed(() => ({
  parsed: completedCount.value || overview.value.paper_count || 0,
  todayMinutes: learningDuration.value?.today || learningOverview.value?.today_minutes || 0,
  reports: overview.value.deep_research_outputs?.reports || overview.value.report_count || 0,
  domainSpan: Math.round((crossDomainRate.value || 0) * 100),
}))

const currentMonthLabel = computed(() => {
  const parts = currentMonth.value.split('-')
  return `${parseInt(parts[1], 10)}月`
})

const reportTitle = computed(() => {
  if (reportLoading.value) return reportLoadingText.value
  if (monthlyReportData.value?.summary) {
    return `本月学习小结已生成（${currentMonthLabel.value}）`
  }
  return `生成本月学习小结（${currentMonthLabel.value}）`
})
const reportEditorialTitle = computed(() => {
  const parts = currentMonth.value.split('-')
  return `${parts[0]}年${parseInt(parts[1], 10)}月·研读总结`
})

const reportHighlights = computed(() => [
  {
    label: '研读报告',
    value: overview.value.deep_research_outputs?.reports || overview.value.report_count || 0,
    tone: 'tone-report',
  },
  {
    label: '知识图谱',
    value: overview.value.deep_research_outputs?.graphs || 0,
    tone: 'tone-graph',
  },
  {
    label: '跨学科占比',
    value: `${heroMetrics.value.domainSpan}%`,
    tone: 'tone-cross',
  },
])

const domainDoughnutStyle = computed(() => {
  const domains = (overview.value.knowledge_domains?.top_domains || []).slice(0, 5)
  const total = domains.reduce((sum: number, d: any) => sum + d.frequency, 0)
  if (!total) return { background: 'var(--border-light)' }
  const colors = ['#2563eb', '#10b981', '#6366f1', '#f59e0b', '#94a3b8']
  let acc = 0
  const stops = domains.map((d: any, i: number) => {
    const pct = (d.frequency / total) * 100
    const start = acc
    acc += pct
    return `${colors[i % colors.length]} ${start}% ${acc}%`
  })
  return { background: `conic-gradient(${stops.join(', ')})` }
})

const domainLegend = computed(() =>
  (overview.value.knowledge_domains?.top_domains || []).slice(0, 3).map((d: any) => ({
    name: d.name,
    count: d.frequency,
  })),
)

function showCellTooltip(event: MouseEvent, cell: { day: number | null; count: number; date: string | null }) {
  if (!cell.day || !cell.date) {
    heatmapTooltip.value.visible = false
    return
  }
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  heatmapTooltip.value = {
    visible: true,
    x: rect.left + rect.width / 2,
    y: rect.top - 8,
    text: `${cell.date} · ${cell.count} ${heatmapUnit.value}`,
  }
}

function hideCellTooltip() {
  heatmapTooltip.value.visible = false
}

async function loadMonthlyReport(force = false) {
  try {
    const result = await featuresApi.monthlyReport(currentMonth.value, force)
    monthlyReportData.value = result
    return result
  } catch (error) {
    console.error('加载月度报告失败:', error)
    return null
  }
}

async function ensureMonthlyReport() {
  const cached = await loadMonthlyReport()
  if (cached?.summary) return
  await generateMonthlyReport()
}

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
  window.addEventListener('resize', handleChartResize)

  await auth.loadMe().catch(() => {})
  await store.load()
  paperCount.value = store.list.length
  completedCount.value = store.list.filter(
    p => p.parse_status === 'completed' || p.parse_status === 'indexed',
  ).length

  try {
    const overviewData = await featuresApi.overview()
    overview.value = overviewData
    overview.value.records = overview.value.records || overview.value.recent_records || []
    learningOverview.value = overviewData
  } catch { /* ignore */ }

  await ensureMonthlyReport().catch(() => {})

  try {
    learningDuration.value = await authApi.getAllLearningDuration()
  } catch { /* ignore */ }

  await nextTick()
  renderMainPanoramaCharts()
})

watch(domainList, () => {
  nextTick(() => renderMainPanoramaCharts())
})

function handleChartResize() {
  mainRoseChartInstance.value?.resize()
  mainSubRadarChartInstance.value?.resize()
  modalRadarChartInstance.value?.resize()
}

onUnmounted(() => {
  window.removeEventListener('resize', handleChartResize)
  chartResizeObserver?.disconnect()
  chartResizeObserver = null
  mainRoseChartInstance.value?.dispose()
  mainSubRadarChartInstance.value?.dispose()
  modalRadarChartInstance.value?.dispose()
})

watch(currentMonth, () => {
  monthlyReportData.value = null
  ensureMonthlyReport().catch(() => {})
})

async function generateMonthlyReport(force = false) {
  reportLoading.value = true
  if (!force) monthlyReportData.value = null

  // 滚动加载文案
  const phraseInterval = setInterval(() => {
    const idx = Math.floor(Math.random() * loadingPhrases.length)
    reportLoadingText.value = loadingPhrases[idx]
  }, 2000)
  reportLoadingText.value = loadingPhrases[0]

  try {
    const result = await featuresApi.monthlyReport(currentMonth.value, force)
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
  const period = monthlyReportData.value?.period
    || monthlyReportData.value?.month
    || currentMonth.value
  const prefix = '本月学习小结'

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
  a.download = `${prefix}_${period}.${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="profile-page profile-container">
    <!-- 左栏：身份名片 -->
    <aside class="profile-col profile-col--left">
      <section class="profile-card identity-card">
        <div
          class="avatar-wrapper"
          :class="{ 'is-uploading': avatarUploading }"
          role="button"
          tabindex="0"
          title="点击更换头像"
          @click="triggerAvatarUpload"
          @keydown.enter.prevent="triggerAvatarUpload"
        >
          <input
            ref="avatarInputRef"
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            hidden
            @change="onAvatarSelected"
          />
          <img v-if="avatarDisplayUrl" :src="avatarDisplayUrl" class="avatar-image" alt="用户头像">
          <div v-else class="avatar-box">{{ user.username?.slice(0, 1)?.toUpperCase() }}</div>
          <div class="avatar-upload-mask">
            <span>{{ avatarUploading ? '上传中…' : '更换头像' }}</span>
          </div>
        </div>
        <div class="profile-identity-text">
          <h2>{{ user.name || user.username }}</h2>
        </div>

        <div v-if="overview.research_interests?.length" class="profile-tags">
          <span v-for="tag in overview.research_interests.slice(0, 3)" :key="tag" class="profile-tag">{{ tag }}</span>
        </div>

        <nav class="profile-settings">
          <button type="button" class="settings-row" @click="editUsername = user.username; showUsernameModal = true">
            <span class="settings-row-label">用户名</span>
            <span class="settings-row-value">{{ user.username }}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
          </button>
          <button type="button" class="settings-row" @click="showEmailModal = true">
            <span class="settings-row-label">邮箱</span>
            <span class="settings-row-value">{{ user.email || '未设置' }}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
          <button type="button" class="settings-row" @click="showPhoneModal = true">
            <span class="settings-row-label">手机</span>
            <span class="settings-row-value">{{ user.phone ? maskPhone(user.phone) : '未设置' }}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
          <button type="button" class="settings-row" @click="showPasswordModal = true">
            <span class="settings-row-label">修改密码</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
        </nav>

        <button type="button" class="logout-btn" @click="logout">退出登录</button>
      </section>

      <section class="heatmap-compact profile-card heatmap-card--left">
        <div class="heatmap-card-head">
          <h3>科研热力</h3>
          <div class="heatmap-mode-row heatmap-mode-row--inline" :class="`heatmap-mode-row--${heatmapMode}`">
            <button type="button" class="heatmap-mode-btn heatmap-mode-btn--upload" :class="{ active: heatmapMode === 'upload' }" @click="heatmapMode = 'upload'">上传</button>
            <button type="button" class="heatmap-mode-btn heatmap-mode-btn--focus" :class="{ active: heatmapMode === 'focus' }" @click="heatmapMode = 'focus'">专注</button>
          </div>
        </div>
        <div class="heatmap-calendar">
          <div class="heatmap-dow-head">
            <span v-for="day in weekDays" :key="day">{{ day }}</span>
          </div>
          <div class="heatmap-calendar-grid">
            <div v-for="(row, rowIndex) in heatmapRows" :key="rowIndex" class="heatmap-calendar-row">
              <div
                v-for="(cell, idx) in row.data"
                :key="`${rowIndex}-${idx}`"
                class="heatmap-cell"
                :class="{ empty: !cell.day }"
                :style="{ backgroundColor: getCellColor(cell.day, cell.count) }"
                @mouseenter="showCellTooltip($event, cell)"
                @mouseleave="hideCellTooltip"
              />
            </div>
          </div>
        </div>
      </section>
    </aside>

    <!-- 中栏：月度报告 & 技能图谱 -->
    <main class="profile-col profile-col--center">
      <section class="report-editorial profile-card report-editorial--always monthly-report-card">
        <div class="report-editorial-head">
          <div class="report-month-nav">
            <button type="button" class="nav-btn" :class="{ disabled: !canPrev }" :disabled="!canPrev" @click="prevMonth">
              <ArrowLeft />
            </button>
            <button type="button" class="month-btn" @click="showCalendar = !showCalendar">{{ currentMonth }}</button>
            <button type="button" class="nav-btn" :class="{ disabled: !canNext }" :disabled="!canNext" @click="nextMonth">
              <ArrowRight />
            </button>
          </div>
          <div class="report-editorial-actions">
            <button
              v-if="monthlyReportData?.summary"
              type="button"
              class="btn-ghost btn-ghost--sm"
              @click="exportReport('md')"
            >导出 MD</button>
            <button
              type="button"
              class="btn-ghost btn-ghost--sm"
              :disabled="reportLoading"
              @click="generateMonthlyReport(true)"
            >重新生成</button>
          </div>
        </div>

        <div class="report-title-container">
          <h3 class="report-header-title">{{ reportEditorialTitle }}</h3>
          <p class="report-header-sub">{{ reportLoading ? reportLoadingText : reportSubtitle }}</p>
        </div>

        <div class="report-highlights">
          <div v-for="item in reportHighlights" :key="item.label" class="report-highlight">
            <span class="report-highlight-value" :class="item.tone">{{ item.value }}</span>
            <span class="report-highlight-label">{{ item.label }}</span>
          </div>
        </div>

        <div v-if="reportLoading && !monthlyReportData?.summary" class="report-loading">
          <span class="report-loading-spinner" aria-hidden="true" />
          <span>{{ reportLoadingText }}</span>
        </div>
        <div v-else-if="monthlyReportData?.summary" class="report-detail-inline">
          <div ref="reportSummaryRef" class="report-summary-content">
            <MarkdownRenderer :content="monthlyReportData.summary" />
          </div>
        </div>
      </section>
    </main>

    <!-- 右栏：学科分布 & 学科领域 -->
    <aside class="profile-col profile-col--right">
      <section class="domain-charts-panel profile-card">
        <div class="domain-chart-block domain-chart-block--rose">
          <div class="panel-head">
            <h3>学科分布</h3>
            <button
              type="button"
              class="btn-detail"
              :disabled="!radarSidebarDomains.length"
              @click="openDomainModal"
            >详情</button>
          </div>
          <div ref="mainRoseChartRef" class="skill-chart skill-chart--rose" />
          <div v-if="roseLegendDomains.length" class="skill-domain-legend">
            <span
              v-for="item in roseLegendDomains"
              :key="item.name"
              class="skill-domain-legend-item"
              :title="`${item.name} · ${item.frequency} 篇`"
            >
              <i :style="{ background: item.color }" />
              {{ item.name }}
            </span>
          </div>
        </div>

        <div class="domain-charts-divider" aria-hidden="true" />

        <div class="domain-chart-block domain-chart-block--sub">
          <div class="panel-head panel-head--compact">
            <div class="panel-head-main">
              <h3>学科领域</h3>
              <span v-if="topRadarDomain" class="insights-domain-badge insights-domain-badge--inline">{{ topRadarDomain.name }}</span>
            </div>
          </div>
          <div ref="mainSubRadarChartRef" class="skill-chart skill-chart--side skill-chart--sub" />
        </div>
      </section>
    </aside>

    <!-- 热力图 Tooltip -->
    <Teleport to="body">
      <div
        v-if="heatmapTooltip.visible"
        class="heatmap-tooltip"
        :style="{ left: `${heatmapTooltip.x}px`, top: `${heatmapTooltip.y}px` }"
      >
        {{ heatmapTooltip.text }}
      </div>
    </Teleport>

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
            <div v-if="radarSidebarDomains.length > 1" class="domain-view-tabs">
              <button
                v-for="(domain, index) in radarSidebarDomains"
                :key="domain.name"
                type="button"
                class="domain-view-tab"
                :class="{ active: modalDomainIndex === index }"
                @click="selectModalDomain(index)"
              >
                {{ domain.name }}
                <span class="domain-view-tab-sub">{{ getEffectiveSubDomains(domain).length }} 子领域</span>
              </button>
            </div>

            <section class="domain-main">
              <div v-if="modalSelectedDomain" class="radar-section">
                <div class="radar-header">
                  <h5>{{ modalChartTitle }}</h5>
                </div>
                <div ref="modalRadarChartRef" class="radar-chart" />

                <div class="sub-domain-table">
                  <div class="table-header">
                    <span>子领域</span>
                    <span class="header-right">频次</span>
                    <span class="header-right">占比</span>
                  </div>
                  <div
                    v-for="sub in getEffectiveSubDomains(modalSelectedDomain)"
                    :key="sub.name"
                    class="table-row"
                  >
                    <span class="sub-name">{{ sub.name }}</span>
                    <span class="sub-freq">{{ sub.frequency }}</span>
                    <span class="sub-ratio">{{ ((sub.frequency / getEffectiveSubDomains(modalSelectedDomain).reduce((s: number, x: any) => s + x.frequency, 0)) * 100).toFixed(1) }}%</span>
                  </div>
                </div>
              </div>
              <div v-else class="domain-modal-empty">
                暂无子领域雷达数据（需 3 个及以上子方向）
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
  --bg-surface: #f1f5f9;
  --text-main: var(--text-heading);
  --text-muted: var(--text-secondary);
  --accent-caramel: var(--academic-primary);
  height: 100%;
  overflow-y: auto;
}

.profile-container {
  background: var(--bg-canvas);
  padding: 20px 28px;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 280px;
  gap: 12px;
  align-items: stretch;
  box-sizing: border-box;
}

.profile-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  height: 100%;
}

.profile-col--left .identity-card {
  flex-shrink: 0;
}

.profile-col--left .heatmap-card--left {
  margin-top: auto;
}

.profile-col--center .report-editorial {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.profile-col--right .domain-charts-panel {
  flex: 1;
  min-height: 0;
}

.profile-card {
  background: #ffffff;
  border-radius: 14px;
  padding: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: var(--shadow-card);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.profile-card:hover {
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06);
}

/* ============ 左栏身份名片 ============ */
.identity-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.avatar-wrapper {
  position: relative;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: 3px solid #ffffff;
  outline: 1px solid var(--text-muted);
  overflow: hidden;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
  margin-bottom: 8px;
  cursor: pointer;
}

.avatar-wrapper.is-uploading {
  pointer-events: none;
  opacity: 0.75;
}

.avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.avatar-upload-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.45);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.avatar-wrapper:hover .avatar-upload-mask,
.avatar-wrapper:focus-visible .avatar-upload-mask {
  opacity: 1;
}

.avatar-box {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  background: linear-gradient(145deg, #3b82f6, #10b981);
  color: #fff;
  font-size: 30px;
  font-weight: 800;
}

.profile-identity-text h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-main);
}

.profile-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 5px;
  margin-top: 10px;
}

.profile-tag {
  padding: 4px 12px;
  border-radius: 6px;
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
  font-size: 12px;
  font-weight: 600;
}

.profile-settings {
  width: 100%;
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.settings-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: background 0.12s;
}

.settings-row:hover {
  background: var(--bg-surface);
}

.settings-row-label {
  flex: 1;
  font-size: 13px;
  color: var(--text-main);
}

.settings-row-value {
  font-size: 12px;
  color: var(--text-muted);
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-row svg {
  flex-shrink: 0;
  color: var(--text-muted);
}

.logout-btn {
  margin-top: 8px;
  padding-top: 8px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s;
}

.logout-btn:hover {
  color: #ef4444;
}

/* ============ 中栏：杂志化报告 ============ */
.profile-col--center,
.profile-col--left,
.profile-col--right {
  gap: 12px;
}

.domain-charts-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 12px 14px;
  height: 100%;
}

.domain-chart-block {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.domain-chart-block--rose {
  flex: 1;
}

.domain-chart-block--sub {
  flex: 1.08;
}

.domain-charts-divider {
  height: 1px;
  background: rgba(226, 232, 240, 0.55);
  margin: 6px 0;
  flex-shrink: 0;
}

.domain-chart-block .panel-head {
  margin-bottom: 2px;
  flex-shrink: 0;
}

.domain-charts-panel,
.heatmap-card--left,
.report-editorial {
  margin: 0;
}

.report-editorial.profile-card {
  padding: 16px 18px;
  background: var(--bg-canvas);
  border-color: rgba(226, 232, 240, 0.35);
  box-shadow: inset 0 0 60px rgba(0, 0, 0, 0.01), var(--shadow-card);
  min-height: 0;
}

.monthly-report-card.report-editorial.profile-card {
  background: #ffffff;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  padding: 32px 40px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
  transform: translateY(-2px);
}

.report-editorial.profile-card:hover {
  box-shadow: inset 0 0 60px rgba(0, 0, 0, 0.01), var(--shadow-card);
}

.monthly-report-card.report-editorial.profile-card:hover {
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
  transform: translateY(-2px);
}

.report-editorial:hover {
  transform: none;
}

.report-editorial--always:hover {
  transform: none;
}

.monthly-report-card.report-editorial--always:hover {
  transform: translateY(-2px);
}

.report-detail-inline {
  width: 100%;
  margin-top: 20px;
  padding-top: 8px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.report-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding: 12px 0;
  color: var(--text-muted);
  font-size: 13px;
  flex: 1;
}

.report-loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #e8e4dc;
  border-top-color: var(--academic-primary);
  border-radius: 50%;
  animation: reportSpin 0.8s linear infinite;
}

@keyframes reportSpin {
  to { transform: rotate(360deg); }
}

.report-editorial.is-expanded {
  box-shadow: inset 0 0 60px rgba(0, 0, 0, 0.015), 0 6px 20px rgba(15, 23, 42, 0.06);
}

.report-editorial-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.report-editorial .nav-btn,
.report-editorial .month-btn,
.report-editorial .btn-ghost {
  background: transparent;
  border-color: rgba(156, 148, 140, 0.28);
  color: var(--text-muted);
  box-shadow: none;
}

.report-editorial .month-btn {
  color: var(--text-main);
  font-weight: 600;
}

.report-editorial .nav-btn:hover:not(.disabled),
.report-editorial .month-btn:hover,
.report-editorial .btn-ghost:hover:not(:disabled) {
  background: rgba(239, 246, 255, 0.85);
  border-color: rgba(59, 130, 246, 0.4);
  color: var(--text-main);
}

.report-editorial .btn-ghost:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.report-month-nav {
  display: flex;
  align-items: center;
  gap: 6px;
}

.report-editorial-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.report-title-container {
  border-left: 4px solid #2563eb;
  padding-left: 12px;
  margin-bottom: 24px;
}

.report-header-title {
  margin: 0;
  font-family: Georgia, 'Source Han Serif CN', 'Noto Serif SC', serif;
  color: var(--text-main);
  font-size: 20px;
  font-weight: 600;
}

.report-header-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.report-highlights {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(226, 232, 240, 0.5);
}

.report-highlight {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.report-highlight-value {
  font-size: 36px;
  font-weight: 800;
  font-family: 'Inter', system-ui, sans-serif;
  line-height: 1;
  letter-spacing: -0.02em;
}

.report-highlight-value.tone-report {
  color: #2563eb;
}

.report-highlight-value.tone-graph {
  color: #10b981;
}

.report-highlight-value.tone-cross {
  color: #f59e0b;
}

.report-highlight-label {
  font-size: 12px;
  color: var(--text-muted);
}

.panel-head--compact {
  margin-bottom: 2px;
}

.panel-head-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

/* ============ 图表卡片 ============ */
.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.panel-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-main);
}

.panel-sub {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

.insights-domain-badge {
  display: inline-flex;
  align-self: flex-start;
  margin: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 500;
  color: #2563eb;
  background: rgba(91, 143, 185, 0.1);
}

.insights-domain-badge--inline {
  align-self: flex-start;
}

/* ============ 右栏数据魔方 ============ */
.stats-cube-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.stat-cube {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 16px;
  border-radius: 14px;
  background: var(--bg-surface);
  transition: transform 0.2s ease;
}

.stat-cube:hover {
  transform: translateY(-2px);
}

.stat-cube-value {
  font-size: 26px;
  font-weight: 800;
  color: var(--text-main);
  line-height: 1;
  letter-spacing: -0.02em;
}

.stat-cube-label {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}

.skill-graph-card,
.domain-mini-card {
  padding: 20px;
}

.skill-chart {
  width: 100%;
}

.skill-chart--rose {
  flex: 1;
  min-height: 128px;
  height: auto;
}

.skill-chart--sub,
.skill-chart--side.skill-chart--sub {
  flex: 1;
  min-height: 148px;
  height: auto;
}

.skill-domain-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 8px;
  flex-shrink: 0;
}

.skill-domain-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.35;
  white-space: nowrap;
}

.skill-domain-legend-item i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.btn-detail {
  border: none;
  background: transparent;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
}

.btn-detail:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ============ 共享组件 ============ */
.card-surface {
  background: #fff;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: var(--shadow-card);
}

.dashboard-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

/* Hero Metrics */
.hero-metrics {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 20px;
}

.hero-metric {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 16px;
}

.hero-metric:first-child {
  padding-left: 0;
}

.hero-metric-value {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-heading);
  letter-spacing: -0.03em;
  line-height: 1;
}

.hero-metric-value small {
  font-size: 14px;
  font-weight: 600;
  color: var(--graph-muted);
  margin-left: 2px;
}

.hero-metric-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--graph-muted);
}

.hero-metric-divider {
  width: 1px;
  height: 36px;
  background: var(--graph-line);
  flex-shrink: 0;
}

.hero-metric-divider--wide {
  height: 48px;
  margin: 0 8px;
}

.hero-domain-viz {
  flex: 1.4;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 0 0 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: opacity 0.15s;
}

.hero-domain-viz:hover {
  opacity: 0.85;
}

.domain-doughnut-wrap {
  flex-shrink: 0;
}

.domain-doughnut {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  position: relative;
}

.domain-doughnut-hole {
  position: absolute;
  inset: 8px;
  border-radius: 50%;
  background: #fff;
  display: grid;
  place-items: center;
}

.domain-doughnut-count {
  font-size: 14px;
  font-weight: 800;
  color: var(--graph-blue);
}

.hero-domain-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hero-domain-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-heading);
}

.hero-domain-tags {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.hero-domain-tag {
  font-size: 11px;
  color: var(--graph-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hero-domain-empty {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* 第二层 Middle Row */
.middle-row {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(0, 1fr);
  gap: 16px;
  margin-top: 20px;
  align-items: stretch;
}

.report-row {
  margin-top: 16px;
}

.domain-panorama-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.domain-panorama-split {
  display: grid;
  grid-template-columns: minmax(0, 0.36fr) 1px minmax(0, 0.64fr);
  gap: 0;
  min-height: 280px;
  align-items: stretch;
}

.panorama-half {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 0 8px;
}

.panorama-half:first-child {
  padding-left: 0;
  padding-right: 4px;
}

.panorama-half:last-child {
  padding-left: 6px;
  padding-right: 0;
}

.panorama-half-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.panorama-divider {
  background: var(--border-light);
  margin: 24px 0;
}

.panorama-chart {
  flex: 1;
  width: 100%;
  min-height: 240px;
}

/* 紧凑热力图 */
.heatmap-compact {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 12px 14px;
}

.heatmap-mode-row--inline {
  margin-bottom: 0;
  gap: 6px;
}

.heatmap-mode-row--inline .heatmap-mode-btn {
  padding: 5px 10px;
  font-size: 11px;
}

.heatmap-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.heatmap-card-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-main);
}

.month-nav--card {
  flex-shrink: 0;
}

.month-btn--card {
  min-width: 96px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  gap: 4px;
}

.heatmap-mode-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.heatmap-mode-btn {
  border: none;
  background: transparent;
  padding: 7px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}

.heatmap-mode-btn:hover:not(.active) {
  color: var(--text-heading);
}

.heatmap-mode-btn.active {
  color: #fff;
}

.heatmap-mode-btn--upload.active {
  background: #2563eb;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.28);
}

.heatmap-mode-btn--focus.active {
  background: #10b981;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.28);
}

.heatmap-calendar {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.heatmap-dow-head {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 4px;
  margin-bottom: 6px;
}

.heatmap-dow-head span {
  text-align: center;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  line-height: 1;
}

.heatmap-calendar-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.heatmap-calendar-row {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 4px;
  width: 100%;
}

.heatmap-compact .heatmap-cell {
  width: 100%;
  height: auto;
  aspect-ratio: 1;
  min-height: 0;
  border-radius: 3px;
  align-self: start;
}

.heatmap-compact .heatmap-cell.empty {
  background: transparent !important;
}

.link-btn {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 12px;
  font-weight: 500;
  color: var(--graph-blue);
  cursor: pointer;
  transition: opacity 0.15s;
}

.link-btn:hover {
  opacity: 0.75;
}

/* 月度报告 CTA */
.report-cta--compact {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  background: linear-gradient(160deg, var(--bg-canvas) 0%, var(--border-lighter) 45%, var(--el-color-primary-light) 100%);
}

.report-cta-header {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  min-width: 0;
}

.report-cta--compact .report-cta-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
}

.report-cta-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.report-cta--compact .report-cta-body {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.report-cta--compact .report-cta-text {
  flex: 1;
  min-width: 0;
}

.report-cta--compact .report-cta-text h3 {
  font-size: 14px;
  line-height: 1.4;
  white-space: normal;
}

.report-cta--compact .report-cta-text p {
  font-size: 11.5px;
  line-height: 1.55;
}

.report-cta--compact .report-cta-actions {
  flex-direction: row;
  align-items: center;
  width: auto;
  flex-shrink: 0;
  gap: 8px;
}

.report-detail-inline .report-summary-content {
  overflow: visible;
}

.dashboard-bottom-row {
  margin-top: 20px;
}

.report-cta-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: #fff;
  border: 1px solid var(--graph-line);
  color: var(--graph-blue);
}

.report-cta-text h3 {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-heading);
  letter-spacing: -0.01em;
}

.report-cta-text p {
  margin: 0;
  font-size: 12px;
  color: var(--graph-muted);
  line-height: 1.5;
}

.report-cta-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.btn-primary--sm {
  padding: 8px 14px;
  font-size: 12px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 18px;
  border: none;
  border-radius: 8px;
  background: var(--graph-blue);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}

.btn-primary:hover:not(:disabled) {
  background: var(--el-color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.65;
  cursor: wait;
}

.btn-ghost {
  padding: 9px 14px;
  border: 1px solid var(--graph-line);
  border-radius: 8px;
  background: #fff;
  color: var(--graph-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
  white-space: nowrap;
}

.btn-ghost:hover {
  border-color: var(--graph-blue);
  color: var(--graph-blue);
}

.btn-ghost--sm {
  padding: 7px 12px;
  font-size: 11px;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.report-summary-content {
  --notebook-line: 32px;
  font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'SimSun', serif;
  font-size: 16px;
  color: #334155;
  line-height: var(--notebook-line);
  text-align: justify;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 8px 20px;
  background-color: #f8fafc;
  background-image: linear-gradient(
    to bottom,
    transparent calc(var(--notebook-line) - 1px),
    rgba(37, 99, 235, 0.14) calc(var(--notebook-line) - 1px),
    rgba(37, 99, 235, 0.14) var(--notebook-line)
  );
  background-size: 100% var(--notebook-line);
  background-attachment: local;
  border-radius: 6px;
  scrollbar-width: thin;
  scrollbar-color: var(--graph-line) transparent;
}

.report-summary-content :deep(h2) {
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-heading);
  text-align: left;
  border-bottom: none;
  padding: 0 0 8px;
  margin: 0 0 12px;
  background: #f8fafc;
  line-height: 1.5;
}

.report-summary-content :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-heading);
  margin: 8px 0 4px;
  background: #f8fafc;
  line-height: 1.5;
}

.report-summary-content :deep(p) {
  font-size: inherit;
  line-height: var(--notebook-line);
  color: inherit;
  letter-spacing: 0.01em;
  margin: 0 0 0;
  text-align: justify;
  text-indent: 2em;
}

.report-summary-content :deep(strong) {
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.08);
  padding: 0 4px;
  border-radius: 4px;
  font-weight: 600;
}

.report-summary-content :deep(ul),
.report-summary-content :deep(ol) {
  margin: 5px 0;
  padding-left: 18px;
}

.heatmap-strip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.heatmap-strip-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--graph-muted);
}

.heatmap-strip-title h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-heading);
}

.heatmap-strip-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.heatmap-toggle {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border-radius: 7px;
  background: var(--bg-canvas);
  border: 1px solid var(--graph-line);
}

.toggle-btn {
  padding: 5px 12px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--graph-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.toggle-btn:hover {
  color: var(--text-heading);
}

.toggle-btn.active {
  background: #fff;
  color: var(--graph-blue);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}

.month-nav {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-btn {
  width: 28px;
  height: 28px;
  border: 1px solid var(--graph-line);
  border-radius: 6px;
  background: #fff;
  color: var(--graph-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}

.nav-btn:hover:not(.disabled) {
  border-color: var(--graph-blue);
  color: var(--graph-blue);
}

.nav-btn.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.month-btn {
  padding: 5px 12px;
  border: 1px solid var(--graph-line);
  border-radius: 6px;
  background: #fff;
  color: var(--text-heading);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-arrow {
  font-size: 9px;
  color: var(--graph-muted);
}

.heatmap-github {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.heatmap-github-labels {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 0;
  flex-shrink: 0;
}

.heatmap-github-label {
  width: 14px;
  height: 11px;
  font-size: 9px;
  line-height: 11px;
  color: var(--text-tertiary);
  text-align: right;
}

.heatmap-github-grid {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.heatmap-github-row {
  display: flex;
  gap: 2px;
}

.heatmap-cell {
  width: 11px;
  height: 11px;
  border-radius: 2px;
  flex-shrink: 0;
  cursor: pointer;
  transition: transform 0.1s, outline 0.1s;
}

.heatmap-cell:hover:not(.empty) {
  transform: scale(1.25);
  outline: 1px solid rgba(15, 23, 42, 0.25);
  outline-offset: 1px;
  z-index: 2;
}

.heatmap-cell.empty {
  background: transparent !important;
  cursor: default;
}

.heatmap-strip-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--graph-line);
}

.summary-text {
  font-size: 12px;
  color: var(--graph-muted);
}

.heatmap-legend {
  display: flex;
  align-items: center;
  gap: 3px;
}

.legend-label {
  font-size: 10px;
  color: var(--text-tertiary);
  margin: 0 2px;
}

.legend-cell {
  width: 11px;
  height: 11px;
  border-radius: 2px;
}

/* 热力图 Tooltip */
.heatmap-tooltip {
  position: fixed;
  z-index: 2000;
  transform: translate(-50%, -100%);
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--text-heading);
  color: var(--bg-canvas);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.15);
}

.heatmap-tooltip::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -4px;
  transform: translateX(-50%);
  border: 4px solid transparent;
  border-top-color: var(--text-heading);
}

/* ============ 右侧个人中心 ============ */
.profile-center {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
}

.profile-identity {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}

.avatar-box {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: var(--graph-blue);
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  flex-shrink: 0;
}

.profile-identity-text h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-heading);
  letter-spacing: -0.01em;
}

.profile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 18px;
}

.profile-tag {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #1d4ed8;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}

.profile-settings {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.settings-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 11px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: background 0.12s;
}

.settings-row:hover {
  background: var(--bg-canvas);
}

.settings-row-label {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
}

.settings-row-value {
  font-size: 12px;
  color: var(--graph-muted);
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-row svg {
  flex-shrink: 0;
  color: var(--text-tertiary);
}

.logout-btn {
  margin-top: auto;
  padding-top: 16px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  text-align: center;
  transition: color 0.15s;
}

.logout-btn:hover {
  color: #ef4444;
}

/* ============ 响应式 ============ */
@media (max-width: 1200px) {
  .profile-container {
    grid-template-columns: 240px minmax(0, 1fr) 240px;
    padding: 24px;
    gap: 18px;
  }
}

@media (max-width: 1024px) {
  .profile-container {
    grid-template-columns: 1fr 1fr;
  }

  .profile-col--right {
    grid-column: 1 / -1;
    position: static;
  }

  .profile-col--left {
    grid-column: 1 / -1;
  }

  .identity-card {
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
    text-align: left;
    align-items: flex-start;
    gap: 16px;
  }

  .avatar-wrapper {
    margin-bottom: 0;
  }

  .profile-settings {
    flex: 1 1 100%;
  }
}

@media (max-width: 768px) {
  .profile-container {
    grid-template-columns: 1fr;
    padding: 16px;
  }

  .profile-col--right {
    grid-template-columns: 1fr;
  }

  .report-highlights {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .monthly-report-card.report-editorial.profile-card {
    padding: 24px 20px;
  }

  .report-highlight-value {
    font-size: 28px;
  }
}

@media (max-width: 480px) {
  .report-editorial-head {
    flex-direction: column;
    align-items: stretch;
  }

  .stat-cube-value {
    font-size: 22px;
  }
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
  box-shadow: 0 0 0 3px rgba(156, 136, 120, 0.1);
}

.modal-textarea:focus {
  outline: none;
  border-color: var(--academic-primary);
  box-shadow: 0 0 0 3px rgba(156, 136, 120, 0.1);
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
  border-color: var(--border-light);
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
  box-shadow: 0 4px 12px rgba(156, 136, 120, 0.25);
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
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(37, 99, 235, 0.06));
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
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.domain-view-tabs {
  display: flex;
  gap: 8px;
  padding: 12px 20px 0;
  border-bottom: 1px solid var(--academic-border);
  background: var(--bg-canvas);
}

.domain-view-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: none;
  border-radius: 8px 8px 0 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: color 0.15s, background 0.15s;
}

.domain-view-tab:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.7);
}

.domain-view-tab.active {
  color: var(--el-color-primary-hover);
  background: #fff;
  font-weight: 600;
}

.domain-view-tab.active::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: -1px;
  height: 2px;
  background: var(--el-color-primary-hover);
  border-radius: 2px 2px 0 0;
}

.domain-view-tab-sub {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--el-color-primary-hover);
  font-size: 11px;
  font-weight: 600;
}

.domain-main {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  background: #fff;
}

.radar-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.radar-header {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.radar-header h5 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--academic-text-main);
}

.radar-hint {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--academic-text-muted);
  line-height: 1.5;
}

.radar-chart {
  width: 100%;
  height: 360px;
}

.domain-modal-empty {
  padding: 48px 24px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
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
  background: var(--bg-canvas);
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
  background: var(--bg-canvas);
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
  background: var(--bg-canvas);
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
