<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { papersApi } from '@/api/papers'
import { reportsApi } from '@/api/reports'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import { parseMarkdownHeadings, normalizeMissingReportMarkdown, stripDuplicateReferenceMarkdown, displayReportValue, displayReferenceReason, isMissingReportContent } from '@/utils/reportMarkdown'
import type { Paper, Report, ReportReferenceLink } from '@/types/domain'
import { officialLinkLabel, resolveOfficialPaperUrl } from '@/utils/paperOfficialUrl'

interface TocItem {
  id: string
  label: string
  level: 1 | 2
}

const route = useRoute()
const list = ref<Report[]>([])
const current = ref<Report | null>(null)
const papers = ref<Paper[]>([])
const selectedPaperId = ref<number | null>(null)
const reportTitle = ref('')
const creating = ref(false)
const sidebarCollapsed = ref(false)
const sidebarHovered = ref(false)
const exportOpen = ref(false)
const exportMenuRef = ref<HTMLElement | null>(null)
const reportBodyRef = ref<HTMLElement | null>(null)
const activeTocId = ref('')
let tocObserver: IntersectionObserver | null = null

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
  document.addEventListener('click', onDocumentClick)
  await Promise.all([
    loadReports(),
    papersApi.list().then(rows => {
      papers.value = rows
      selectedPaperId.value = rows[0]?.id || null
    }),
  ])
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  tocObserver?.disconnect()
})

function markdown(r: Report | null) {
  let content = r?.content?.markdown || JSON.stringify(r?.content || {}, null, 2)
  if (r?.content?.reference_links?.length) {
    content = stripDuplicateReferenceMarkdown(content)
  }
  return normalizeMissingReportMarkdown(content)
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
  (visualSummary.value?.metric_cards || []).filter(card => !isMissingReportContent(card.value)),
)
const referenceLinks = computed(() => current.value?.content?.reference_links || [])

const tocItems = computed((): TocItem[] => {
  if (!current.value) return []

  const items: TocItem[] = []
  if (visualSummary.value) {
    items.push({ id: 'section-visual-summary', label: '速览', level: 1 })
    if (methodFlow.value.length) items.push({ id: 'section-method-flow', label: '方法流程', level: 2 })
    if (keyDataTable.value.length) items.push({ id: 'section-key-data', label: '关键数据', level: 2 })
    if (metricCards.value.length) items.push({ id: 'section-metrics', label: '核心指标', level: 2 })
  }

  for (const heading of parseMarkdownHeadings(markdown(current.value))) {
    items.push(heading)
  }

  if (referenceLinks.value.length) {
    items.push({ id: 'section-references', label: '延伸阅读', level: 1 })
  }
  return items
})

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

function formatDate(ts: string | null | undefined) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
}

function reportSummary(report: Report) {
  const source = report.content?.source as Record<string, unknown> | undefined
  const abstract = String(source?.abstract || '').trim()
  if (abstract) {
    return abstract.length > 72 ? `${abstract.slice(0, 72)}…` : abstract
  }
  const md = String(report.content?.markdown || '')
  const match = md.match(/^##\s+摘要速览\s*\n+([\s\S]*?)(?=\n##\s|$)/m)
  const snippet = match?.[1]?.replace(/\n+/g, ' ').trim() || ''
  if (snippet) {
    return snippet.length > 72 ? `${snippet.slice(0, 72)}…` : snippet
  }
  return ''
}

function scrollToSection(id: string) {
  const root = reportBodyRef.value
  const el = root?.querySelector(`#${CSS.escape(id)}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    activeTocId.value = id
  }
}

function setupTocObserver() {
  tocObserver?.disconnect()
  tocObserver = null

  const root = reportBodyRef.value
  if (!root || !tocItems.value.length) return

  const ratios = new Map<string, number>()
  tocObserver = new IntersectionObserver(
    entries => {
      for (const entry of entries) {
        const id = (entry.target as HTMLElement).id
        if (!id) continue
        if (entry.isIntersecting) ratios.set(id, entry.intersectionRatio)
        else ratios.delete(id)
      }
      if (ratios.size) {
        const best = [...ratios.entries()].sort((a, b) => b[1] - a[1])[0]
        if (best) activeTocId.value = best[0]
        return
      }
      const firstVisible = tocItems.value.find(item => {
        const el = root.querySelector(`#${CSS.escape(item.id)}`)
        if (!el) return false
        const rect = el.getBoundingClientRect()
        const rootRect = root.getBoundingClientRect()
        return rect.top >= rootRect.top - 8 && rect.top <= rootRect.bottom
      })
      if (firstVisible) activeTocId.value = firstVisible.id
    },
    { root, rootMargin: '-12% 0px -55% 0px', threshold: [0, 0.15, 0.4, 0.75] },
  )

  for (const item of tocItems.value) {
    const el = root.querySelector(`#${CSS.escape(item.id)}`)
    if (el) tocObserver.observe(el)
  }

  if (!activeTocId.value) {
    activeTocId.value = tocItems.value[0]?.id || ''
  }
}

function closeExportMenu() {
  exportOpen.value = false
}

function toggleExportMenu() {
  exportOpen.value = !exportOpen.value
}

function onDocumentClick(event: MouseEvent) {
  if (!exportOpen.value) return
  const target = event.target as Node
  if (!exportMenuRef.value?.contains(target)) {
    exportOpen.value = false
  }
}

watch([current, tocItems], async () => {
  activeTocId.value = tocItems.value[0]?.id || ''
  await nextTick()
  setupTocObserver()
}, { flush: 'post' })

function openOfficialPaper() {
  if (currentOfficialUrl.value) {
    window.open(currentOfficialUrl.value, '_blank', 'noopener,noreferrer')
  }
}

function referenceTitle(item: ReportReferenceLink) {
  return item.raw?.trim() || item.title?.trim() || '未命名参考文献'
}

function referenceButtonLabel(item: ReportReferenceLink) {
  return item.url ? '打开原文' : '-'
}

function openReference(item: ReportReferenceLink) {
  if (item.url) {
    window.open(item.url, '_blank', 'noopener,noreferrer')
  }
}

function displaySummaryValue(content?: string) {
  return displayReportValue(content)
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
  closeExportMenu()
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
  <div class="reports-workspace">
    <!-- 左侧列表 -->
    <div
      class="report-sidebar-wrapper"
      :class="{ collapsed: sidebarCollapsed }"
      @mouseenter="sidebarHovered = true"
      @mouseleave="sidebarHovered = false"
    >
      <aside class="report-sidebar">
        <div class="report-sidebar-head">
          <h2 class="report-sidebar-title">研读报告</h2>
          <span class="report-count">{{ list.length }} 份</span>
        </div>

        <div class="report-divider" />

        <div class="report-create-block">
          <select v-model.number="selectedPaperId" class="report-field" :disabled="creating || papers.length === 0">
            <option :value="null" disabled>选择一篇文献</option>
            <option v-for="paper in papers" :key="paper.id" :value="paper.id">
              {{ paper.title || paper.original_filename || `文献 #${paper.id}` }}
            </option>
          </select>
          <input
            v-model="reportTitle"
            class="report-field"
            placeholder="报告标题，可不填"
            :disabled="creating"
          />
          <button class="report-create-btn" :disabled="!selectedPaperId || creating" @click="createReport">
            {{ creating ? '生成中...' : '生成研读报告' }}
          </button>
        </div>

        <div class="report-divider" />

        <div class="report-list-wrap slim-scroll">
          <div
            v-for="r in list"
            :key="r.id"
            class="report-list-item"
            :class="{ active: current?.id === r.id }"
            @click="current = r"
          >
            <div class="report-item-main">
              <div class="report-item-title">{{ r.title }}</div>
              <p v-if="reportSummary(r)" class="report-item-summary">{{ reportSummary(r) }}</p>
              <div class="report-item-meta">{{ formatDate(r.created_at) }}</div>
            </div>
            <button class="report-item-delete" title="删除报告" @click.stop="deleteReport(r)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
          <div v-if="list.length === 0" class="report-empty-side">暂无报告</div>
        </div>
      </aside>
    </div>

    <button
      class="report-sidebar-toggle"
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
    <main class="report-main" :class="{ 'is-sidebar-collapsed': sidebarCollapsed }">
      <div class="report-header">
        <div class="report-header-copy">
          <h2 class="report-header-title" :title="fullTitle">{{ displayTitle }}</h2>
          <span v-if="fullTitle !== displayTitle" class="report-header-subtitle" :title="fullTitle">{{ fullTitle }}</span>
        </div>

        <div class="report-header-spacer" />

        <div class="report-header-actions">
          <button
            v-if="currentOfficialUrl"
            type="button"
            class="report-action-btn official"
            @click="openOfficialPaper"
          >
            {{ officialLinkLabel(currentOfficialUrl) }} ↗
          </button>
          <div ref="exportMenuRef" class="export-dropdown">
            <button
              type="button"
              class="report-action-btn primary export-trigger"
              :disabled="!current"
              @click.stop="toggleExportMenu"
            >
              导出报告
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            <div v-if="exportOpen" class="export-menu">
              <button type="button" @click="downloadReport('md')">Markdown (.md)</button>
              <button type="button" @click="downloadReport('docx')">Word (.docx)</button>
              <button type="button" @click="downloadReport('pdf')">PDF (.pdf)</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="current" class="report-reading">
        <nav v-if="tocItems.length" class="report-toc slim-scroll" aria-label="报告目录">
          <span class="toc-label">目录</span>
          <button
            v-for="item in tocItems"
            :key="item.id"
            type="button"
            class="toc-item"
            :class="{ active: activeTocId === item.id, sub: item.level === 2 }"
            @click="scrollToSection(item.id)"
          >
            {{ item.label }}
          </button>
        </nav>

        <div ref="reportBodyRef" class="report-body slim-scroll">
          <section v-if="visualSummary" id="section-visual-summary" class="content-panel">
            <header class="panel-head">
              <h3>速览</h3>
            </header>

            <div v-if="methodFlow.length" id="section-method-flow" class="panel-section">
              <h4>方法流程</h4>
              <div class="flow-steps">
                <template v-for="(step, index) in methodFlow" :key="flowKey(step, index)">
                  <div class="flow-step">
                    <div class="flow-step-index">{{ index + 1 }}</div>
                    <div class="flow-step-body">
                      <strong>{{ step.title }}</strong>
                      <p>{{ displaySummaryValue(step.content) }}</p>
                    </div>
                  </div>
                  <div v-if="index < methodFlow.length - 1" class="flow-connector" aria-hidden="true">→</div>
                </template>
              </div>
            </div>

            <div v-if="keyDataTable.length" id="section-key-data" class="panel-section">
              <h4>关键数据表</h4>
              <div class="data-table-panel">
                <div class="table-wrap">
                  <table class="flat-table">
                    <thead>
                      <tr>
                        <th>字段</th>
                        <th>内容</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="row in keyDataTable" :key="row.name">
                        <td>{{ row.name }}</td>
                        <td>{{ displaySummaryValue(row.value) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div v-if="metricCards.length" id="section-metrics" class="panel-section">
              <h4>核心指标</h4>
              <div class="metric-grid">
                <div v-for="card in metricCards" :key="`${card.label}-${card.value}`" class="metric-cell">
                  <div class="metric-label">{{ card.label }}</div>
                  <div class="metric-value">{{ card.value }}</div>
                  <div v-if="card.note" class="metric-note">{{ card.note }}</div>
                </div>
              </div>
            </div>
          </section>

          <section class="content-panel markdown-panel">
            <MarkdownRenderer :content="markdown(current)" :linkify-references="false" heading-anchors />
          </section>

          <section v-if="referenceLinks.length" id="section-references" class="content-panel">
            <header class="panel-head">
              <h3>延伸阅读</h3>
              <span class="panel-head-meta">{{ referenceLinks.length }} 篇</span>
            </header>
            <div class="reference-rows">
              <article v-for="(item, index) in referenceLinks" :key="`${item.raw}-${index}`" class="reference-row">
                <div class="reference-main">
                  <p class="reference-citation">{{ referenceTitle(item) }}</p>
                  <p v-if="displayReferenceReason(item.reason)" class="reference-reason">{{ displayReferenceReason(item.reason) }}</p>
                </div>
                <button
                  v-if="item.url"
                  type="button"
                  class="reference-link-btn"
                  @click="openReference(item)"
                >
                  {{ referenceButtonLabel(item) }} ↗
                </button>
              </article>
            </div>
          </section>
        </div>
      </div>

      <div v-else class="report-empty-main">
        <h3>选择一个报告查看详情</h3>
        <p>从左侧列表选择已有报告，或选择文献后生成新报告</p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.reports-workspace {
  position: relative;
  display: flex;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: #F8FAFC;
}

/* ====== 左侧栏 ====== */
.report-sidebar-wrapper {
  position: relative;
  flex-shrink: 0;
  width: 260px;
  overflow: hidden;
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.report-sidebar-wrapper.collapsed {
  width: 0;
}

.report-sidebar {
  width: 260px;
  height: 100%;
  background: #fff;
  box-shadow: 1px 0 0 0 #E2E8F0;
  display: flex;
  flex-direction: column;
  padding: 20px 12px;
  overflow: hidden;
  gap: 12px;
}

.report-sidebar-toggle {
  position: absolute;
  left: 240px;
  top: 18px;
  z-index: 50;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #E2E8F0;
  border-radius: 50%;
  background: #fff;
  color: #64748B;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 0.2s ease, transform 0.2s ease, color 0.15s, left 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}

.report-sidebar-toggle.visible {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.report-sidebar-toggle.collapsed {
  left: 12px;
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.report-sidebar-toggle:hover {
  color: #0F172A;
  border-color: #CBD5E1;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

.report-sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
}

.report-sidebar-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #0F172A;
}

.report-count {
  font-size: 11px;
  color: #94A3B8;
  font-weight: 500;
  background: #F1F5F9;
  padding: 1px 7px;
  border-radius: 10px;
}

.report-divider {
  height: 1px;
  background: #F1F5F9;
}

.report-create-block {
  display: grid;
  gap: 8px;
  padding: 0 8px;
}

.report-field {
  width: 100%;
  min-width: 0;
  height: 34px;
  padding: 0 10px;
  border: none;
  border-radius: 8px;
  background: #F8FAFC;
  color: #334155;
  font-size: 13px;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
}

.report-field:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.report-create-btn {
  height: 34px;
  border: none;
  border-radius: 8px;
  background: #3B82F6;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.report-create-btn:hover:not(:disabled) {
  background: #2563EB;
}

.report-create-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.report-list-wrap {
  flex: 1;
  overflow-y: auto;
  margin: 0 -12px;
  padding-bottom: 12px;
}

.report-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.12s;
  box-shadow: 0 1px 0 0 #F1F5F9;
}

.report-list-item:hover {
  background: #F1F5F9;
}

.report-list-item.active {
  background: #EFF6FF;
}

.report-list-item.active:hover {
  background: #DBEAFE;
}

.report-item-main {
  flex: 1;
  min-width: 0;
}

.report-item-title {
  font-size: 13px;
  font-weight: 600;
  color: #0F172A;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.35;
}

.report-list-item.active .report-item-title {
  color: #1D4ED8;
}

.report-item-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #94A3B8;
}

.report-item-summary {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: #64748B;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.report-item-delete {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #94A3B8;
  cursor: pointer;
  opacity: 0;
  transition: all 0.12s;
}

.report-list-item:hover .report-item-delete {
  opacity: 1;
}

.report-item-delete:hover {
  background: #FEE2E2;
  color: #EF4444;
}

.report-empty-side {
  padding: 32px 16px;
  text-align: center;
  color: #94A3B8;
  font-size: 13px;
}

/* ====== 右侧主区 ====== */
.report-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.report-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.report-main.is-sidebar-collapsed .report-header {
  padding-left: 48px;
}

.report-header-copy {
  min-width: 0;
}

.report-header-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #0F172A;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.35;
}

.report-header-subtitle {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: #94A3B8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-header-spacer {
  flex: 1;
  min-width: 8px;
}

.report-header-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.report-action-btn {
  padding: 7px 14px;
  border: none;
  border-radius: 8px;
  background: #fff;
  color: #475569;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: all 0.12s;
}

.report-action-btn:hover:not(:disabled) {
  background: #F8FAFC;
  color: #334155;
}

.report-action-btn.primary {
  background: #3B82F6;
  color: #fff;
  box-shadow: none;
}

.report-action-btn.primary:hover:not(:disabled) {
  background: #2563EB;
}

.report-action-btn.official {
  color: #7C3AED;
  background: #F5F3FF;
  box-shadow: 0 0 0 1px rgba(124, 58, 237, 0.2);
}

.report-action-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.export-dropdown {
  position: relative;
}

.export-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.export-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 168px;
  padding: 6px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12), 0 0 0 1px #E2E8F0;
  z-index: 30;
}

.export-menu button {
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #334155;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s;
}

.export-menu button:hover {
  background: #F1F5F9;
  color: #1D4ED8;
}

.report-reading {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.report-toc {
  width: 196px;
  flex-shrink: 0;
  min-height: 0;
  padding: 8px 10px 24px 24px;
  overflow-y: auto;
  border-right: 1px solid #E2E8F0;
  background: #fff;
}

.toc-label {
  display: block;
  padding: 0 10px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #94A3B8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.toc-item {
  display: block;
  width: 100%;
  padding: 7px 10px;
  margin-bottom: 2px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #64748B;
  font-size: 13px;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
  transition: all 0.12s;
}

.toc-item.sub {
  padding-left: 22px;
  font-size: 12px;
}

.toc-item:hover {
  background: #F8FAFC;
  color: #334155;
}

.toc-item.active {
  background: #EFF6FF;
  color: #1D4ED8;
  font-weight: 600;
}

.report-body {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 24px 28px;
  overscroll-behavior: contain;
}

.content-panel {
  background: #fff;
  border-radius: 10px;
  padding: 20px 24px;
  margin-bottom: 2px;
  box-shadow: 0 1px 0 0 #F1F5F9;
  scroll-margin-top: 16px;
}

.content-panel:last-child {
  box-shadow: none;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.panel-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #0F172A;
}

.panel-head-meta {
  font-size: 12px;
  color: #94A3B8;
}

.panel-section {
  padding-top: 4px;
  padding-bottom: 16px;
  border-bottom: 1px solid #F1F5F9;
  scroll-margin-top: 16px;
}

.panel-section:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.panel-section h4,
.panel-subtitle,
.reference-row h4 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.panel-subtitle {
  margin-top: -4px;
}

.panel-hint,
.flow-step-body p,
.metric-note,
.metric-source,
.reference-reason,
.reference-raw p {
  margin: 0;
  color: #64748B;
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.panel-hint {
  margin-top: 8px;
  font-size: 12px;
}

.flow-steps {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr);
  gap: 8px;
  align-items: stretch;
}

.flow-step {
  min-width: 0;
  display: flex;
  gap: 10px;
  padding: 12px 0;
  border-left: 3px solid #3B82F6;
  padding-left: 12px;
}

.flow-step-index {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #EFF6FF;
  color: #1D4ED8;
  font-size: 11px;
  font-weight: 700;
}

.flow-step-body {
  min-width: 0;
}

.flow-step-body strong {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  color: #0F172A;
}

.flow-step-body p {
  display: -webkit-box;
  max-height: 96px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}

.flow-connector {
  align-self: center;
  justify-self: center;
  color: #CBD5E1;
  font-weight: 700;
  font-size: 16px;
}

.data-table-panel {
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 10px;
  overflow: hidden;
}

.table-wrap {
  overflow-x: auto;
}

.flat-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.flat-table th,
.flat-table td {
  padding: 11px 14px;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
  color: #334155;
  border-bottom: 1px solid #E2E8F0;
  overflow-wrap: anywhere;
}

.flat-table th {
  background: #EFF6FF;
  color: #1E40AF;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.02em;
}

.flat-table th:first-child,
.flat-table td:first-child {
  width: 150px;
}

.flat-table th:last-child,
.flat-table td:last-child {
  width: 100px;
  color: #94A3B8;
}

.flat-table tbody tr:last-child td {
  border-bottom: none;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0;
  border: 1px solid #DBEAFE;
  border-radius: 10px;
  overflow: hidden;
  background: #F8FAFC;
}

.metric-cell {
  padding: 16px 18px;
  border-right: 1px solid #DBEAFE;
  border-bottom: 1px solid #DBEAFE;
  background: linear-gradient(180deg, #fff 0%, #F8FAFC 100%);
}

.metric-label {
  color: #94A3B8;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.metric-value {
  margin: 6px 0 4px;
  color: #1D4ED8;
  font-size: 20px;
  font-weight: 800;
  overflow-wrap: anywhere;
  line-height: 1.2;
}

.metric-source {
  margin-top: 6px;
}

.markdown-panel {
  padding: 28px 32px 32px;
}

.markdown-panel :deep(.markdown-body h2) {
  margin-top: 36px;
  padding-top: 22px;
  border-top: 1px solid #E2E8F0;
  scroll-margin-top: 20px;
  font-size: 18px;
}

.markdown-panel :deep(.markdown-body h2:first-child) {
  margin-top: 0;
  padding-top: 0;
  border-top: none;
}

.markdown-panel :deep(.markdown-body h3) {
  margin-top: 24px;
  scroll-margin-top: 20px;
  font-size: 15px;
  color: #334155;
}

.markdown-panel :deep(.markdown-body p) {
  margin: 10px 0;
  max-width: none;
}

.markdown-panel :deep(.markdown-body) {
  width: 100%;
}

.markdown-panel :deep(.markdown-body table) {
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 10px;
  margin: 16px 0;
}

.markdown-panel :deep(.markdown-body th) {
  background: #EFF6FF;
  color: #1E40AF;
}

.markdown-panel :deep(.markdown-body ul) {
  margin: 12px 0;
  padding-left: 1.25rem;
}

.markdown-panel :deep(.markdown-body li) {
  margin: 8px 0;
  line-height: 1.7;
}

.markdown-panel :deep(.markdown-body li > ul) {
  margin-top: 6px;
  margin-bottom: 0;
}

.markdown-panel :deep(.markdown-body li > p) {
  margin: 4px 0;
}

.markdown-panel :deep(.markdown-body a[href*="scholar.google"]) {
  word-break: break-word;
  font-size: 14px;
}

.reference-rows {
  display: flex;
  flex-direction: column;
}

.reference-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid #F1F5F9;
}

.reference-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.reference-main {
  min-width: 0;
}

.reference-row h4,
.reference-citation {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.6;
  color: #0F172A;
  white-space: pre-wrap;
  word-break: break-word;
}

.reference-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 6px 0;
  color: #94A3B8;
  font-size: 12px;
}

.reference-reason {
  margin-top: 6px;
}

.reference-raw {
  margin-top: 8px;
  color: #64748B;
  font-size: 12px;
}

.reference-raw summary {
  cursor: pointer;
}

.reference-raw p {
  white-space: pre-wrap;
  word-break: break-word;
}

.reference-link-btn {
  flex: 0 0 auto;
  border: none;
  border-radius: 8px;
  background: #EFF6FF;
  color: #1D4ED8;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.12s;
}

.reference-link-btn:hover {
  background: #DBEAFE;
}

.reference-empty {
  flex: 0 0 auto;
  color: #94A3B8;
  font-size: 12px;
}

.report-empty-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  color: #94A3B8;
}

.report-empty-main h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: #64748B;
}

.report-empty-main p {
  margin: 0;
  font-size: 13px;
}

@media (max-width: 980px) {
  .report-reading {
    flex-direction: column;
  }

  .report-toc {
    width: 100%;
    max-height: 120px;
    border-right: none;
    border-bottom: 1px solid #E2E8F0;
    display: flex;
    flex-wrap: nowrap;
    gap: 6px;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 10px 16px;
  }

  .toc-label {
    display: none;
  }

  .toc-item {
    flex: 0 0 auto;
    width: auto;
    white-space: nowrap;
    margin-bottom: 0;
  }

  .toc-item.sub {
    padding-left: 10px;
  }

  .flow-steps {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .flow-connector {
    display: none;
  }

  .reference-row,
  .report-header {
    flex-direction: column;
    align-items: stretch;
  }

  .report-header-actions {
    justify-content: flex-start;
  }
}
</style>
