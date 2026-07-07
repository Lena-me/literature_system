<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { papersApi } from '@/api/papers'
import { reportsApi } from '@/api/reports'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import type { Paper, Report, ReportReferenceLink } from '@/types/domain'
import { officialLinkLabel, resolveOfficialPaperUrl } from '@/utils/paperOfficialUrl'

const route = useRoute()
const list = ref<Report[]>([])
const current = ref<Report | null>(null)
const papers = ref<Paper[]>([])
const selectedPaperId = ref<number | null>(null)
const reportTitle = ref('')
const creating = ref(false)
const sidebarCollapsed = ref(false)
const sidebarHovered = ref(false)

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

async function loadReports() {
  list.value = await reportsApi.list()
  const queryId = Number(route.query.id)
  if (queryId && list.value.some(item => item.id === queryId)) {
    current.value = list.value.find(item => item.id === queryId) || list.value[0] || null
  } else {
    current.value = list.value[0] || null
  }
}

watch(() => route.query.id, () => {
  void loadReports()
})

onMounted(async () => {
  await Promise.all([
    loadReports(),
    papersApi.list().then(rows => {
      papers.value = rows
      selectedPaperId.value = rows[0]?.id || null
    }),
  ])
})

function stripStructuredReferenceSection(text: string) {
  return text
    .replace(/\n{2,}##\s*(?:文献溯源链接|可点击文献溯源)\s*\n[\s\S]*$/u, '')
    .replace(/\n{2,}##\s*文献溯源\s*\n\s*可点击参考文献已在结构化文献溯源模块中展示；导出文件会保留完整链接列表。\s*$/u, '')
    .replace(/\n?###\s*原文参考文献溯源\s*\n[\s\S]*?(?=\n###\s*基础知识与拓展检索式|\n##\s|$)/u, '\n')
    .trim()
}

function markdown(r: Report | null) {
  const content = r?.content?.markdown || JSON.stringify(r?.content || {}, null, 2)
  if (r?.content?.reference_links?.length) {
    return stripStructuredReferenceSection(content)
  }
  return content
}

const currentPaper = computed(() =>
  papers.value.find(p => p.id === current.value?.paper_id) || null,
)

const currentOfficialUrl = computed(() =>
  resolveOfficialPaperUrl({ doi: currentPaper.value?.doi }),
)

const visualSummary = computed(() => current.value?.content?.visual_summary || null)
const methodFlow = computed(() => visualSummary.value?.method_flow || [])
const keyDataTable = computed(() => visualSummary.value?.key_data_table || [])
const metricCards = computed(() =>
  (visualSummary.value?.metric_cards || []).filter(card => !isMissingSummaryContent(card.value)),
)
const referenceLinks = computed(() => current.value?.content?.reference_links || [])

const displayTitle = computed(() => shortenReportTitle(current.value?.title || '暂无报告'))
const fullTitle = computed(() => current.value?.title || '暂无报告')

function shortenReportTitle(title: string) {
  const normalized = title.replace(/\s+/g, ' ').trim()
  const aliases = ['ColBERT', 'Triton', 'EnvGraph']
  for (const alias of aliases) {
    if (normalized.toLowerCase().includes(alias.toLowerCase())) {
      return `${alias} 研读报告`
    }
  }
  return normalized.length > 40 ? `${normalized.slice(0, 40)}...` : normalized
}

function openOfficialPaper() {
  if (currentOfficialUrl.value) {
    window.open(currentOfficialUrl.value, '_blank', 'noopener,noreferrer')
  }
}

function referenceTitle(item: ReportReferenceLink) {
  const title = item.title?.trim() || ''
  if (title && !isBadReferenceTitle(title)) {
    return title
  }
  return item.raw?.slice(0, 120) || '未命名参考文献'
}

function isBadReferenceTitle(title: string) {
  const value = title.trim()
  return (
    !value ||
    value.length < 8 ||
    /^(?:19|20)\d{2}$/i.test(value) ||
    /^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)$/i.test(value) ||
    /^[\d.\s]+$/.test(value) ||
    /^\d{4,6}(?:\s+(?:19|20)\d{2})?$/.test(value) ||
    /^(?:arxiv\s+preprint|(?:19|20)\d{2}\s+arxiv\s+preprint)$/i.test(value)
  )
}

function referenceButtonLabel(item: ReportReferenceLink) {
  if (item.url_type === 'doi') return '打开 DOI'
  if (item.url_type === 'arxiv') return '打开 arXiv'
  if (item.url_type === 'official') return '打开论文'
  if (item.url_type === 'scholar') return '学术搜索'
  return '暂无可用链接'
}

function openReference(item: ReportReferenceLink) {
  if (item.url) {
    window.open(item.url, '_blank', 'noopener,noreferrer')
  }
}

function isMissingSummaryContent(content?: string) {
  const value = String(content || '').trim()
  return !value || value === '当前解析未提取到明确证据'
}

function flowKey(step: { title?: string }, index: number) {
  return `${step.title || 'step'}-${index}`
}

async function createReport() {
  if (!selectedPaperId.value || creating.value) return

  creating.value = true
  try {
    const report = await reportsApi.create({
      paper_id: selectedPaperId.value,
      title: reportTitle.value || undefined,
    })
    await loadReports()
    current.value = list.value.find(item => item.id === report.id) || report
    reportTitle.value = ''
    ElMessage.success('研读报告已生成')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '研读报告生成失败')
  } finally {
    creating.value = false
  }
}

async function deleteReport(report: Report) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${report.title || '该报告'}」吗？删除后不可恢复。`,
      '删除研读报告',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  await reportsApi.remove(report.id)
  ElMessage.success('研读报告已删除')
  await loadReports()
}

async function downloadReport(format: 'md' | 'docx' | 'pdf') {
  const reportId = current.value?.id
  if (!reportId) {
    ElMessage.warning('请先选择一份报告')
    return
  }
  if (!list.value.some(item => item.id === reportId)) {
    await loadReports()
    const refreshed = list.value.find(item => item.id === reportId) || null
    if (!refreshed) {
      current.value = null
      ElMessage.warning('当前报告不存在或已被删除，请重新选择报告')
      return
    }
    current.value = refreshed
  }
  try {
    const res = await reportsApi.export(reportId, format)
    const contentType = String(res.headers['content-type'] || 'application/octet-stream')
    const blob = new Blob([res.data], { type: contentType })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${current.value?.title || 'report'}.${format}`
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (error: any) {
    if (error?.response?.status === 404) {
      ElMessage.error('报告不存在或无权访问，请刷新列表后重试')
      await loadReports()
      return
    }
    ElMessage.error('导出失败，请稍后重试')
  }
}
</script>

<template>
  <div class="reports-page">
    <!-- 左侧列表 -->
    <div
      class="report-sidebar-wrapper"
      :class="{ collapsed: sidebarCollapsed }"
      @mouseenter="sidebarHovered = true"
      @mouseleave="sidebarHovered = false"
    >
      <aside class="sidebar-panel">
        <div class="sidebar-head">
          <h3>研读报告</h3>
          <span class="count">{{ list.length }} 份</span>
        </div>

        <div class="create-panel">
          <select v-model.number="selectedPaperId" class="paper-select" :disabled="creating || papers.length === 0">
            <option :value="null" disabled>选择一篇文献</option>
            <option v-for="paper in papers" :key="paper.id" :value="paper.id">
              {{ paper.title || paper.original_filename || `文献 #${paper.id}` }}
            </option>
          </select>
          <input
            v-model="reportTitle"
            class="title-input"
            placeholder="报告标题，可不填"
            :disabled="creating"
          />
          <button class="create-report-btn" :disabled="!selectedPaperId || creating" @click="createReport">
            {{ creating ? '生成中...' : '生成研读报告' }}
          </button>
        </div>

        <div class="sidebar-list slim-scroll">
          <div
            v-for="r in list"
            :key="r.id"
            class="report-card"
            :class="{ active: current?.id === r.id }"
            @click="current = r"
          >
            <div class="r-row">
              <div class="r-title">{{ r.title }}</div>
              <button class="report-delete-btn" title="删除报告" @click.stop="deleteReport(r)">删除</button>
            </div>
            <div class="r-meta">{{ new Date(r.created_at).toLocaleString('zh-CN') }}</div>
          </div>
          <div v-if="list.length === 0" class="empty">暂无报告</div>
        </div>
      </aside>
    </div>

    <button
      class="module-sidebar-toggle"
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

    <!-- 右侧内容 -->
    <section class="reader-panel">
      <div class="reader-head">
        <div class="reader-title" :title="fullTitle">
          <h2>{{ displayTitle }}</h2>
          <p v-if="fullTitle !== displayTitle">{{ fullTitle }}</p>
        </div>
        <div class="reader-actions">
          <button
            v-if="currentOfficialUrl"
            type="button"
            class="official-btn"
            @click="openOfficialPaper"
          >
            {{ officialLinkLabel(currentOfficialUrl) }} ↗
          </button>
          <button :disabled="!current" @click="downloadReport('md')">导出 MD</button>
          <button :disabled="!current" @click="downloadReport('docx')">导出 Word</button>
          <button :disabled="!current" class="primary" @click="downloadReport('pdf')">导出 PDF</button>
        </div>
      </div>
      <div class="reader-body slim-scroll">
        <template v-if="current">
          <section v-if="visualSummary" class="visual-summary">
            <div class="section-title">
              <h3>图表化摘要</h3>
            </div>

            <div v-if="methodFlow.length" class="summary-block">
              <h4>方法流程图</h4>
              <div class="method-flow">
                <template v-for="(step, index) in methodFlow" :key="flowKey(step, index)">
                  <div
                    class="flow-card"
                    :class="{ missing: isMissingSummaryContent(step.content) }"
                  >
                    <div class="flow-index">{{ index + 1 }}</div>
                    <div class="flow-content">
                      <strong>{{ step.title }}</strong>
                      <p :title="step.content">{{ step.content }}</p>
                    </div>
                  </div>
                  <div v-if="index < methodFlow.length - 1" class="flow-arrow" aria-hidden="true">→</div>
                </template>
              </div>
            </div>

            <div v-if="keyDataTable.length" class="summary-block">
              <h4>关键数据表</h4>
              <table class="data-table">
                <thead>
                  <tr>
                    <th>字段</th>
                    <th>内容</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in keyDataTable" :key="row.name">
                    <td>{{ row.name }}</td>
                    <td>{{ row.value }}</td>
                    <td>
                      <span class="status-tag" :class="{ missing: row.status === 'missing' }">
                        {{ row.status === 'missing' ? '未提取到明确证据' : '已提取' }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
              <p v-if="!metricCards.length" class="metric-hint">当前解析未提取到明确数值型指标。</p>
            </div>

            <div v-if="metricCards.length" class="summary-block">
              <h4>指标卡片</h4>
              <div class="metric-grid">
                <div v-for="card in metricCards" :key="`${card.label}-${card.value}`" class="metric-card">
                  <div class="metric-label">{{ card.label }}</div>
                  <div class="metric-value">{{ card.value }}</div>
                  <div v-if="card.note" class="metric-note">{{ card.note }}</div>
                  <div v-if="card.source" class="metric-source">{{ card.source }}</div>
                </div>
              </div>
            </div>
          </section>

          <MarkdownRenderer :content="markdown(current)" />

          <section v-if="referenceLinks.length" class="reference-section">
            <div class="section-title">
              <h3>文献溯源</h3>
            </div>
            <h4 class="reference-subtitle">可点击参考文献</h4>
            <div class="reference-list">
              <article v-for="(item, index) in referenceLinks" :key="`${item.raw}-${index}`" class="reference-card">
                <div class="reference-main">
                  <h4>{{ referenceTitle(item) }}</h4>
                  <div class="reference-meta">
                    <span v-if="item.authors">{{ item.authors }}</span>
                    <span v-if="item.year">{{ item.year }}</span>
                    <span v-if="item.venue">{{ item.venue }}</span>
                  </div>
                  <p v-if="item.reason" class="reference-reason">{{ item.reason }}</p>
                  <details v-if="item.raw" class="reference-raw">
                    <summary>原始参考文献</summary>
                    <p>{{ item.raw }}</p>
                  </details>
                </div>
                <button
                  v-if="item.url"
                  type="button"
                  class="reference-link-btn"
                  @click="openReference(item)"
                >
                  {{ referenceButtonLabel(item) }} ↗
                </button>
                <span v-else class="reference-empty">暂无可用链接</span>
              </article>
            </div>
          </section>
        </template>
        <div v-else class="no-report">
          <p>选择一个报告查看详情</p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.reports-page {
  display: flex;
  gap: 16px;
  height: 100%;
  padding: 20px;
  position: relative;
  overflow: hidden;
}

/* ====== 左侧栏 ====== */
.report-sidebar-wrapper {
  position: relative;
  flex-shrink: 0;
  width: 300px;
  overflow: hidden;
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.report-sidebar-wrapper.collapsed {
  width: 0;
}

.sidebar-panel {
  width: 300px;
  height: 100%;
  border-radius: 20px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-soft);
}

.module-sidebar-toggle {
  position: absolute;
  left: 300px;
  top: 38px;
  z-index: 50;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e2e8f0;
  border-radius: 50%;
  background: #fff;
  color: #64748b;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 0.2s ease, transform 0.2s ease, color 0.15s, left 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}

.module-sidebar-toggle.visible {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.module-sidebar-toggle.collapsed {
  left: 32px;
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.module-sidebar-toggle:hover {
  color: #0f172a;
  border-color: #cbd5e1;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
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

.create-panel {
  display: grid;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--academic-border);
}

.paper-select,
.title-input {
  width: 100%;
  min-width: 0;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  padding: 0 10px;
  font-size: 13px;
  outline: none;
}

.paper-select:focus,
.title-input:focus {
  border-color: var(--academic-primary);
}

.create-report-btn {
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--academic-primary);
  background: var(--academic-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.create-report-btn:hover:not(:disabled) {
  background: var(--academic-primary-hover);
}

.create-report-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.count {
  font-size: 12px;
  color: var(--academic-text-muted);
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px;
}

.report-card {
  padding: 14px;
  border-radius: 14px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.report-card:hover {
  background: rgba(0, 0, 0, 0.02);
}

.report-card.active {
  background: var(--academic-primary-light);
  border-color: var(--academic-primary);
}

.r-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.r-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--academic-text-body);
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.35;
}

.report-delete-btn {
  flex: 0 0 auto;
  border: 1px solid transparent;
  background: transparent;
  color: var(--academic-text-muted);
  border-radius: 6px;
  padding: 3px 6px;
  font-size: 12px;
  cursor: pointer;
}

.report-delete-btn:hover {
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.2);
  background: rgba(220, 38, 38, 0.06);
}

.report-card.active .r-title {
  color: var(--academic-primary);
}

.r-meta {
  font-size: 11px;
  color: var(--academic-text-muted);
  margin-top: 4px;
}

.empty {
  padding: 30px;
  text-align: center;
  color: var(--academic-text-muted);
  font-size: 13px;
}

/* ====== 右侧阅读区 ====== */
.reader-panel {
  flex: 1;
  min-width: 0;
  border-radius: 20px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-soft);
}

.reader-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--academic-border);
  background: var(--academic-canvas);
}

.reader-title {
  flex: 1;
  min-width: 0;
}

.reader-title h2 {
  margin: 0;
  font-size: 20px;
  color: var(--academic-text-main);
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.35;
}

.reader-title p {
  margin: 4px 0 0;
  color: var(--academic-text-muted);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reader-actions {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.reader-actions button {
  padding: 8px 16px;
  border-radius: 10px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.reader-actions button:hover:not(:disabled) {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border-color: var(--academic-primary);
}

.reader-actions button.primary {
  background: var(--academic-primary);
  color: #fff;
  border-color: var(--academic-primary);
}

.reader-actions button.primary:hover:not(:disabled) {
  background: var(--academic-primary-hover);
}

.reader-actions button.official-btn {
  color: #7c3aed;
  border-color: rgba(124, 58, 237, 0.35);
  background: rgba(124, 58, 237, 0.08);
}

.reader-actions button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.reader-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.visual-summary,
.reference-section {
  margin-bottom: 24px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-title h3,
.summary-block h4,
.reference-card h4 {
  margin: 0;
  color: var(--academic-text-main);
}

.section-title h3 {
  font-size: 18px;
}

.summary-block {
  margin-bottom: 18px;
}

.summary-block h4 {
  margin-bottom: 10px;
  font-size: 15px;
}

.method-flow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 28px minmax(0, 1fr) 28px minmax(0, 1fr) 28px minmax(0, 1fr);
  gap: 10px;
  align-items: stretch;
}

.flow-card {
  min-width: 0;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: var(--academic-canvas);
  padding: 14px;
}

.flow-card.missing {
  background: rgba(148, 163, 184, 0.08);
  border-style: dashed;
}

.flow-arrow {
  align-self: center;
  justify-self: center;
  color: var(--academic-text-muted);
  font-weight: 700;
  font-size: 18px;
  line-height: 1;
}

.flow-index {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: var(--academic-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 10px;
}

.flow-content strong {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  color: var(--academic-text-main);
}

.flow-content p,
.muted-line,
.metric-note,
.metric-source,
.reference-reason,
.reference-raw p {
  margin: 0;
  color: var(--academic-text-muted);
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.flow-content p {
  display: -webkit-box;
  max-height: 108px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 5;
}

.flow-card.missing .flow-index {
  background: #94a3b8;
}

.flow-card.missing .flow-content p {
  color: #94a3b8;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  overflow: hidden;
}

.data-table th,
.data-table td {
  border-bottom: 1px solid var(--academic-border);
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
  color: var(--academic-text-body);
  overflow-wrap: anywhere;
}

.data-table th {
  background: var(--academic-canvas);
  color: var(--academic-text-main);
  font-weight: 700;
}

.data-table th:first-child,
.data-table td:first-child {
  width: 150px;
}

.data-table th:last-child,
.data-table td:last-child {
  width: 140px;
}

.status-tag {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.1);
  color: #0369a1;
  font-size: 12px;
  white-space: normal;
}

.status-tag.missing {
  background: rgba(148, 163, 184, 0.16);
  color: #64748b;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.metric-card,
.reference-card {
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: var(--academic-canvas);
}

.metric-card {
  padding: 14px;
}

.metric-label {
  color: var(--academic-text-muted);
  font-size: 12px;
}

.metric-value {
  margin: 6px 0;
  color: var(--academic-primary);
  font-size: 22px;
  font-weight: 800;
  overflow-wrap: anywhere;
  line-height: 1.2;
}

.metric-source {
  margin-top: 8px;
}

.metric-hint {
  margin: 8px 0 0;
  color: var(--academic-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.reference-subtitle {
  margin: -4px 0 10px;
  color: var(--academic-text-main);
  font-size: 15px;
}

.reference-list {
  display: grid;
  gap: 12px;
}

.reference-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 14px;
}

.reference-main {
  min-width: 0;
}

.reference-card h4 {
  font-size: 14px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.reference-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 6px 0;
  color: var(--academic-text-muted);
  font-size: 12px;
}

.reference-reason {
  margin-top: 8px;
}

.reference-raw {
  margin-top: 8px;
  color: var(--academic-text-muted);
  font-size: 12px;
}

.reference-raw summary {
  cursor: pointer;
}

.reference-link-btn {
  flex: 0 0 auto;
  border: 1px solid var(--academic-primary);
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
}

.reference-link-btn:hover {
  background: var(--academic-primary);
  color: #fff;
}

.reference-empty {
  flex: 0 0 auto;
  color: var(--academic-text-muted);
  font-size: 13px;
}

.no-report {
  display: grid;
  place-items: center;
  height: 100%;
  color: var(--academic-text-muted);
  font-size: 15px;
}

@media (max-width: 980px) {
  .reports-page {
    grid-template-columns: 1fr;
    height: auto;
  }

  .method-flow {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .flow-arrow {
    display: none;
  }

  .reference-card,
  .reader-head {
    flex-direction: column;
    align-items: stretch;
  }

  .reader-actions {
    flex-wrap: wrap;
  }
}
</style>
