<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { featuresApi } from '@/api/features'
import { usePaperStore } from '@/stores/papers'
import type { Paper, Source } from '@/types/domain'

interface CompareHistoryItem {
  id: number
  name?: string | null
  paper_ids?: number[]
  created_at?: string | null
}

interface EvidenceRow {
  paper_id?: number | string
  title?: string
  evidences?: Record<string, unknown>[]
}

interface EvidenceDimensionGroup {
  dimension_key?: string
  label?: string
  rows?: EvidenceRow[]
}

const paperStore = usePaperStore()
const route = useRoute()

const emit = defineEmits<{
  sourceClick: [source: Source]
}>()

const completedStatuses = new Set(['completed', 'indexed'])

const dimensionOptions = [
  { label: '研究问题', value: 'research_question', desc: '论文要解决的核心问题' },
  { label: '方法 / 模型', value: 'method', desc: '技术路线、模型结构或算法流程' },
  { label: '数据集 / 实验对象', value: 'experiment_data', desc: '数据来源、实验场景和对象' },
  { label: '评价指标', value: 'metrics', desc: '实验指标与评价口径' },
  { label: '主要结果', value: 'main_results', desc: '关键实验结果和结论' },
  { label: '创新点', value: 'innovations', desc: '相对已有工作的贡献' },
  { label: '局限性', value: 'limitations', desc: '方法边界、实验不足和风险' },
  { label: '未来方向', value: 'future_work', desc: '可延展研究方向' },
]

const defaultDimensionValues = ['research_question', 'method', 'experiment_data', 'main_results', 'innovations']
const allDimensionValues = dimensionOptions.map(x => x.value)

const activeTab = ref<'setup' | 'result'>('setup')
const activeHistoryId = ref<number | null>(null)
const selectedIds = ref<number[]>([])
const selectedDimensions = ref<string[]>([...defaultDimensionValues])
const compareName = ref('')
const evidenceQuestion = ref('')
const compareNameInputRef = ref<HTMLInputElement | null>(null)
const compareLoading = ref(false)
const evidenceLoading = ref(false)
const historyLoading = ref(false)
const nameLoading = ref(false)
const nameTouched = ref(false)
const isCompareNameAuto = ref(true)
const tableViewMode = ref<'zh' | 'raw'>('zh')
const compareResult = ref<any>(null)
const evidenceResult = ref<any>(null)
const history = ref<CompareHistoryItem[]>([])
const expandedCompareCells = ref<Set<string>>(new Set())
const expandedEvidenceItems = ref<Set<string>>(new Set())
const sidebarCollapsed = ref(false)
const sidebarHovered = ref(false)
const compareSnapshotKey = 'multi-paper-compare:last-result'
const evidenceSnapshotKey = 'multi-paper-compare:last-evidence'

const completedPapers = computed(() =>
  paperStore.list.filter(p => completedStatuses.has(String(p.parse_status || '').toLowerCase()))
)

const libraryPapers = computed(() => paperStore.list)

const selectedPapers = computed(() =>
  completedPapers.value.filter(p => selectedIds.value.includes(p.id))
)

const resultData = computed(() => compareResult.value?.result || compareResult.value || {})

const compareSummary = computed(() => {
  const joinList = (value: unknown) => Array.isArray(value) ? value.filter(Boolean).join('\n') : ''
  return {
    overview: resultData.value.summary || '',
    difference: joinList(resultData.value.key_differences) || resultData.value.difference_analysis || resultData.value.differences || '',
    trend: joinList(resultData.value.common_trends) || resultData.value.trend_summary || '',
    gaps: joinList(resultData.value.research_gaps) || '',
    future: joinList(resultData.value.future_directions) || resultData.value.future_direction || '',
  }
})

const summaryCards = computed(() => {
  const toItems = (value: unknown) => {
    if (Array.isArray(value)) {
      return value.map(item => String(item).trim()).filter(Boolean)
    }
    if (typeof value === 'string') {
      return value.split(/\n+/).map(item => item.trim()).filter(Boolean)
    }
    return []
  }
  const pickItems = (primary: unknown, fallback: unknown) => {
    const items = toItems(primary)
    return items.length ? items : toItems(fallback)
  }
  const cards = [
    { key: 'overview', title: '总体总结', items: toItems(resultData.value.summary) },
    { key: 'differences', title: '差异分析', items: pickItems(resultData.value.key_differences, compareSummary.value.difference) },
    { key: 'trends', title: '研究趋势', items: pickItems(resultData.value.common_trends, compareSummary.value.trend) },
    { key: 'gaps', title: '研究空白', items: pickItems(resultData.value.research_gaps, compareSummary.value.gaps) },
    { key: 'future', title: '未来方向', items: pickItems(resultData.value.future_directions, compareSummary.value.future) },
  ].filter(card => card.items.length)
  if (cards.length) return cards

  const aliases = resultPapers.value.map((p: any) => shortPaperHeader(p.title || p.short_title || p.key)).filter(Boolean)
  if (!aliases.length) return []
  return [
    {
      key: 'overview',
      title: '总体总结',
      items: [`本次对比覆盖 ${aliases.join('、')}。这些工作都围绕检索增强或神经检索展开，但分别侧重生成、预训练、段落召回或细粒度排序。`],
    },
    {
      key: 'differences',
      title: '差异分析',
      items: ['主要差异体现在检索与生成的耦合方式、训练目标、检索粒度、排序机制和推理效率。'],
    },
    {
      key: 'future',
      title: '未来方向',
      items: ['后续可继续比较端到端训练、更高效索引、证据可信度控制和动态知识更新机制。'],
    },
  ]
})

const comparisonTable = computed(() => {
  if (tableViewMode.value === 'raw') {
    if (Array.isArray(resultData.value.raw_comparison_table)) {
      return resultData.value.raw_comparison_table
    }
    if (Array.isArray(resultData.value.comparison_table)) {
      return resultData.value.comparison_table
    }
    return []
  }

  if (Array.isArray(resultData.value.comparison_table_zh)) {
    return resultData.value.comparison_table_zh
  }
  return Array.isArray(resultData.value.comparison_table) ? resultData.value.comparison_table : []
})

const resultPapers = computed(() => {
  return Array.isArray(resultData.value.papers) ? resultData.value.papers : []
})

const comparisonTableKeys = computed(() => {
  if (!comparisonTable.value.length) return []
  const rowKeys = Object.keys(comparisonTable.value[0]).filter(key => key !== 'dimension_key')
  const orderedPaperKeys = resultPapers.value
    .map((p: any) => p.key)
    .filter((key: string) => rowKeys.includes(key))
  const rest = rowKeys.filter(key => key !== 'dimension' && !orderedPaperKeys.includes(key))
  return ['dimension', ...orderedPaperKeys, ...rest].filter(key => rowKeys.includes(key))
})

const paperColumnKeys = computed(() =>
  comparisonTableKeys.value.filter(key => key !== 'dimension' && key !== 'dimension_key'),
)

const evidenceByDimensionPaper = computed(() => {
  const map = new Map<string, Record<string, unknown>>()
  for (const dimension of evidenceDimensions.value) {
    const dimKey = getDimensionKey(dimension)
    for (const row of getDimensionRows(dimension)) {
      const evidences = getRowEvidences(row)
      if (!evidences.length || row.paper_id == null) continue
      map.set(`${dimKey}:${row.paper_id}`, evidences[0])
    }
  }
  return map
})

const allDimensionsSelected = computed(() =>
  selectedDimensions.value.length === allDimensionValues.length
)

const selectedPaperCountLabel = computed(() => {
  const count = selectedIds.value.length
  return count ? `已选 ${count} 篇` : '未选择文献'
})

const selectedDimensionCountLabel = computed(() => `已选 ${selectedDimensions.value.length} 项`)

const evidenceDimensions = computed<EvidenceDimensionGroup[]>(() => {
  return Array.isArray(evidenceResult.value?.dimensions) ? evidenceResult.value.dimensions : []
})

const compareResultTitle = computed(() => String(compareResult.value?.name || '多文献对比结果'))

const compareResultBody = computed(() => compareResult.value?.result || compareResult.value || '暂无结果')

const displayEvidenceQuestion = computed(() => {
  const fromResult = evidenceResult.value?.question
  if (fromResult) return String(fromResult)
  return evidenceQuestion.value
})

const showEvidenceQuestion = computed(() => Boolean(displayEvidenceQuestion.value))

const evidenceFlatRows = computed<EvidenceRow[]>(() =>
  Array.isArray(evidenceResult.value?.rows) ? evidenceResult.value.rows : [],
)

function paperTitle(paper: Paper) {
  return paper.title || paper.original_filename || `Paper ${paper.id}`
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function historyItemTitle(item: CompareHistoryItem) {
  return item.name || '未命名对比'
}

function historyItemMeta(item: CompareHistoryItem) {
  const count = Array.isArray(item.paper_ids) ? item.paper_ids.length : 0
  return `${count} 篇文献 · ${formatDate(item.created_at)}`
}

function tableHeader(key: string) {
  if (key === 'dimension') return '对比维度'

  const paper = resultPapers.value.find((p: any) => p.key === key)
  if (paper?.title) return shortPaperHeader(paper.title)

  return key
}

function fullTableHeader(key: string) {
  if (key === 'dimension') return '对比维度'
  const paper = resultPapers.value.find((p: any) => p.key === key)
  return paper?.title || key
}

function shortPaperHeader(title: string) {
  const clean = String(title || '').replace(/\s+/g, ' ').trim()
  const acronymRules = [
    { label: 'Generative QA', pattern: /leveraging passage retrieval with generative models/i },
    { label: 'REALM', pattern: /\bREALM\b/i },
    { label: 'DPR', pattern: /\bDPR\b|dense passage retrieval/i },
    { label: 'ColBERT', pattern: /\bColBERT\b/i },
    { label: 'RAG', pattern: /\bRAG\b|retrieval[-\s]?augmented generation/i },
    { label: 'BM25', pattern: /\bBM25\b/i },
    { label: 'LLM', pattern: /\bLLMs?\b|large language models?/i },
    { label: 'Triton', pattern: /\bTriton\b/i },
    { label: 'EnvGraph', pattern: /\bEnvGraph\b/i },
  ]
  const matches = acronymRules.filter(rule => rule.pattern.test(clean)).map(rule => rule.label)
  if (matches.length) {
    if (['Generative QA', 'REALM', 'DPR', 'ColBERT'].includes(matches[0])) {
      return matches[0]
    }
    const unique = Array.from(new Set(matches))
    return unique.slice(0, 2).join(' / ')
  }
  if (clean.length <= 36) return clean
  return `${clean.slice(0, 34)}...`
}

function shortCompareTitle(title: string) {
  const alias = shortPaperHeader(title)
  if (alias && alias.length <= 18 && !alias.endsWith('...')) return alias
  const clean = String(title || '').replace(/\s+/g, ' ').trim()
  return clean.length <= 16 ? clean : `${clean.slice(0, 14)}...`
}

function toggleAllDimensions(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  selectedDimensions.value = checked ? [...allDimensionValues] : []
}

function dimensionLabel(key: string) {
  return dimensionOptions.find(x => x.value === key)?.label || key
}

function fallbackCompareName() {
  const names = selectedPapers.value.slice(0, 3).map(p => shortCompareTitle(paperTitle(p))).filter(Boolean)
  if (names.length >= 2) {
    const now = new Date()
    const stamp = `${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
    const prefix = names.join('、')
    return `多文献对比：${prefix} 等 ${selectedPapers.value.length} 篇 · ${stamp}`.slice(0, 80)
  }
  return '多文献对比'
}

function defaultEvidenceQuestion() {
  return ''
}

function normalizedSelectedPaperIds() {
  return selectedIds.value
    .map(id => Number(id))
    .filter(id => Number.isInteger(id) && id > 0)
}

async function generateCompareName(force = false) {
  const ids = normalizedSelectedPaperIds()
  if (ids.length < 2) {
    compareName.value = fallbackCompareName()
    isCompareNameAuto.value = true
    return
  }
  if (!force) {
    compareName.value = fallbackCompareName()
    isCompareNameAuto.value = true
    return
  }
  if (!force && !isCompareNameAuto.value) return

  nameLoading.value = true
  try {
    const res = await featuresApi.suggestCompareName({
      paper_ids: ids,
      dimensions: selectedDimensions.value,
    })
    const candidate = String(res?.name || '').trim()
    const generated = isEnglishLongText(candidate) ? fallbackCompareName() : (candidate || fallbackCompareName())
    const stamp = fallbackCompareName().match(/ · \d{2}-\d{2} \d{2}:\d{2}$/)?.[0] || ''
    compareName.value = generated.includes('·') ? generated : `${generated}${stamp}`.slice(0, 80)
    nameTouched.value = false
    isCompareNameAuto.value = true
  } catch {
    compareName.value = fallbackCompareName()
    isCompareNameAuto.value = true
  } finally {
    nameLoading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    history.value = await featuresApi.compareList() as any[]
  } catch {
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

function saveSnapshot(key: string, value: any) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Snapshot persistence is best-effort only.
  }
}

function loadSnapshot(key: string) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function removeSnapshot(key: string) {
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore
  }
}

function restoreLastResults() {
  const lastCompare = loadSnapshot(compareSnapshotKey)
  const lastEvidence = loadSnapshot(evidenceSnapshotKey)
  if (lastCompare) {
    compareResult.value = lastCompare
    activeHistoryId.value = lastCompare?.id ?? activeHistoryId.value
    if (Array.isArray(lastCompare?.paper_ids)) {
      selectedIds.value = lastCompare.paper_ids
    }
  }
  if (lastEvidence) {
    evidenceResult.value = lastEvidence
    if (Array.isArray(lastEvidence?.paper_ids)) {
      selectedIds.value = lastEvidence.paper_ids
    }
    evidenceQuestion.value = lastEvidence?.question || evidenceQuestion.value
  }
}

function resetPanel() {
  activeTab.value = 'setup'
  tableViewMode.value = 'zh'
  compareResult.value = null
  evidenceResult.value = null
  selectedDimensions.value = [...defaultDimensionValues]
  selectedIds.value = completedPapers.value.slice(0, 5).map(p => p.id)
  evidenceQuestion.value = defaultEvidenceQuestion()
  compareName.value = fallbackCompareName()
  nameTouched.value = false
  isCompareNameAuto.value = true
}

watch(selectedIds, () => {
  if (isCompareNameAuto.value) {
    compareName.value = fallbackCompareName()
  }
})

watch(selectedDimensions, () => {
  if (isCompareNameAuto.value) {
    compareName.value = fallbackCompareName()
  }
})

watch(compareResult, () => {
  tableViewMode.value = 'zh'
  expandedCompareCells.value = new Set()
  expandedEvidenceItems.value = new Set()
})

async function runCompare() {
  if (selectedIds.value.length < 2) {
    ElMessage.warning('请至少选择 2 篇已完成解析的文献')
    return
  }
  if (selectedIds.value.length > 5) {
    ElMessage.warning('多文献对比最多支持 5 篇文献')
    return
  }
  if (!selectedDimensions.value.length) {
    ElMessage.warning('请至少选择一个对比维度')
    return
  }

  compareLoading.value = true
  try {
    if (!compareName.value.trim()) {
      await generateCompareName(true)
    }
    compareResult.value = await featuresApi.compare({
      paper_ids: selectedIds.value,
      dimensions: selectedDimensions.value,
      name: compareName.value || undefined,
    })
    saveSnapshot(compareSnapshotKey, compareResult.value)
    await loadHistory()
    activeHistoryId.value = compareResult.value?.id ?? null
    activeTab.value = 'result'
    await loadEvidenceSilently()
    ElMessage.success('多文献对比已生成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '多文献对比生成失败')
  } finally {
    compareLoading.value = false
  }
}

async function loadEvidenceSilently() {
  if (selectedIds.value.length < 1) return

  evidenceLoading.value = true
  try {
    evidenceResult.value = await featuresApi.evidenceMatrix({
      paper_ids: selectedIds.value,
      question: evidenceQuestion.value || undefined,
      dimensions: selectedDimensions.value,
    })
    evidenceResult.value = {
      ...evidenceResult.value,
      paper_ids: [...selectedIds.value],
      selected_dimensions: [...selectedDimensions.value],
    }
    saveSnapshot(evidenceSnapshotKey, evidenceResult.value)
  } catch {
    evidenceResult.value = null
  } finally {
    evidenceLoading.value = false
  }
}

async function openHistoryItem(item: CompareHistoryItem) {
  try {
    compareResult.value = await featuresApi.compareDetail(item.id)
  } catch {
    compareResult.value = item
  }
  saveSnapshot(compareSnapshotKey, compareResult.value)
  selectedIds.value = Array.isArray(compareResult.value?.paper_ids) ? compareResult.value.paper_ids : selectedIds.value
  activeHistoryId.value = item.id
  activeTab.value = 'result'
  void loadEvidenceSilently()
}

function startNewCompare() {
  activeHistoryId.value = null
  resetPanel()
}

async function openFromQuery() {
  const id = Number(route.query.id)
  if (!id) return
  const cached = history.value.find(item => item.id === id)
  if (cached) {
    await openHistoryItem(cached)
    return
  }
  try {
    compareResult.value = await featuresApi.compareDetail(id)
    saveSnapshot(compareSnapshotKey, compareResult.value)
    selectedIds.value = Array.isArray(compareResult.value?.paper_ids)
      ? compareResult.value.paper_ids
      : selectedIds.value
    activeHistoryId.value = id
    activeTab.value = 'result'
  } catch {
    // ignore invalid query
  }
}

async function bootstrap() {
  if (!paperStore.list.length) {
    try {
      await paperStore.load()
    } catch {
      // ignore
    }
  }
  resetPanel()
  await loadHistory()
  restoreLastResults()
  await openFromQuery()
}

onMounted(() => {
  void bootstrap()
})

watch(
  () => route.query.id,
  () => {
    void openFromQuery()
  },
)

async function deleteHistoryItem(item: CompareHistoryItem) {
  try {
    await ElMessageBox.confirm('确定删除这条对比历史吗？', '删除历史记录', { type: 'warning' })
    await featuresApi.deleteCompare(item.id)
    if (activeHistoryId.value === item.id) {
      activeHistoryId.value = null
      compareResult.value = null
      activeTab.value = 'setup'
      removeSnapshot(compareSnapshotKey)
    }
    await loadHistory()
    ElMessage.success('已删除对比历史')
  } catch (e: any) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

function openEvidenceSource(evidence: any) {
  const paper = paperStore.list.find(p => p.id === evidence?.paper_id)
  const base = evidence?.source || {}
  const source: Source = {
    ...base,
    paper_id: evidence.paper_id ?? base.paper_id,
    page_number: evidence.page_number ?? base.page_number,
    section_title: evidence.section_title || base.section_title,
    snippet: evidence.snippet || base.snippet,
    paper_title: evidence.paper_title || paper?.title || paper?.original_filename,
    bbox: base.bbox ?? evidence.bbox,
    chunk_id: base.chunk_id ?? evidence.chunk_id,
    section_id: base.section_id ?? evidence.section_id,
    locate_snippet: base.locate_snippet || evidence.snippet,
    locate_type: base.locate_type,
  }
  emit('sourceClick', source)
}

function paperKeyToId(paperKey: string) {
  const paper = resultPapers.value.find((p: any) => p.key === paperKey)
  return paper?.paper_id ?? null
}

function hasCompareCellSource(row: Record<string, unknown>, paperKey: string) {
  const dimKey = String(row.dimension_key || '')
  const paperId = paperKeyToId(paperKey)
  if (!dimKey || paperId == null) return false
  return evidenceByDimensionPaper.value.has(`${dimKey}:${paperId}`)
}

function openCompareCellSource(row: Record<string, unknown>, paperKey: string) {
  const dimKey = String(row.dimension_key || '')
  const paperId = paperKeyToId(paperKey)
  if (!dimKey || paperId == null) {
    ElMessage.info('暂无原文定位信息')
    return
  }
  const evidence = evidenceByDimensionPaper.value.get(`${dimKey}:${paperId}`)
  if (evidence) {
    openEvidenceSource(evidence)
    return
  }
  ElMessage.info('该维度暂无原文依据，请查看下方「原文依据」')
}

function normalizeCompareCellText(value: unknown) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

function compareTokenSet(text: string) {
  const tokens = text.match(/[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}/gi) || []
  return new Set(tokens.map(token => token.toLowerCase()))
}

function compareTextSimilarity(a: string, b: string) {
  if (!a || !b) return 0
  if (a === b) return 1
  const setA = compareTokenSet(a)
  const setB = compareTokenSet(b)
  if (!setA.size || !setB.size) return 0
  let inter = 0
  for (const token of setA) {
    if (setB.has(token)) inter += 1
  }
  const union = new Set([...setA, ...setB]).size
  return union ? inter / union : 0
}

function getRowPaperTexts(row: Record<string, unknown>) {
  return paperColumnKeys.value
    .map(key => ({
      key,
      text: normalizeCompareCellText(displayCompareCell(row[key], row, key)),
    }))
    .filter(item => !isMissingCompareText(item.text))
}

function getCompareCellHighlight(row: Record<string, unknown>, paperKey: string) {
  if (paperKey === 'dimension' || paperKey === 'dimension_key') return ''
  const texts = getRowPaperTexts(row)
  if (texts.length < 2) return ''

  const current = texts.find(item => item.key === paperKey)
  if (!current) return ''

  const others = texts.filter(item => item.key !== paperKey)
  const maxSim = Math.max(...others.map(item => compareTextSimilarity(current.text, item.text)), 0)

  const pairSims: number[] = []
  for (let i = 0; i < texts.length; i += 1) {
    for (let j = i + 1; j < texts.length; j += 1) {
      pairSims.push(compareTextSimilarity(texts[i].text, texts[j].text))
    }
  }
  const rowAvgSim = pairSims.reduce((sum, sim) => sum + sim, 0) / pairSims.length

  if (rowAvgSim < 0.42 && maxSim < 0.48) return 'cell-diff'
  return ''
}

function compareCellKey(rowIndex: number | string, key: string) {
  return `${tableViewMode.value}-${Number(rowIndex)}-${key}`
}

function isCompareCellExpanded(rowIndex: number | string, key: string) {
  return expandedCompareCells.value.has(compareCellKey(rowIndex, key))
}

function shouldShowCompareToggle(value: unknown) {
  return tableViewMode.value === 'raw' && String(value || '').length > 160
}

function isMissingCompareText(value: unknown) {
  const text = String(value || '').trim()
  return (
    !text
    || text === '-'
    || text === '当前解析未提取到明确证据'
    || text === '当前解析未提取到明确中文概括'
  )
}

function summarizeCompareCell(text: string, maxLen = 96) {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (!normalized) return '-'
  const parts = normalized.split(/(?<=[。；;])\s*/).filter(Boolean)
  const first = (parts[0] || normalized).trim()
  if (first.length <= maxLen) return first
  return `${first.slice(0, maxLen)}…`
}

function isEnglishLongText(value: unknown) {
  const text = String(value || '').trim()
  const letters = (text.match(/[A-Za-z]/g) || []).length
  const chinese = (text.match(/[\u4e00-\u9fff]/g) || []).length
  const words = text.match(/\b[A-Za-z][A-Za-z-]{2,}\b/g) || []
  const hasEnglishSentence = /[A-Z][A-Za-z,\-\s]{35,}\./.test(text)
  const hasRawMark = /https?:\/\/|www\.|abstract|introduction|we\s+(propose|present|show|introduce)\b/i.test(text)
  const chineseRatio = chinese / Math.max(text.length, 1)
  return (
    letters > chinese * 1.4 ||
    (words.length >= 8 && chinese < 18) ||
    hasEnglishSentence ||
    hasRawMark ||
    (text.length > 80 && chineseRatio < 0.28)
  )
}

function rawCompareValue(row: any, key: string) {
  const dimKey = row?.dimension_key
  const rawRows = Array.isArray(resultData.value.raw_comparison_table) ? resultData.value.raw_comparison_table : []
  const rawRow = rawRows.find((item: any) => item?.dimension_key === dimKey)
  return rawRow?.[key] ?? row?.[key]
}

function displayCompareCell(value: unknown, row: any, key: string) {
  if (key === 'dimension' || key === 'dimension_key') {
    return String(value || '-')
  }

  const rawText = String(rawCompareValue(row, key) || '').trim()

  if (tableViewMode.value === 'raw') {
    return isMissingCompareText(rawText) ? '-' : rawText
  }

  const zhText = String(value || '').trim()
  if (isMissingCompareText(zhText)) {
    return isMissingCompareText(rawText) ? '-' : summarizeCompareCell(rawText)
  }
  if (rawText && (zhText === rawText || rawText.includes(zhText) || zhText.includes(rawText))) {
    return summarizeCompareCell(rawText)
  }
  return zhText
}

function focusCompareName() {
  if (!isCompareNameAuto.value) return
  requestAnimationFrame(() => compareNameInputRef.value?.select())
}

function markCompareNameEdited() {
  nameTouched.value = true
  isCompareNameAuto.value = false
}

function toggleCompareCell(rowIndex: number | string, key: string) {
  const id = compareCellKey(rowIndex, key)
  const next = new Set(expandedCompareCells.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedCompareCells.value = next
}

function getDimensionKey(dimension: EvidenceDimensionGroup) {
  return String(dimension.dimension_key || '')
}

function getDimensionRows(dimension: EvidenceDimensionGroup) {
  return Array.isArray(dimension.rows) ? dimension.rows : []
}

function getRowEvidences(row: EvidenceRow) {
  return Array.isArray(row.evidences) ? row.evidences : []
}

function hasRowEvidences(row: EvidenceRow) {
  return getRowEvidences(row).length > 0
}

function evidenceFlatRowKey(row: EvidenceRow) {
  return String(row.paper_id ?? '')
}

function dimensionRowGroupKey(dimension: EvidenceDimensionGroup, row: EvidenceRow) {
  return `${getDimensionKey(dimension)}-${row.paper_id ?? ''}`
}

function getEvidencePageNumber(evidence: { page_number?: number | string }) {
  return evidence?.page_number
}

function getEvidenceSectionTitle(evidence: { section_title?: string }) {
  return evidence?.section_title
}

function getEvidenceSnippet(evidence: { snippet?: string }) {
  return evidence?.snippet ?? ''
}

function evidenceItemKey(evidence: any, prefix = 'evidence') {
  return `${prefix}-${evidence?.paper_id || ''}-${evidence?.page_number || ''}-${String(evidence?.snippet || '').slice(0, 48)}`
}

function isEvidenceExpanded(evidence: any, prefix = 'evidence') {
  return expandedEvidenceItems.value.has(evidenceItemKey(evidence, prefix))
}

function shouldShowEvidenceToggle(evidence: any) {
  return String(evidence?.snippet || '').length > 180
}

function toggleEvidenceItem(evidence: any, prefix = 'evidence') {
  const id = evidenceItemKey(evidence, prefix)
  const next = new Set(expandedEvidenceItems.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedEvidenceItems.value = next
}

function evidenceSupport(evidence: any) {
  return String(evidence?.support || evidence?.strength || 'related').toLowerCase()
}

function evidenceSupportLabel(evidence: any) {
  const level = evidenceSupport(evidence)
  if (level === 'strong') return '高度相关'
  if (level === 'medium' || level === 'related') return '部分相关'
  if (level === 'weak') return '弱相关'
  return ''
}

function evidenceSectionLabel(section?: string) {
  const value = String(section || '').trim()
  if (!value || value === '结构化抽取结果' || value === '结构化摘要') return ''
  return value
}

function shouldShowEvidenceSupport(evidence: any) {
  return Boolean(evidenceSupportLabel(evidence))
}

function evidencePageLabel(page?: number | string) {
  const value = Number(page)
  return Number.isFinite(value) && value > 0 ? `第 ${value} 页` : ''
}
</script>

<template>
  <div class="compare-workspace">
    <div
      class="compare-sidebar-wrapper"
      :class="{ collapsed: sidebarCollapsed }"
      @mouseenter="sidebarHovered = true"
      @mouseleave="sidebarHovered = false"
    >
      <aside class="compare-sidebar">
        <div class="compare-sidebar-head">
          <h2 class="compare-sidebar-title">多文献对比</h2>
          <span class="compare-count">{{ history.length }} 条</span>
        </div>

        <div class="compare-divider" />

        <div class="compare-create-block">
          <button class="compare-create-btn" @click="startNewCompare">新建对比</button>
        </div>

        <div class="compare-divider" />

        <div class="compare-list-wrap slim-scroll">
          <div v-if="historyLoading" class="compare-empty-side">加载中...</div>
          <div v-else-if="!history.length" class="compare-empty-side">暂无历史记录</div>
          <div
            v-for="item in history"
            :key="item.id"
            class="compare-list-item"
            :class="{ active: activeHistoryId === item.id }"
            @click="openHistoryItem(item)"
          >
            <div class="compare-item-main">
              <div class="compare-item-title">{{ historyItemTitle(item) }}</div>
              <div class="compare-item-meta">{{ historyItemMeta(item) }}</div>
            </div>
            <button class="compare-item-delete" title="删除" @click.stop="deleteHistoryItem(item)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>
      </aside>
    </div>

    <button
      class="compare-sidebar-toggle"
      :class="{ visible: sidebarHovered || sidebarCollapsed, collapsed: sidebarCollapsed }"
      :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
      @click="toggleSidebar"
      @mouseenter="sidebarHovered = true"
      @mouseleave="sidebarHovered = false"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline v-if="!sidebarCollapsed" points="15 18 9 12 15 6"/>
        <polyline v-else points="9 18 15 12 9 6"/>
      </svg>
    </button>

    <main class="compare-main" :class="{ 'is-sidebar-collapsed': sidebarCollapsed }">
      <header class="compare-header">
        <h2 class="compare-header-title">多文献对比</h2>
      </header>

      <div class="compare-tabs">
        <button :class="{ active: activeTab === 'setup' }" @click="activeTab = 'setup'">设置</button>
        <button :class="{ active: activeTab === 'result' }" @click="activeTab = 'result'" :disabled="!compareResult">对比结果</button>
      </div>

      <section v-if="activeTab === 'setup'" class="compare-body slim-scroll">
        <div class="section-block config-block">
          <div class="field-row name-row">
            <label class="field-label">记录名称</label>
            <div class="name-input-row">
              <input
                ref="compareNameInputRef"
                v-model="compareName"
                class="text-field"
                placeholder="输入本次对比名称"
                @focus="focusCompareName"
                @input="markCompareNameEdited"
              />
            <button
              class="inline-action"
              :disabled="nameLoading || selectedIds.length < 2"
              @click="generateCompareName(true)"
            >
              {{ nameLoading ? '生成中...' : '生成名称' }}
            </button>
            </div>
          </div>

          <div class="field-row">
            <label class="field-label">关注问题</label>
            <textarea
              v-model="evidenceQuestion"
              class="text-area"
              rows="2"
              placeholder="例如：比较检索策略、数据集和评价指标"
            />
          </div>
        </div>

        <div class="section-block">
          <div class="section-title">
            <span>选择文献</span>
            <b>{{ selectedPaperCountLabel }}</b>
          </div>
          <div v-if="completedPapers.length < 2" class="empty-note">
            文献库中至少需要 2 篇已完成解析的文献。
          </div>
          <label
            v-for="paper in libraryPapers"
            :key="paper.id"
            class="paper-option"
            :class="{ disabled: !completedStatuses.has(String(paper.parse_status || '').toLowerCase()) }"
          >
            <input
              v-model="selectedIds"
              type="checkbox"
              :value="paper.id"
              :disabled="!completedStatuses.has(String(paper.parse_status || '').toLowerCase())"
            />
            <span>
              <strong>{{ paperTitle(paper) }}</strong>
            </span>
          </label>
        </div>

        <div class="section-block">
          <div class="section-title with-actions">
            <span>对比维度</span>

            <div class="title-actions">
              <label class="select-all-box">
                <input
                  type="checkbox"
                  :checked="allDimensionsSelected"
                  @change="toggleAllDimensions"
                />
                <span>全选</span>
              </label>
              <b>{{ selectedDimensionCountLabel }}</b>
            </div>
          </div>
          <label v-for="item in dimensionOptions" :key="item.value" class="dimension-option">
            <input v-model="selectedDimensions" type="checkbox" :value="item.value" />
            <span>
              <strong>{{ item.label }}</strong>
              <em>{{ item.desc }}</em>
            </span>
          </label>
        </div>

        <div class="action-row">
          <button class="primary-action" :disabled="compareLoading || evidenceLoading" @click="runCompare">
            {{ compareLoading || evidenceLoading ? '生成中...' : '生成对比' }}
          </button>
        </div>
      </section>

      <section v-else-if="activeTab === 'result'" class="compare-body slim-scroll">
        <div class="result-meta">
          <div class="result-title-row">
            <div>
              <h3>{{ compareResultTitle }}</h3>
              <p>{{ selectedPapers.map(paperTitle).join(' · ') }}</p>
            </div>
            <div class="table-view-switch" aria-label="对比表展示模式">
              <button
                type="button"
                :class="{ active: tableViewMode === 'zh' }"
                @click="tableViewMode = 'zh'"
              >
                对比摘要
              </button>
              <button
                type="button"
                :class="{ active: tableViewMode === 'raw' }"
                @click="tableViewMode = 'raw'"
              >
                原文摘录
              </button>
            </div>
          </div>
        </div>

        <div
          v-if="comparisonTable.length"
          class="compare-table-wrap"
          :class="{ 'raw-mode': tableViewMode === 'raw' }"
        >
          <table class="compare-table">
            <thead>
              <tr>
                <th v-for="key in comparisonTableKeys" :key="key" :title="fullTableHeader(key)">
                  <span class="compare-header-text">{{ tableHeader(key) }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in comparisonTable" :key="idx">
                <td
                  v-for="key in comparisonTableKeys"
                  :key="key"
                  :class="[
                    getCompareCellHighlight(row, key),
                    {
                      'is-locatable': key !== 'dimension' && hasCompareCellSource(row, key),
                    },
                  ]"
                >
                  <div
                    class="compare-cell"
                    :class="{ clickable: key !== 'dimension' && hasCompareCellSource(row, key) }"
                    @click="key !== 'dimension' && hasCompareCellSource(row, key) ? openCompareCellSource(row, key) : undefined"
                  >
                    <div
                      class="compare-cell-content"
                      :class="{ expanded: isCompareCellExpanded(idx, key) }"
                    >
                      {{ displayCompareCell(row[key], row, key) }}
                    </div>
                    <button
                      v-if="shouldShowCompareToggle(row[key])"
                      type="button"
                      class="inline-toggle hover-action"
                      @click.stop="toggleCompareCell(idx, key)"
                    >
                      {{ isCompareCellExpanded(idx, key) ? '收起' : '展开' }}
                    </button>
                    <button
                      v-else-if="key !== 'dimension' && hasCompareCellSource(row, key)"
                      type="button"
                      class="inline-toggle hover-action locate-action"
                      @click.stop="openCompareCellSource(row, key)"
                    >
                      定位
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="raw-result">
          {{ compareResultBody }}
        </div>

        <div class="analysis-sections">
          <div v-for="card in summaryCards" :key="card.key" class="analysis-section">
            <h4>{{ card.title }}</h4>
            <ul>
              <li v-for="(item, idx) in card.items" :key="idx">{{ item }}</li>
            </ul>
          </div>
          <div v-if="!summaryCards.length" class="analysis-section">
            <h4>综合分析</h4>
            <p>暂无总结内容</p>
          </div>
        </div>

        <div v-if="evidenceLoading" class="evidence-panel">
          <h3 class="evidence-panel-title">原文依据</h3>
          <p class="evidence-panel-hint">正在整理原文摘录…</p>
        </div>

        <div v-else-if="evidenceResult" class="evidence-panel">
          <div class="evidence-panel-head">
            <h3 class="evidence-panel-title">原文依据</h3>
            <p class="evidence-panel-hint">点击条目可在 PDF 中定位到对应页码并高亮原文</p>
            <p v-if="showEvidenceQuestion" class="evidence-panel-question">
              {{ displayEvidenceQuestion }}
            </p>
          </div>

          <template v-if="evidenceDimensions.length">
            <div
              v-for="dimension in evidenceDimensions"
              :key="getDimensionKey(dimension)"
              class="dimension-section"
            >
              <div class="dimension-header">
                {{ dimension.label || dimensionLabel(getDimensionKey(dimension)) }}
              </div>
              <div class="dimension-body">
                <div
                  v-for="row in getDimensionRows(dimension)"
                  :key="dimensionRowGroupKey(dimension, row)"
                  class="evidence-group"
                >
                  <p class="evidence-paper-title">{{ row.title }}</p>
                  <div
                    v-for="evidence in getRowEvidences(row)"
                    :key="evidenceItemKey(evidence, getDimensionKey(dimension))"
                    class="evidence-item"
                    :class="`support-${evidenceSupport(evidence)}`"
                    role="button"
                    tabindex="0"
                    @click="openEvidenceSource(evidence)"
                    @keydown.enter="openEvidenceSource(evidence)"
                  >
                    <div class="evidence-item-head">
                      <span class="evidence-tags">
                        <em v-if="evidencePageLabel(getEvidencePageNumber(evidence))">{{ evidencePageLabel(getEvidencePageNumber(evidence)) }}</em>
                        <em v-if="evidenceSectionLabel(getEvidenceSectionTitle(evidence))">{{ evidenceSectionLabel(getEvidenceSectionTitle(evidence)) }}</em>
                        <em
                          v-if="shouldShowEvidenceSupport(evidence)"
                          :class="['support-tag', evidenceSupport(evidence)]"
                        >{{ evidenceSupportLabel(evidence) }}</em>
                      </span>
                    </div>
                    <span class="evidence-snippet" :class="{ expanded: isEvidenceExpanded(evidence, getDimensionKey(dimension)) }">
                      {{ getEvidenceSnippet(evidence) }}
                    </span>
                    <div class="evidence-hover-actions">
                      <button
                        v-if="shouldShowEvidenceToggle(evidence)"
                        type="button"
                        class="hover-action"
                        @click.stop="toggleEvidenceItem(evidence, getDimensionKey(dimension))"
                      >
                        {{ isEvidenceExpanded(evidence, getDimensionKey(dimension)) ? '收起' : '展开' }}
                      </button>
                      <button
                        type="button"
                        class="hover-action"
                        @click.stop="openEvidenceSource(evidence)"
                      >
                        定位
                      </button>
                    </div>
                  </div>
                  <div v-if="!hasRowEvidences(row)" class="empty-note">
                    该文献在此维度暂无原文依据。
                  </div>
                </div>
              </div>
            </div>
          </template>
          <template v-else>
            <div v-for="row in evidenceFlatRows" :key="evidenceFlatRowKey(row)" class="evidence-group">
              <p class="evidence-paper-title">{{ row.title }}</p>
              <div
                v-for="evidence in getRowEvidences(row)"
                :key="evidenceItemKey(evidence, 'flat')"
                class="evidence-item"
                :class="`support-${evidenceSupport(evidence)}`"
                role="button"
                tabindex="0"
                @click="openEvidenceSource(evidence)"
                @keydown.enter="openEvidenceSource(evidence)"
              >
                <div class="evidence-item-head">
                  <span class="evidence-tags">
                    <em v-if="evidencePageLabel(getEvidencePageNumber(evidence))">{{ evidencePageLabel(getEvidencePageNumber(evidence)) }}</em>
                    <em v-if="evidenceSectionLabel(getEvidenceSectionTitle(evidence))">{{ evidenceSectionLabel(getEvidenceSectionTitle(evidence)) }}</em>
                    <em
                      v-if="shouldShowEvidenceSupport(evidence)"
                      :class="['support-tag', evidenceSupport(evidence)]"
                    >{{ evidenceSupportLabel(evidence) }}</em>
                  </span>
                </div>
                <span class="evidence-snippet" :class="{ expanded: isEvidenceExpanded(evidence, 'flat') }">
                  {{ getEvidenceSnippet(evidence) }}
                </span>
                <div class="evidence-hover-actions">
                  <button
                    v-if="shouldShowEvidenceToggle(evidence)"
                    type="button"
                    class="hover-action"
                    @click.stop="toggleEvidenceItem(evidence, 'flat')"
                  >
                    {{ isEvidenceExpanded(evidence, 'flat') ? '收起' : '展开' }}
                  </button>
                  <button
                    type="button"
                    class="hover-action"
                    @click.stop="openEvidenceSource(evidence)"
                  >
                    定位
                  </button>
                </div>
              </div>
            </div>
          </template>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.compare-workspace {
  position: relative;
  display: flex;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-canvas);
}

.compare-sidebar-wrapper {
  position: relative;
  flex-shrink: 0;
  width: 260px;
  overflow: hidden;
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.compare-sidebar-wrapper.collapsed {
  width: 0;
}

.compare-sidebar {
  width: 260px;
  height: 100%;
  background: var(--bg-surface);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  box-sizing: border-box;
}

.compare-sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
}

.compare-sidebar-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-heading);
}

.compare-count {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
  background: var(--border-lighter);
  padding: 1px 7px;
  border-radius: 10px;
}

.compare-divider {
  height: 1px;
  background: var(--border-lighter);
  margin: 12px 0;
}

.compare-create-block {
  display: grid;
  gap: 8px;
  padding: 0 8px;
}

.compare-create-btn {
  height: 34px;
  border: none;
  border-radius: 8px;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.compare-create-btn:hover {
  background: var(--el-color-primary-hover);
}

.compare-list-wrap {
  flex: 1;
  overflow-y: auto;
  margin: 0 -12px;
  padding-bottom: 8px;
}

.compare-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.12s;
  box-shadow: 0 1px 0 0 var(--border-lighter);
  position: relative;
}

.compare-list-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: transparent;
  transition: background 0.12s;
}

.compare-list-item:hover {
  background: var(--border-lighter);
}

.compare-list-item.active {
  background: rgba(239, 246, 255, 0.85);
}

.compare-list-item.active::before {
  background: #2563eb;
}

.compare-list-item.active:hover {
  background: rgba(239, 246, 255, 0.95);
}

.compare-item-main {
  flex: 1;
  min-width: 0;
}

.compare-item-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-heading);
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.35;
}

.compare-list-item.active .compare-item-title {
  color: var(--text-heading);
}

.compare-item-meta {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.compare-item-delete {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: all 0.12s;
}

.compare-list-item:hover .compare-item-delete {
  opacity: 1;
}

.compare-item-delete:hover {
  background: #FEE2E2;
  color: #EF4444;
}

.compare-empty-side {
  padding: 32px 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.compare-sidebar-toggle {
  position: absolute;
  left: 240px;
  top: 18px;
  z-index: 50;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-light);
  border-radius: 50%;
  background: var(--bg-surface);
  color: var(--text-secondary);
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 0.2s ease, transform 0.2s ease, color 0.15s, left 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}

.compare-sidebar-toggle.visible {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.compare-sidebar-toggle.collapsed {
  left: 12px;
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.compare-sidebar-toggle:hover {
  color: var(--text-heading);
  border-color: #CBD5E1;
}

.compare-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.compare-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  flex-shrink: 0;
  background: var(--bg-canvas);
}

.compare-main.is-sidebar-collapsed .compare-header {
  padding-left: 48px;
}

.compare-header-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-heading);
}

.compare-tabs {
  display: flex;
  gap: 4px;
  padding: 0 24px;
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-canvas);
  flex-shrink: 0;
}

.compare-tabs button {
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: -1px;
}

.compare-tabs button.active {
  color: var(--el-color-primary-hover);
  border-bottom-color: var(--el-color-primary-hover);
  font-weight: 600;
}

.compare-tabs button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.compare-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 20px 24px 32px;
  background: var(--bg-canvas);
}

.section-block {
  padding: 16px 0;
  border-bottom: 1px solid var(--border-light);
}

.section-block:first-child {
  padding-top: 0;
}

.section-block:last-child {
  border-bottom: none;
}

.config-block {
  display: grid;
  gap: 14px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--text-heading);
  font-size: 14px;
  font-weight: 600;
}

.section-title b {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
}

.section-title.with-actions {
  align-items: center;
}

.title-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.select-all-box {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.select-all-box input,
.paper-option input[type="checkbox"],
.dimension-option input[type="checkbox"] {
  accent-color: #2563eb;
}

.paper-option,
.dimension-option {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: flex-start;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 6px;
  cursor: pointer;
}

.dimension-option {
  display: flex;
}

.paper-option input {
  margin-top: 2px;
}

.paper-option:hover,
.dimension-option:hover {
  background: var(--border-lighter);
}

.paper-option.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.paper-option span,
.dimension-option span {
  display: flex;
  min-width: 0;
  width: 100%;
  flex-direction: column;
  gap: 3px;
}

.paper-option strong,
.dimension-option strong {
  color: var(--text-heading);
  font-size: 13px;
  line-height: 1.35;
}

.paper-option em,
.dimension-option em,
.evidence-item em {
  color: var(--text-tertiary);
  font-size: 12px;
  font-style: normal;
  line-height: 1.4;
}

.field-label {
  display: block;
  margin: 0 0 7px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.field-row {
  min-width: 0;
}

.name-input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.inline-action {
  height: 40px;
  padding: 0 12px;
  border-radius: 8px;
  border: none;
  background: var(--border-lighter);
  color: var(--el-color-primary-hover);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.inline-action:hover:not(:disabled) {
  background: var(--border-light);
}

.inline-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.text-field,
.text-area {
  width: 100%;
  border: none;
  border-radius: 8px;
  padding: 9px 12px;
  color: var(--text-primary);
  font: inherit;
  line-height: 1.5;
  outline: none;
  resize: vertical;
  background: var(--bg-surface);
  box-shadow: 0 0 0 1px var(--border-light);
}

.text-field {
  height: 40px;
}

.text-area {
  min-height: 68px;
  max-height: 120px;
}

.text-field:focus,
.text-area:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.action-row {
  display: flex;
  gap: 10px;
  padding-top: 8px;
}

.primary-action,
.secondary-action {
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  padding: 10px 16px;
}

.primary-action {
  background: var(--el-color-primary);
  color: #fff;
}

.primary-action:hover:not(:disabled) {
  background: var(--el-color-primary-hover);
}

.secondary-action {
  background: var(--bg-surface);
  color: var(--el-color-primary-hover);
  box-shadow: 0 0 0 1px var(--border-light);
}

.primary-action:disabled,
.secondary-action:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.result-meta {
  margin-bottom: 16px;
}

.result-meta h3,
.analysis-section h4 {
  margin: 0;
  color: var(--text-heading);
  font-size: 15px;
  font-weight: 600;
}

.evidence-paper-title {
  margin: 0 0 8px;
  color: var(--sidebar-accent);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
}

.result-meta p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.result-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.result-title-row > div:first-child {
  min-width: 0;
}

.result-title-row h3 {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.3;
}

.result-title-row p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.table-view-switch {
  display: inline-flex;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 8px;
  background: var(--bg-surface);
  box-shadow: 0 0 0 1px var(--border-light);
}

.table-view-switch button {
  border: 0;
  border-right: 1px solid var(--border-light);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 12px;
  white-space: nowrap;
}

.table-view-switch button:last-child {
  border-right: 0;
}

.table-view-switch button.active {
  background: var(--el-color-primary-light);
  color: var(--el-color-primary-hover);
}

.compare-table-wrap {
  overflow: auto;
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
  border-radius: 12px;
}

.compare-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
  table-layout: fixed;
}

.compare-table th,
.compare-table td {
  min-width: 190px;
  border: none;
  border-bottom: 1px solid var(--border-lighter);
  padding: 16px;
  text-align: left;
  vertical-align: top;
  line-height: 1.55;
}

.compare-table th {
  color: var(--text-primary);
  background: var(--bg-canvas);
  font-weight: 600;
  border-bottom: 2px solid var(--academic-border);
}

.compare-table tbody tr:hover td {
  background: var(--bg-canvas);
}

.compare-table th:first-child,
.compare-table td:first-child {
  position: sticky;
  left: 0;
  z-index: 2;
  width: 140px;
  min-width: 140px;
  background: var(--bg-surface);
}

.compare-table th:first-child {
  z-index: 3;
  background: var(--bg-canvas);
}

.compare-table tbody tr:hover td:first-child {
  background: var(--bg-canvas);
}

.compare-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.compare-cell.clickable {
  cursor: pointer;
}

.compare-table td.cell-diff {
  background: linear-gradient(180deg, rgba(204, 251, 241, 0.35) 0%, rgba(239, 246, 255, 0.2) 100%);
}

.compare-table td.cell-diff .compare-cell-content {
  background-image: linear-gradient(var(--academic-primary-light), var(--academic-primary-light));
  background-size: 100% 2px;
  background-repeat: no-repeat;
  background-position: 0 100%;
}

.compare-table td.is-locatable:hover {
  background: var(--bg-canvas);
}

.compare-header-text {
  display: -webkit-box;
  max-height: 42px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow-wrap: anywhere;
  line-height: 1.45;
}

.compare-cell-content {
  max-height: none;
  overflow: visible;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.compare-table-wrap:not(.raw-mode) .compare-cell-content {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}

.table-view-hint {
  margin: 8px 0 0;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.raw-mode .compare-cell-content {
  display: block;
  max-height: 152px;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.45) transparent;
}

.raw-mode .compare-cell-content.expanded {
  max-height: none;
  overflow: visible;
}

.inline-toggle,
.hover-action {
  border: 0;
  background: transparent;
  color: var(--sidebar-accent);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  padding: 0;
}

.compare-cell .hover-action {
  align-self: flex-start;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s ease, visibility 0.15s ease;
}

.compare-table tbody tr:hover .hover-action,
.compare-cell .hover-action:focus-visible,
.compare-cell-content.expanded + .hover-action {
  opacity: 1;
  visibility: visible;
}

.analysis-sections {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  margin-top: 16px;
  background: var(--bg-surface);
  box-shadow: 0 0 0 1px var(--border-light);
  border-radius: 8px;
  overflow: hidden;
}

.evidence-panel {
  --ev-strong: #2563eb;
  --ev-strong-soft: rgba(37, 99, 235, 0.14);
  --ev-strong-text: #1d4ed8;
  --ev-medium: #3b82f6;
  --ev-medium-soft: rgba(59, 130, 246, 0.14);
  --ev-medium-text: #1e40af;
  --ev-related: #14b8a6;
  --ev-related-soft: rgba(20, 184, 166, 0.16);
  --ev-related-text: #0f766e;
  --ev-weak: #94a3b8;
  --ev-weak-soft: rgba(148, 163, 184, 0.2);
  --ev-weak-text: #64748b;

  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--border-light);
}

.evidence-panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-heading);
}

.evidence-panel-head {
  margin-bottom: 12px;
}

.evidence-panel-hint {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.evidence-panel-question {
  margin: 6px 0 0;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.analysis-section {
  padding: 16px 18px;
  border-right: 1px solid var(--border-lighter);
}

.analysis-section:last-child {
  border-right: none;
}

.analysis-section ul {
  display: grid;
  gap: 7px;
  margin: 10px 0 0;
  padding-left: 17px;
}

.analysis-section li,
.analysis-section p,
.raw-result {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.dimension-section {
  background: var(--bg-surface);
  border-radius: 12px;
  margin-bottom: 20px;
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.dimension-header {
  padding: 12px 16px;
  background: rgba(239, 246, 255, 0.75);
  color: var(--sidebar-accent);
  font-weight: 600;
  font-size: 14px;
  border-bottom: 1px solid var(--sidebar-border);
}

.dimension-body {
  padding: 0 16px 16px;
}

.evidence-group {
  border-top: 1px solid var(--border-lighter);
  padding-top: 14px;
}

.dimension-body .evidence-group:first-child {
  border-top: none;
  padding-top: 12px;
}

.evidence-item {
  position: relative;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
  padding: 12px 16px 12px 20px;
  border: none;
  border-bottom: 1px solid var(--border-lighter);
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  line-height: 1.55;
  transition: background 0.12s ease, box-shadow 0.12s ease;
  border-radius: 0 8px 8px 0;
}

.evidence-item::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 2px;
  background: var(--ev-weak);
}

.evidence-item.support-strong {
  background: var(--ev-strong-soft);
}

.evidence-item.support-strong::before {
  background: var(--ev-strong);
}

.evidence-item.support-medium {
  background: var(--ev-medium-soft);
}

.evidence-item.support-medium::before {
  background: var(--ev-medium);
}

.evidence-item.support-related {
  background: var(--ev-related-soft);
}

.evidence-item.support-related::before {
  background: var(--ev-related);
}

.evidence-item.support-weak {
  background: var(--ev-weak-soft);
}

.evidence-item.support-weak::before {
  background: var(--ev-weak);
}

.evidence-item:hover {
  background: rgba(239, 246, 255, 0.65);
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.45);
}

.evidence-item.support-strong:hover {
  background: rgba(37, 99, 235, 0.18);
}

.evidence-item.support-medium:hover {
  background: rgba(59, 130, 246, 0.18);
}

.evidence-item.support-related:hover {
  background: rgba(20, 184, 166, 0.2);
}

.evidence-item.support-weak:hover {
  background: rgba(148, 163, 184, 0.28);
}

.evidence-item:hover .evidence-hover-actions {
  opacity: 1;
  visibility: visible;
}

.evidence-hover-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s ease, visibility 0.15s ease;
}

.evidence-hover-actions .hover-action:focus-visible {
  opacity: 1;
  visibility: visible;
}

.evidence-item-head {
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 10px;
}

.evidence-item-head strong {
  color: var(--text-heading);
  font-size: 13px;
  line-height: 1.4;
}

.evidence-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 5px;
}

.evidence-tags em {
  border-radius: 999px;
  background: rgba(239, 246, 255, 0.85);
  color: var(--text-secondary);
  font-size: 11px;
  font-style: normal;
  line-height: 1;
  padding: 5px 8px;
  border: 1px solid rgba(226, 232, 240, 0.5);
}

.evidence-tags .support-tag {
  border-radius: 999px;
  padding: 5px 8px;
  font-weight: 600;
  border: 1px solid transparent;
}

.evidence-tags .support-tag.strong {
  background: var(--ev-strong-soft);
  color: var(--ev-strong-text);
  border-color: rgba(37, 99, 235, 0.28);
}

.evidence-tags .support-tag.medium {
  background: var(--ev-medium-soft);
  color: var(--ev-medium-text);
  border-color: rgba(59, 130, 246, 0.28);
}

.evidence-tags .support-tag.related {
  background: var(--ev-related-soft);
  color: var(--ev-related-text);
  border-color: rgba(20, 184, 166, 0.32);
}

.evidence-tags .support-tag.weak {
  background: var(--ev-weak-soft);
  color: var(--ev-weak-text);
  border-color: rgba(148, 163, 184, 0.45);
}

.evidence-snippet {
  display: -webkit-box;
  max-height: 96px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.evidence-snippet.expanded {
  display: block;
  max-height: 220px;
  overflow: auto;
  -webkit-line-clamp: unset;
}

.empty-note {
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-canvas);
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 960px) {
  .compare-sidebar-wrapper {
    width: 220px;
  }

  .compare-sidebar {
    width: 220px;
  }

  .compare-sidebar-toggle {
    left: 200px;
  }

  .analysis-sections {
    grid-template-columns: 1fr;
  }

  .analysis-section {
    border-right: none;
    border-bottom: 1px solid var(--border-lighter);
  }

  .analysis-section:last-child {
    border-bottom: none;
  }
}

@media (max-width: 640px) {
  .compare-body {
    padding: 16px;
  }

  .compare-tabs,
  .compare-header {
    padding-left: 16px;
    padding-right: 16px;
  }

  .result-title-row,
  .evidence-item-head {
    flex-direction: column;
  }

  .evidence-tags {
    justify-content: flex-start;
  }
}
</style>
