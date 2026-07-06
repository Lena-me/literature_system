<!-- frontend/src/views/admin/AuditCenter.vue — 风控与审计中心 · Borderless Canvas -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { adminApi } from '@/api/admin'
import {
  formatAuditAction,
  formatAuditSummary,
  formatAuditModule,
  formatDateTime,
  tableRowIndex,
} from '@/utils/adminDisplay'

const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const auditLogs = ref<any[]>([])

const keyword = ref('')
const dateRange = ref<[Date, Date] | null>(null)

const totalLabel = computed(() => `共 ${total.value} 条`)

function rowIndex(index: number) {
  return tableRowIndex(page.value, pageSize.value, index)
}

function defaultDateRange(): [Date, Date] {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 6)
  start.setHours(0, 0, 0, 0)
  end.setHours(23, 59, 59, 999)
  return [start, end]
}

function toIsoDate(d: Date, endOfDay = false): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return endOfDay ? `${y}-${m}-${day}T23:59:59` : `${y}-${m}-${day}T00:00:00`
}

function buildQueryParams() {
  const params: Record<string, string | number | undefined> = {
    page: page.value,
    size: pageSize.value,
    keyword: keyword.value.trim() || undefined,
  }
  if (dateRange.value?.[0]) params.start_at = toIsoDate(dateRange.value[0])
  if (dateRange.value?.[1]) params.end_at = toIsoDate(dateRange.value[1], true)
  return params
}

async function loadAudit() {
  loading.value = true
  try {
    const res = await adminApi.auditLogs(buildQueryParams())
    auditLogs.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadAudit()
}

function onPageChange(next: number) {
  page.value = next
  loadAudit()
}

function auditRowClass({ row }: { row: any }) {
  return row.risk_flag >= 1 ? 'audit-row--risk' : ''
}

function riskBadge(row: any) {
  if (row.risk_flag >= 2) return { label: '高危', cls: 'is-alert' }
  if (row.risk_flag >= 1) return { label: '预警', cls: 'is-warn' }
  return { label: '正常', cls: 'is-ok' }
}

function resultLabel(result: string) {
  return result === 'success' ? '成功' : '失败'
}

onMounted(() => {
  dateRange.value = defaultDateRange()
  loadAudit()
})
</script>

<template>
  <div class="audit-center">
    <header class="audit-center__header">
      <div class="audit-center__header-main">
        <h1 class="audit-center__title">风控与审计中心</h1>
        <p class="audit-center__subtitle">用户操作留痕与高危行为追踪</p>
      </div>

      <div class="audit-center__filters">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          size="default"
          class="audit-center__date"
          :clearable="false"
          @change="handleSearch"
        />
        <el-input
          v-model="keyword"
          class="audit-center__search"
          placeholder="搜索用户、操作类型、模块…"
          clearable
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <button type="button" class="audit-center__query-btn" @click="handleSearch">检索</button>
      </div>
    </header>

    <div class="audit-center__toolbar">
      <span class="audit-center__section-label">用户行为审计</span>
      <span class="audit-center__tab-meta">{{ totalLabel }}</span>
    </div>

    <main class="audit-center__body" v-loading="loading">
      <div class="admin-el-table flush-x audit-center__table">
        <el-table
          :data="auditLogs"
          size="default"
          height="calc(100vh - 260px)"
          :row-class-name="auditRowClass"
        >
          <el-table-column label="序号" width="64" align="center">
            <template #default="{ $index }">{{ rowIndex($index) }}</template>
          </el-table-column>
          <el-table-column label="用户" min-width="120">
            <template #default="{ row }">
              <span class="audit-cell-strong">{{ row.username || '未知用户' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="模块" width="88">
            <template #default="{ row }">{{ formatAuditModule(row.module) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">{{ formatAuditAction(row.operation_type) }}</template>
          </el-table-column>
          <el-table-column label="详情" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.operation_summary || formatAuditSummary(row.module, row.operation_type) }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="108">
            <template #default="{ row }">
              <span
                class="audit-badge"
                :class="row.risk_flag >= 1 ? riskBadge(row).cls : row.operation_result === 'success' ? 'is-ok' : 'is-fail'"
              >
                {{ row.risk_flag >= 1 ? riskBadge(row).label : resultLabel(row.operation_result) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP" width="130" />
          <el-table-column label="时间" width="168">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </main>

    <footer class="admin-pager audit-center__pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, jumper"
        background
        @current-change="onPageChange"
      />
    </footer>
  </div>
</template>

<style scoped>
.audit-center {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--admin-bg-subtle, #f8fafc);
}

.audit-center__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 2rem;
  padding: 2rem 2rem 1.25rem;
  background: var(--admin-bg-subtle, #f8fafc);
}

.audit-center__title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--academic-text-main, #0f172a);
  line-height: 1.25;
}

.audit-center__subtitle {
  margin: 0.375rem 0 0;
  font-size: 0.8125rem;
  color: var(--academic-text-muted, #64748b);
}

.audit-center__filters {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  flex: 1;
  justify-content: flex-end;
  min-width: 0;
}

.audit-center__date {
  width: 260px;
  flex-shrink: 0;
}

.audit-center__search {
  flex: 1;
  min-width: 220px;
  max-width: 420px;
}

.audit-center__query-btn {
  flex-shrink: 0;
  border: none;
  background: transparent;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--admin-accent, #2563eb);
  cursor: pointer;
  padding: 0.5rem 0.75rem;
}

.audit-center__query-btn:hover {
  color: var(--admin-accent-hover, #1d4ed8);
}

.audit-center__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2rem 0.75rem;
  border-bottom: 1px solid var(--admin-border-soft, #f1f5f9);
}

.audit-center__section-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--academic-text-main, #0f172a);
}

.audit-center__tab-meta {
  font-size: 0.75rem;
  color: var(--academic-text-muted, #64748b);
}

.audit-center__body {
  flex: 1;
  min-height: 0;
  background: var(--admin-bg-subtle, #f8fafc);
}

.audit-center__table {
  padding: 0;
}

.audit-center__table.admin-el-table :deep(.el-table) {
  background: transparent;
}

.audit-center__table.admin-el-table :deep(.audit-row--risk) {
  background: rgba(254, 226, 226, 0.28) !important;
}

.audit-center__table.admin-el-table :deep(.audit-row--risk:hover > td.el-table__cell) {
  background: rgba(254, 202, 202, 0.35) !important;
}

.audit-cell-strong {
  font-weight: 500;
  color: var(--academic-text-main, #0f172a);
}

.audit-cell-muted {
  margin-left: 0.375rem;
  font-size: 0.75rem;
  color: var(--academic-text-muted, #64748b);
}

.audit-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-radius: 4px;
}

.audit-badge.is-ok {
  color: #047857;
  background: #d1fae5;
}

.audit-badge.is-fail {
  color: #b91c1c;
  background: #fee2e2;
}

.audit-badge.is-warn {
  color: #b45309;
  background: #fef3c7;
  box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.35);
}

.audit-badge.is-alert {
  color: #fff;
  background: #dc2626;
  box-shadow: 0 0 0 1px rgba(220, 38, 38, 0.4);
}

.audit-center__pager {
  background: var(--admin-bg-subtle, #f8fafc);
  border-top: 1px solid var(--admin-border-soft, #f1f5f9);
}

@media (max-width: 960px) {
  .audit-center__header {
    flex-direction: column;
    align-items: stretch;
  }

  .audit-center__filters {
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .audit-center__search {
    max-width: none;
    flex: 1 1 100%;
  }
}
</style>
