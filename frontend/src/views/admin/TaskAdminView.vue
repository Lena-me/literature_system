<!-- frontend/src/views/admin/TaskAdminView.vue -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '@/api/admin'

const rows = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const status = ref('')
const loading = ref(true)
const selectedIds = ref<number[]>([])
const expandedId = ref<number | null>(null)

const failedSelected = computed(() =>
  rows.value.filter(r => selectedIds.value.includes(r.id) && r.status === 'failed').map(r => r.id),
)
const cancellableSelected = computed(() =>
  rows.value.filter(r => selectedIds.value.includes(r.id) && !['completed', 'failed', 'cancelled'].includes(r.status)).map(r => r.id),
)

const statusCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const row of rows.value) {
    counts[row.status] = (counts[row.status] || 0) + 1
  }
  return counts
})

async function load() {
  loading.value = true
  try {
    const res = await adminApi.tasks({
      page: page.value,
      page_size: pageSize.value,
      status: status.value || undefined,
    })
    rows.value = res.items || []
    total.value = res.total || 0
    selectedIds.value = []
    expandedId.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)

function onSelectionChange(val: any[]) {
  selectedIds.value = val.map(v => v.id)
}

function toggleError(row: any) {
  expandedId.value = expandedId.value === row.id ? null : row.id
}

function statusLabel(s: string) {
  const map: Record<string, string> = {
    completed: 'Completed',
    failed: 'Failed',
    running: 'Running',
    queued: 'Queued',
    cancelled: 'Cancelled',
  }
  return map[s] || s
}

function statusClass(s: string) {
  const map: Record<string, string> = {
    completed: 'is-success',
    failed: 'is-danger',
    running: 'is-info',
    queued: 'is-muted',
    cancelled: 'is-warning',
  }
  return map[s] || 'is-muted'
}

async function batchRetry() {
  const ids = failedSelected.value.length
    ? failedSelected.value
    : selectedIds.value.filter(id => {
        const row = rows.value.find(r => r.id === id)
        return row && ['failed', 'cancelled'].includes(row.status)
      })
  if (!ids.length) {
    ElMessage.warning('请选择失败或已终止的任务')
    return
  }
  const res = await adminApi.batchRetryTasks(ids)
  ElMessage.success(`已重试 ${res.retried_task_ids?.length || 0} 个任务`)
  await load()
}

async function batchCancel() {
  const ids = cancellableSelected.value.length
    ? cancellableSelected.value
    : selectedIds.value.filter(id => {
        const row = rows.value.find(r => r.id === id)
        return row && !['completed', 'failed', 'cancelled'].includes(row.status)
      })
  if (!ids.length) {
    ElMessage.warning('请选择可终止的任务')
    return
  }
  try {
    await ElMessageBox.confirm(`确认终止选中的 ${ids.length} 个任务？`, '批量终止', { type: 'warning' })
  } catch {
    return
  }
  const res = await adminApi.batchCancelTasks(ids)
  ElMessage.success(`已终止 ${res.cancelled_task_ids?.length || 0} 个任务`)
  await load()
}

function onPageChange(p: number) {
  page.value = p
  load()
}
</script>

<template>
  <div class="admin-page" v-loading="loading">
    <section class="admin-metrics-bar">
      <div class="admin-metric">
        <span class="admin-metric-label">任务总数</span>
        <span class="admin-metric-value">{{ total }}</span>
        <span class="admin-metric-sub">当前筛选结果</span>
      </div>
      <div class="admin-metric-divider" />
      <div class="admin-metric">
        <span class="admin-metric-label">Running</span>
        <span class="admin-metric-value">{{ statusCounts.running || 0 }}</span>
        <span class="admin-metric-sub">本页执行中</span>
      </div>
      <div class="admin-metric-divider" />
      <div class="admin-metric">
        <span class="admin-metric-label">Failed</span>
        <span class="admin-metric-value">{{ statusCounts.failed || 0 }}</span>
        <span class="admin-metric-sub">本页失败</span>
      </div>
      <div class="admin-metric-divider" />
      <div class="admin-metric">
        <span class="admin-metric-label">已选</span>
        <span class="admin-metric-value">{{ selectedIds.length }}</span>
        <span class="admin-metric-sub">批量操作</span>
      </div>
    </section>

    <div class="admin-toolbar">
      <div class="admin-toolbar-left">
        <el-select v-model="status" clearable placeholder="状态筛选" style="width: 140px" @change="() => { page = 1; load() }">
          <el-option label="Queued" value="queued" />
          <el-option label="Running" value="running" />
          <el-option label="Failed" value="failed" />
          <el-option label="Completed" value="completed" />
          <el-option label="Cancelled" value="cancelled" />
        </el-select>
      </div>
      <div class="admin-toolbar-right">
        <el-button text type="primary" @click="batchRetry">批量重试</el-button>
        <el-button text type="danger" @click="batchCancel">批量终止</el-button>
        <el-button text @click="load">刷新</el-button>
      </div>
    </div>

    <div class="admin-el-table">
      <el-table :data="rows" size="default" row-key="id" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="44" />
        <el-table-column label="任务" min-width="160">
          <template #default="{ row }">
            <div class="cell-main">文献 #{{ row.paper_id }}</div>
            <div class="cell-sub">用户 #{{ row.user_id }} · {{ row.task_type }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="admin-status" :class="statusClass(row.status)">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column prop="retry_count" label="重试" width="64" />
        <el-table-column label="时间" width="160">
          <template #default="{ row }">
            <span class="cell-sub">{{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'failed'" link type="primary" size="small" @click="toggleError(row)">
              {{ expandedId === row.id ? '收起日志' : '错误日志' }}
            </el-button>
            <el-button
              v-if="!['completed', 'failed', 'cancelled'].includes(row.status)"
              link
              type="danger"
              size="small"
              @click="adminApi.cancelTask(row.id).then(load)"
            >
              终止
            </el-button>
            <el-button
              v-if="['failed', 'cancelled'].includes(row.status)"
              link
              type="primary"
              size="small"
              @click="adminApi.retryTask(row.id).then(load)"
            >
              重试
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-for="row in rows" :key="'err-' + row.id">
        <div v-if="expandedId === row.id && row.error_log" class="error-expand">
          <pre>{{ row.error_log }}</pre>
        </div>
      </div>
    </div>

    <div class="admin-pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        small
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<style scoped>
.cell-main {
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
}

.cell-sub {
  font-size: 0.75rem;
  color: #64748b;
  margin-top: 0.125rem;
}

.error-expand {
  margin: 0 2rem 1rem;
  padding: 0.75rem 1rem;
  background: #0f172a;
  overflow: auto;
  max-height: 200px;
}

.error-expand pre {
  margin: 0;
  font-size: 0.6875rem;
  line-height: 1.5;
  color: #fca5a5;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
