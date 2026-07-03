<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { papersApi } from '@/api/papers'
import { reportsApi } from '@/api/reports'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import type { Paper, Report } from '@/types/domain'

const list = ref<Report[]>([])
const current = ref<Report | null>(null)
const papers = ref<Paper[]>([])
const selectedPaperId = ref<number | null>(null)
const reportTitle = ref('')
const creating = ref(false)

async function loadReports() {
  list.value = await reportsApi.list()
  current.value = list.value[0] || null
}

onMounted(async () => {
  await Promise.all([
    loadReports(),
    papersApi.list().then(rows => {
      papers.value = rows
      selectedPaperId.value = rows[0]?.id || null
    }),
  ])
})

function markdown(r: Report | null) {
  return r?.content?.markdown || JSON.stringify(r?.content || {}, null, 2)
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
  if (!current.value) return
  const res = await reportsApi.export(current.value.id, format)
  const contentType = String(res.headers['content-type'] || 'application/octet-stream')
  const blob = new Blob([res.data], { type: contentType })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${current.value.title || 'report'}.${format}`
  link.click()
  URL.revokeObjectURL(link.href)
}
</script>

<template>
  <div class="reports-page">
    <!-- 左侧列表 -->
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

    <!-- 右侧内容 -->
    <section class="reader-panel">
      <div class="reader-head">
        <h2>{{ current?.title || '暂无报告' }}</h2>
        <div class="reader-actions">
          <button :disabled="!current" @click="downloadReport('md')">导出 MD</button>
          <button :disabled="!current" @click="downloadReport('docx')">导出 Word</button>
          <button :disabled="!current" class="primary" @click="downloadReport('pdf')">导出 PDF</button>
        </div>
      </div>
      <div class="reader-body slim-scroll">
        <MarkdownRenderer v-if="current" :content="markdown(current)" />
        <div v-else class="no-report">
          <p>选择一个报告查看详情</p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.reports-page {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 16px;
  height: 100%;
  padding: 20px;
}

/* ====== 左侧栏 ====== */
.sidebar-panel {
  border-radius: 20px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-soft);
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  padding: 18px 24px;
  border-bottom: 1px solid var(--academic-border);
  background: var(--academic-canvas);
}

.reader-head h2 {
  margin: 0;
  font-size: 20px;
  color: var(--academic-text-main);
}

.reader-actions {
  display: flex;
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

.reader-actions button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.reader-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.no-report {
  display: grid;
  place-items: center;
  height: 100%;
  color: var(--academic-text-muted);
  font-size: 15px;
}
</style>
