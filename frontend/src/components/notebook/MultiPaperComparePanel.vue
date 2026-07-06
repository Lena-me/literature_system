<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { featuresApi } from '@/api/features'
import { usePaperStore } from '@/stores/papers'
import type { Paper, Source } from '@/types/domain'

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

const activeTab = ref<'setup' | 'result' | 'evidence'>('setup')
const activeHistoryId = ref<number | null>(null)
const selectedIds = ref<number[]>([])
const selectedDimensions = ref<string[]>([...defaultDimensionValues])
const compareName = ref('')
const evidenceQuestion = ref('')
const compareLoading = ref(false)
const evidenceLoading = ref(false)
const historyLoading = ref(false)
const nameLoading = ref(false)
const nameTouched = ref(false)
const tableViewMode = ref<'zh' | 'raw'>('zh')
const compareResult = ref<any>(null)
const evidenceResult = ref<any>(null)
const history = ref<any[]>([])
const expandedCompareCells = ref<Set<string>>(new Set())
const expandedEvidenceItems = ref<Set<string>>(new Set())

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
  return [
    { key: 'overview', title: '总体总结', items: toItems(resultData.value.summary) },
    { key: 'differences', title: '差异分析', items: pickItems(resultData.value.key_differences, compareSummary.value.difference) },
    { key: 'trends', title: '研究趋势', items: pickItems(resultData.value.common_trends, compareSummary.value.trend) },
    { key: 'gaps', title: '研究空白', items: pickItems(resultData.value.research_gaps, compareSummary.value.gaps) },
    { key: 'future', title: '未来方向', items: pickItems(resultData.value.future_directions, compareSummary.value.future) },
  ].filter(card => card.items.length)
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

const allDimensionsSelected = computed(() =>
  selectedDimensions.value.length === allDimensionValues.length
)

const evidenceDimensions = computed(() => {
  return Array.isArray(evidenceResult.value?.dimensions) ? evidenceResult.value.dimensions : []
})

function paperTitle(paper: Paper) {
  return paper.title || paper.original_filename || `Paper ${paper.id}`
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

function toggleAllDimensions(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  selectedDimensions.value = checked ? [...allDimensionValues] : []
}

function dimensionLabel(key: string) {
  return dimensionOptions.find(x => x.value === key)?.label || key
}

function fallbackCompareName() {
  const names = selectedPapers.value.slice(0, 2).map(p => paperTitle(p))
  if (names.length >= 2) {
    return `多文献对比：${names[0]} 等 ${selectedPapers.value.length} 篇文献`.slice(0, 80)
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
    return
  }
  if (!force && nameTouched.value) return

  nameLoading.value = true
  try {
    const res = await featuresApi.suggestCompareName({
      paper_ids: ids,
      dimensions: selectedDimensions.value,
    })
    compareName.value = res?.name || fallbackCompareName()
    nameTouched.value = false
  } catch {
    compareName.value = fallbackCompareName()
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
  void generateCompareName()
}

watch(selectedIds, () => {
  if (!nameTouched.value) {
    compareName.value = fallbackCompareName()
  }
  void generateCompareName()
})

watch(selectedDimensions, () => {
  void generateCompareName()
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
    await loadHistory()
    activeHistoryId.value = compareResult.value?.id ?? null
    activeTab.value = 'result'
    ElMessage.success('多文献对比已生成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '多文献对比生成失败')
  } finally {
    compareLoading.value = false
  }
}

async function runEvidence() {
  if (selectedIds.value.length < 1) {
    ElMessage.warning('请先选择文献')
    return
  }

  evidenceLoading.value = true
  try {
    evidenceResult.value = await featuresApi.evidenceMatrix({
      paper_ids: selectedIds.value,
      question: evidenceQuestion.value || undefined,
      dimensions: selectedDimensions.value,
    })
    activeTab.value = 'evidence'
    ElMessage.success('证据矩阵已生成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '证据矩阵生成失败')
  } finally {
    evidenceLoading.value = false
  }
}

async function openHistoryItem(item: any) {
  try {
    compareResult.value = await featuresApi.compareDetail(item.id)
  } catch {
    compareResult.value = item
  }
  selectedIds.value = Array.isArray(compareResult.value?.paper_ids) ? compareResult.value.paper_ids : selectedIds.value
  activeHistoryId.value = item.id
  activeTab.value = 'result'
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

async function deleteHistoryItem(item: any) {
  try {
    await ElMessageBox.confirm('确定删除这条对比历史吗？', '删除历史记录', { type: 'warning' })
    await featuresApi.deleteCompare(item.id)
    if (activeHistoryId.value === item.id) {
      activeHistoryId.value = null
      compareResult.value = null
      activeTab.value = 'setup'
    }
    await loadHistory()
    ElMessage.success('已删除对比历史')
  } catch (e: any) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

function openEvidenceSource(evidence: any) {
  const source = evidence?.source || {
    paper_id: evidence.paper_id,
    page_number: evidence.page_number,
    section_title: evidence.section_title,
    snippet: evidence.snippet,
  }
  emit('sourceClick', source)
}

function compareCellKey(rowIndex: number, key: string) {
  return `${tableViewMode.value}-${rowIndex}-${key}`
}

function isCompareCellExpanded(rowIndex: number, key: string) {
  return expandedCompareCells.value.has(compareCellKey(rowIndex, key))
}

function shouldShowCompareToggle(value: unknown) {
  return tableViewMode.value === 'raw' && String(value || '').length > 160
}

function toggleCompareCell(rowIndex: number, key: string) {
  const id = compareCellKey(rowIndex, key)
  const next = new Set(expandedCompareCells.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedCompareCells.value = next
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

function evidenceTitle(row: any, evidence: any) {
  return shortPaperHeader(row?.title || evidence?.title || evidence?.source?.title || `Paper ${evidence?.paper_id || ''}`)
}

function evidenceSupport(evidence: any) {
  return String(evidence?.support || evidence?.strength || 'related').toLowerCase()
}
</script>

<template>
  <div class="compare-page">
    <aside class="history-panel">
      <div class="sidebar-head">
        <h3>多文献对比</h3>
        <span class="count">{{ history.length }} 条</span>
      </div>
      <button class="new-compare-btn" @click="startNewCompare">新建对比</button>
      <div class="history-list slim-scroll">
        <div v-if="historyLoading" class="empty-note">加载中...</div>
        <div v-else-if="!history.length" class="empty-note">暂无历史记录</div>
        <div
          v-for="item in history"
          :key="item.id"
          class="history-card"
          :class="{ active: activeHistoryId === item.id }"
        >
          <button class="history-card-main" @click="openHistoryItem(item)">
            <strong>{{ item.name || '未命名对比' }}</strong>
            <em>{{ (item.paper_ids || []).length }} 篇文献 · {{ item.created_at }}</em>
          </button>
          <button class="delete-action" title="删除" @click="deleteHistoryItem(item)">删除</button>
        </div>
      </div>
      <button class="ghost-action refresh-btn" :disabled="historyLoading" @click="loadHistory">刷新历史</button>
    </aside>

    <section class="main-panel">
      <header class="panel-head">
        <div>
          <h2>多文献对比</h2>
          <p>从文献库选择已解析文献，生成横向对比分析</p>
        </div>
      </header>

      <div class="panel-tabs">
        <button :class="{ active: activeTab === 'setup' }" @click="activeTab = 'setup'">设置</button>
        <button :class="{ active: activeTab === 'result' }" @click="activeTab = 'result'" :disabled="!compareResult">对比结果</button>
        <button :class="{ active: activeTab === 'evidence' }" @click="activeTab = 'evidence'" :disabled="!evidenceResult">证据矩阵</button>
      </div>

      <section v-if="activeTab === 'setup'" class="panel-body slim-scroll">
        <div class="section-block config-block">
          <div class="section-title">
            <span>对比配置</span>
          </div>

          <div class="field-head">
            <label class="field-label">对比记录名称</label>
            <button
              class="inline-action"
              :disabled="nameLoading || selectedIds.length < 2"
              @click="generateCompareName(true)"
            >
              {{ nameLoading ? '生成中...' : 'LLM 生成' }}
            </button>
          </div>
          <input
            v-model="compareName"
            class="text-field"
            placeholder="用于保存到历史记录"
            @input="nameTouched = true"
          />
          <p class="field-help">
            用于在“历史”中识别本次对比记录；默认由 LLM 根据所选文献和维度生成。
          </p>

          <label class="field-label">证据检索问题</label>
          <textarea
            v-model="evidenceQuestion"
            class="text-area"
            rows="3"
            placeholder="可选：输入额外关注点。不填写时，系统会按所选维度自动检索证据。"
          />
          <p class="field-help">
            用于从原文中检索支撑本次对比结论的证据片段；系统会按所选维度分别检索。
          </p>
        </div>

        <div class="section-block">
          <div class="section-title">
            <span>选择文献</span>
            <b>{{ selectedIds.length }}/{{ completedPapers.length }}</b>
          </div>
          <div v-if="completedPapers.length < 2" class="empty-note">
            文献库中至少需要 2 篇已完成解析（completed / indexed）的文献。
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
              <em>{{ paper.parse_status || 'unknown' }}</em>
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
              <b>{{ selectedDimensions.length }}/{{ dimensionOptions.length }}</b>
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
          <button class="primary-action" :disabled="compareLoading" @click="runCompare">
            {{ compareLoading ? '生成中...' : '生成对比' }}
          </button>
          <button class="secondary-action" :disabled="evidenceLoading" @click="runEvidence">
            {{ evidenceLoading ? '检索中...' : '生成证据矩阵' }}
          </button>
        </div>
      </section>

      <section v-else-if="activeTab === 'result'" class="panel-body slim-scroll">
        <div class="result-meta">
          <div class="result-title-row">
            <div>
              <h3>{{ compareResult?.name || '多文献对比结果' }}</h3>
              <p>{{ selectedPapers.map(paperTitle).join(' · ') }}</p>
            </div>
            <div class="table-view-switch" aria-label="对比表展示模式">
              <button
                type="button"
                :class="{ active: tableViewMode === 'zh' }"
                @click="tableViewMode = 'zh'"
              >
                中文总结
              </button>
              <button
                type="button"
                :class="{ active: tableViewMode === 'raw' }"
                @click="tableViewMode = 'raw'"
              >
                原始解析
              </button>
            </div>
          </div>
        </div>

        <div v-if="comparisonTable.length" class="compare-table-wrap" :class="{ 'raw-mode': tableViewMode === 'raw' }">
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
                <td v-for="key in comparisonTableKeys" :key="key">
                  <div
                    class="compare-cell-content"
                    :class="{ expanded: isCompareCellExpanded(idx, key) }"
                  >
                    {{ row[key] || '-' }}
                  </div>
                  <button
                    v-if="shouldShowCompareToggle(row[key])"
                    type="button"
                    class="inline-toggle"
                    @click.stop="toggleCompareCell(idx, key)"
                  >
                    {{ isCompareCellExpanded(idx, key) ? '收起' : '展开' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="raw-result">
          {{ compareResult?.result || compareResult || '暂无结果' }}
        </div>

        <div class="analysis-grid">
          <div v-for="card in summaryCards" :key="card.key" class="analysis-card">
            <h4>{{ card.title }}</h4>
            <ul>
              <li v-for="(item, idx) in card.items" :key="idx">{{ item }}</li>
            </ul>
          </div>
          <div v-if="!summaryCards.length" class="analysis-card">
            <h4>综合分析</h4>
            <p>暂无总结内容</p>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'evidence'" class="panel-body slim-scroll">
        <div class="result-meta">
          <h3>证据矩阵</h3>
          <p>{{ evidenceResult?.question || evidenceQuestion }}</p>
        </div>
        <template v-if="evidenceDimensions.length">
          <div
            v-for="dimension in evidenceDimensions"
            :key="dimension.dimension_key"
            class="evidence-dimension"
          >
            <h3>{{ dimension.label || dimensionLabel(dimension.dimension_key) }}</h3>
            <p>{{ dimension.query }}</p>

            <div
              v-for="row in dimension.rows || []"
              :key="`${dimension.dimension_key}-${row.paper_id}`"
              class="evidence-group"
            >
              <h4>{{ row.title }}</h4>
              <div
                v-for="evidence in row.evidences || []"
                :key="`${dimension.dimension_key}-${evidence.paper_id}-${evidence.page_number}-${evidence.snippet}`"
                class="evidence-item"
                role="button"
                tabindex="0"
                @click="openEvidenceSource(evidence)"
                @keydown.enter="openEvidenceSource(evidence)"
              >
                <div class="evidence-item-head">
                  <strong :title="row.title">{{ evidenceTitle(row, evidence) }}</strong>
                  <span class="evidence-tags">
                    <em v-if="evidence.page_number">Page {{ evidence.page_number }}</em>
                    <em>{{ evidence.section_title || '正文片段' }}</em>
                    <em :class="['support-tag', evidenceSupport(evidence)]">{{ evidence.support || 'related' }}</em>
                  </span>
                </div>
                <span class="evidence-snippet" :class="{ expanded: isEvidenceExpanded(evidence, dimension.dimension_key) }">
                  {{ evidence.snippet }}
                </span>
                <button
                  v-if="shouldShowEvidenceToggle(evidence)"
                  type="button"
                  class="inline-toggle"
                  @click.stop="toggleEvidenceItem(evidence, dimension.dimension_key)"
                >
                  {{ isEvidenceExpanded(evidence, dimension.dimension_key) ? '收起原文' : '展开原文' }}
                </button>
              </div>
              <div v-if="!(row.evidences || []).length" class="empty-note">
                该文献在此维度下暂未检索到高质量证据。
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-for="row in evidenceResult?.rows || []" :key="row.paper_id" class="evidence-group">
            <h4>{{ row.title }}</h4>
            <div
              v-for="evidence in row.evidences || []"
              :key="`${evidence.paper_id}-${evidence.page_number}-${evidence.snippet}`"
              class="evidence-item"
              role="button"
              tabindex="0"
              @click="openEvidenceSource(evidence)"
              @keydown.enter="openEvidenceSource(evidence)"
            >
              <div class="evidence-item-head">
                <strong :title="row.title">{{ evidenceTitle(row, evidence) }}</strong>
                <span class="evidence-tags">
                  <em v-if="evidence.page_number">Page {{ evidence.page_number }}</em>
                  <em>{{ evidence.section_title || '正文片段' }}</em>
                  <em :class="['support-tag', evidenceSupport(evidence)]">{{ evidence.support || 'related' }}</em>
                </span>
              </div>
              <span class="evidence-snippet" :class="{ expanded: isEvidenceExpanded(evidence, 'flat') }">
                {{ evidence.snippet }}
              </span>
              <button
                v-if="shouldShowEvidenceToggle(evidence)"
                type="button"
                class="inline-toggle"
                @click.stop="toggleEvidenceItem(evidence, 'flat')"
              >
                {{ isEvidenceExpanded(evidence, 'flat') ? '收起原文' : '展开原文' }}
              </button>
            </div>
          </div>
        </template>
      </section>
    </section>
  </div>
</template>

<style scoped>
.compare-page {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 16px;
  height: 100%;
  padding: 20px;
  box-sizing: border-box;
}

.history-panel {
  border-radius: 20px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 18px 12px;
  border-bottom: 1px solid var(--academic-border);
}

.sidebar-head h3 {
  margin: 0;
  font-size: 16px;
  color: var(--academic-text-main);
}

.count {
  font-size: 12px;
  color: var(--academic-text-muted);
}

.new-compare-btn {
  margin: 12px 14px 0;
  padding: 10px 14px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #7c3aed, #6366f1);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.history-list {
  flex: 1;
  overflow: auto;
  padding: 10px 12px;
}

.history-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  margin-bottom: 6px;
  border-radius: 10px;
  border: 1px solid transparent;
}

.history-card.active {
  border-color: rgba(124, 58, 237, 0.35);
  background: rgba(124, 58, 237, 0.08);
}

.history-card-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  padding: 0;
}

.refresh-btn {
  margin: 8px 14px 14px;
}

.main-panel {
  border-radius: 20px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--academic-border);
  background: var(--academic-canvas);
}

.panel-head h2,
.result-meta h3,
.analysis-grid h4,
.evidence-group h4 {
  margin: 0;
  letter-spacing: 0;
}

.panel-head h2 {
  font-size: 18px;
}

.panel-head p,
.result-meta p {
  margin: 4px 0 0;
  color: var(--academic-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.result-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.table-view-switch {
  display: inline-flex;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: #fff;
}

.table-view-switch button {
  border: 0;
  border-right: 1px solid var(--academic-border);
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  padding: 8px 12px;
  white-space: nowrap;
}

.table-view-switch button:last-child {
  border-right: 0;
}

.table-view-switch button.active {
  background: var(--academic-primary);
  color: #fff;
}

.icon-button {
  width: 34px;
  height: 34px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: #fff;
  color: var(--academic-text-muted);
  cursor: pointer;
  font-size: 22px;
  line-height: 1;
}

.panel-tabs {
  display: flex;
  gap: 6px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--academic-border);
}

.panel-tabs button,
.ghost-action {
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  padding: 7px 11px;
  font-size: 13px;
}

.panel-tabs button.active {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  font-weight: 700;
}

.panel-tabs button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.panel-body {
  flex: 1;
  overflow: auto;
  padding: 18px;
}

.section-block {
  padding: 14px 0 18px;
  border-bottom: 1px solid var(--academic-border);
}

.section-block:first-child {
  padding-top: 0;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--academic-text-main);
  font-size: 14px;
  font-weight: 700;
}

.section-title b {
  color: var(--academic-primary);
  font-size: 12px;
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
  color: var(--academic-text-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.select-all-box input {
  margin: 0;
}

.paper-option {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: flex-start;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
}

.paper-option input {
  margin-top: 2px;
}

.dimension-option {
  display: flex;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
}

.paper-option:hover,
.dimension-option:hover,
.history-row:hover {
  background: var(--academic-primary-light);
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

.dimension-option strong,
.history-row strong {
  color: var(--academic-text-main);
  font-size: 13px;
  line-height: 1.35;
}

.paper-option strong {
  display: block;
  width: 100%;
  color: var(--academic-text-main);
  font-size: 13px;
  line-height: 1.35;
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  overflow-wrap: anywhere;
}

.paper-option em,
.dimension-option em,
.history-row em,
.evidence-item em {
  color: var(--academic-text-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.4;
}

.field-label {
  display: block;
  margin: 12px 0 6px;
  color: var(--academic-text-main);
  font-size: 13px;
  font-weight: 700;
}

.field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.field-head .field-label {
  margin: 0 0 6px;
}

.inline-action {
  padding: 5px 9px;
  border-radius: 8px;
  border: 1px solid var(--academic-border);
  background: #fff;
  color: var(--academic-primary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.inline-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.field-help {
  margin: 6px 0 0;
  color: var(--academic-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.text-field,
.text-area {
  width: 100%;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  padding: 9px 10px;
  color: var(--academic-text-body);
  font: inherit;
  line-height: 1.5;
  outline: none;
  resize: vertical;
}

.text-field:focus,
.text-area:focus {
  border-color: var(--academic-primary);
}

.action-row {
  display: flex;
  gap: 10px;
  padding-top: 16px;
}

.primary-action,
.secondary-action,
.delete-action {
  border-radius: 8px;
  border: 1px solid var(--academic-border);
  cursor: pointer;
  font-weight: 700;
  padding: 10px 14px;
}

.primary-action {
  background: var(--academic-primary);
  border-color: var(--academic-primary);
  color: #fff;
}

.secondary-action {
  background: #fff;
  color: var(--academic-primary);
}

.primary-action:disabled,
.secondary-action:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.compare-table-wrap {
  overflow: auto;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: #fff;
}

.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  table-layout: fixed;
}

.compare-table th,
.compare-table td {
  min-width: 190px;
  padding: 10px;
  border-bottom: 1px solid var(--academic-border);
  text-align: left;
  vertical-align: top;
  line-height: 1.55;
}

.compare-table th {
  color: var(--academic-text-main);
  background: var(--academic-canvas);
  font-weight: 700;
}

.compare-table th:first-child,
.compare-table td:first-child {
  position: sticky;
  left: 0;
  z-index: 2;
  width: 132px;
  min-width: 132px;
  background: #fff;
  box-shadow: 1px 0 0 var(--academic-border);
}

.compare-table th:first-child {
  z-index: 3;
  background: var(--academic-canvas);
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

.raw-mode .compare-cell-content {
  max-height: 152px;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.45) transparent;
}

.raw-mode .compare-cell-content.expanded {
  max-height: none;
  overflow: visible;
}

.raw-mode .compare-cell-content::-webkit-scrollbar,
.evidence-snippet::-webkit-scrollbar {
  width: 4px;
  height: 4px;
}

.raw-mode .compare-cell-content::-webkit-scrollbar-thumb,
.evidence-snippet::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.45);
  border-radius: 999px;
}

.raw-mode .compare-cell-content::-webkit-scrollbar-track,
.evidence-snippet::-webkit-scrollbar-track {
  background: transparent;
}

.inline-toggle {
  margin-top: 6px;
  border: 0;
  background: transparent;
  color: var(--academic-primary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  padding: 0;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.analysis-card {
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: #fff;
  padding: 14px 16px;
}

.analysis-card h4 {
  color: var(--academic-text-main);
  font-size: 14px;
}

.analysis-card ul {
  display: grid;
  gap: 7px;
  margin: 10px 0 0;
  padding-left: 17px;
}

.analysis-card li,
.analysis-card p {
  color: var(--academic-text-body);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.evidence-group {
  border-top: 1px solid var(--academic-border);
  padding-top: 14px;
}

.evidence-dimension {
  padding: 16px 0;
  border-top: 1px solid var(--academic-border);
}

.evidence-dimension:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.evidence-dimension h3 {
  margin: 0;
  color: var(--academic-text-main);
  font-size: 15px;
  letter-spacing: 0;
}

.evidence-dimension > p {
  margin: 5px 0 12px;
  color: var(--academic-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.analysis-grid p,
.raw-result {
  color: var(--academic-text-body);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.evidence-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
  padding: 12px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: #fff;
  color: var(--academic-text-body);
  text-align: left;
  cursor: pointer;
  line-height: 1.55;
}

.evidence-item:hover {
  border-color: var(--academic-primary);
  background: var(--academic-primary-light);
}

.evidence-item-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.evidence-item-head strong {
  color: var(--academic-text-main);
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
  background: var(--academic-canvas);
  color: var(--academic-text-muted);
  font-size: 11px;
  font-style: normal;
  line-height: 1;
  padding: 5px 7px;
}

.evidence-tags .support-tag.strong {
  background: #dcfce7;
  color: #166534;
}

.evidence-tags .support-tag.medium {
  background: #fef3c7;
  color: #92400e;
}

.evidence-tags .support-tag.weak {
  background: #f1f5f9;
  color: #475569;
}

.evidence-snippet {
  display: -webkit-box;
  max-height: 96px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  color: var(--academic-text-body);
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.45) transparent;
}

.evidence-snippet.expanded {
  display: block;
  max-height: 220px;
  overflow: auto;
  -webkit-line-clamp: unset;
}

.history-row {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 8px;
  padding: 8px;
}

.history-row > button:first-child {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.delete-action {
  padding: 7px 10px;
  background: #fff;
  color: var(--danger);
}

.empty-note {
  padding: 12px;
  border-radius: 8px;
  background: var(--academic-canvas);
  color: var(--academic-text-muted);
  font-size: 13px;
}

@media (max-width: 960px) {
  .compare-page {
    grid-template-columns: 1fr;
    padding: 12px;
  }

  .history-panel {
    max-height: 240px;
  }

  .analysis-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .analysis-grid {
    grid-template-columns: 1fr;
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
