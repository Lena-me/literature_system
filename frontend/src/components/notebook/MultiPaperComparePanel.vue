<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { featuresApi } from '@/api/features'
import type { SessionPaper, Source } from '@/types/domain'

const props = defineProps<{
  visible: boolean
  papers: SessionPaper[]
}>()

const emit = defineEmits<{
  close: []
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

const activeTab = ref<'setup' | 'result' | 'evidence' | 'history'>('setup')
const selectedIds = ref<number[]>([])
const selectedDimensions = ref<string[]>([...defaultDimensionValues])
const compareName = ref('')
const evidenceQuestion = ref('')
const compareLoading = ref(false)
const evidenceLoading = ref(false)
const historyLoading = ref(false)
const nameLoading = ref(false)
const nameTouched = ref(false)
const compareResult = ref<any>(null)
const evidenceResult = ref<any>(null)
const history = ref<any[]>([])

const completedPapers = computed(() =>
  props.papers.filter(p => completedStatuses.has(String(p.parse_status || '').toLowerCase()))
)

const selectedPapers = computed(() =>
  completedPapers.value.filter(p => selectedIds.value.includes(p.id))
)

const resultData = computed(() => compareResult.value?.result || compareResult.value || {})

const compareSummary = computed(() => {
  return {
    difference: resultData.value.difference_analysis || resultData.value.differences || '',
    trend: resultData.value.trend_summary || '',
    future: resultData.value.future_direction || '',
  }
})

const comparisonTable = computed(() => {
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

function paperTitle(paper: SessionPaper) {
  return paper.title || paper.original_filename || `Paper ${paper.id}`
}

function tableHeader(key: string) {
  if (key === 'dimension') return '对比维度'

  const paper = resultPapers.value.find((p: any) => p.key === key)
  if (paper?.title) return paper.title

  return key
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

async function generateCompareName(force = false) {
  if (selectedIds.value.length < 2) {
    compareName.value = fallbackCompareName()
    return
  }
  if (!force && nameTouched.value) return

  nameLoading.value = true
  try {
    const res = await featuresApi.suggestCompareName({
      paper_ids: selectedIds.value,
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
  compareResult.value = null
  evidenceResult.value = null
  selectedDimensions.value = [...defaultDimensionValues]
  selectedIds.value = completedPapers.value.slice(0, 5).map(p => p.id)
  evidenceQuestion.value = defaultEvidenceQuestion()
  compareName.value = fallbackCompareName()
  nameTouched.value = false
  void generateCompareName()
}

watch(
  () => props.visible,
  visible => {
    if (!visible) return
    resetPanel()
    loadHistory()
  }
)

watch(selectedDimensions, () => {
  void generateCompareName()
})

watch(selectedIds, () => {
  if (!nameTouched.value) {
    compareName.value = fallbackCompareName()
  }
  void generateCompareName()
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
  activeTab.value = 'result'
}

async function deleteHistoryItem(item: any) {
  try {
    await ElMessageBox.confirm('确定删除这条对比历史吗？', '删除历史记录', { type: 'warning' })
    await featuresApi.deleteCompare(item.id)
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
</script>

<template>
  <Transition name="compare-panel-slide">
    <aside v-if="visible" class="compare-panel">
      <header class="panel-head">
        <div>
          <h2>多文献对比</h2>
          <p>基于当前 Notebook 挂载文献生成横向分析</p>
        </div>
        <button class="icon-button" title="关闭" @click="emit('close')">×</button>
      </header>

      <div class="panel-tabs">
        <button :class="{ active: activeTab === 'setup' }" @click="activeTab = 'setup'">设置</button>
        <button :class="{ active: activeTab === 'result' }" @click="activeTab = 'result'" :disabled="!compareResult">对比结果</button>
        <button :class="{ active: activeTab === 'evidence' }" @click="activeTab = 'evidence'" :disabled="!evidenceResult">证据矩阵</button>
        <button :class="{ active: activeTab === 'history' }" @click="activeTab = 'history'">历史</button>
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
            当前会话至少需要 2 篇 completed 或 indexed 文献。
          </div>
          <label
            v-for="paper in props.papers"
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
          <h3>{{ compareResult?.name || '多文献对比结果' }}</h3>
          <p>{{ selectedPapers.map(paperTitle).join(' · ') }}</p>
        </div>

        <div v-if="comparisonTable.length" class="compare-table-wrap">
          <table class="compare-table">
            <thead>
              <tr>
                <th v-for="key in comparisonTableKeys" :key="key">{{ tableHeader(key) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in comparisonTable" :key="idx">
                <td v-for="key in comparisonTableKeys" :key="key">{{ row[key] || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="raw-result">
          {{ compareResult?.result || compareResult || '暂无结果' }}
        </div>

        <div class="analysis-grid">
          <div>
            <h4>差异分析</h4>
            <p>{{ compareSummary.difference || '暂无差异分析' }}</p>
          </div>
          <div>
            <h4>研究趋势</h4>
            <p>{{ compareSummary.trend || '暂无趋势总结' }}</p>
          </div>
          <div>
            <h4>未来方向</h4>
            <p>{{ compareSummary.future || '暂无未来方向' }}</p>
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
              <button
                v-for="evidence in row.evidences || []"
                :key="`${dimension.dimension_key}-${evidence.paper_id}-${evidence.page_number}-${evidence.snippet}`"
                class="evidence-item"
                @click="openEvidenceSource(evidence)"
              >
                <span>{{ evidence.snippet }}</span>
                <em>
                  <template v-if="evidence.page_number">Page {{ evidence.page_number }} · </template>
                  {{ evidence.section_title || '正文片段' }}
                  · {{ evidence.support || 'related' }}
                </em>
              </button>
              <div v-if="!(row.evidences || []).length" class="empty-note">
                该文献在此维度下暂未检索到高质量证据。
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-for="row in evidenceResult?.rows || []" :key="row.paper_id" class="evidence-group">
            <h4>{{ row.title }}</h4>
            <button
              v-for="evidence in row.evidences || []"
              :key="`${evidence.paper_id}-${evidence.page_number}-${evidence.snippet}`"
              class="evidence-item"
              @click="openEvidenceSource(evidence)"
            >
              <span>{{ evidence.snippet }}</span>
              <em>
                <template v-if="evidence.page_number">Page {{ evidence.page_number }} · </template>
                {{ evidence.section_title || '正文片段' }}
                · {{ evidence.support || 'related' }}
              </em>
            </button>
          </div>
        </template>
      </section>

      <section v-else class="panel-body slim-scroll">
        <div class="section-title">
          <span>最近对比历史</span>
          <button class="ghost-action" :disabled="historyLoading" @click="loadHistory">刷新</button>
        </div>
        <div v-if="!history.length" class="empty-note">暂无历史记录</div>
        <div v-for="item in history" :key="item.id" class="history-row">
          <button @click="openHistoryItem(item)">
            <strong>{{ item.name || '未命名对比' }}</strong>
            <em>{{ (item.paper_ids || []).length }} 篇文献 · {{ item.created_at }}</em>
          </button>
          <button class="delete-action" @click="deleteHistoryItem(item)">删除</button>
        </div>
      </section>
    </aside>
  </Transition>
</template>

<style scoped>
.compare-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(680px, 58vw);
  min-width: 460px;
  z-index: 35;
  display: flex;
  flex-direction: column;
  background: var(--academic-panel);
  border-left: 1px solid var(--academic-border);
  box-shadow: var(--shadow-float);
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
}

.compare-table th,
.compare-table td {
  min-width: 150px;
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

.analysis-grid {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.analysis-grid > div,
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
  gap: 6px;
  margin-top: 8px;
  padding: 10px;
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

.compare-panel-slide-enter-active,
.compare-panel-slide-leave-active {
  transition: transform 0.25s ease;
}

.compare-panel-slide-enter-from,
.compare-panel-slide-leave-to {
  transform: translateX(100%);
}

@media (max-width: 820px) {
  .compare-panel {
    width: 100%;
    min-width: 0;
  }
}
</style>
