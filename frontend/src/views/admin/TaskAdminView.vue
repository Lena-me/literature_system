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
  rows.value.filter(r => selectedIds.value.includes(r.id) && r.status === 'failed').map(r => r.id)
)
const cancellableSelected = computed(() =>
  rows.value.filter(r => selectedIds.value.includes(r.id) && !['completed', 'failed', 'cancelled'].includes(r.status)).map(r => r.id)
)

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

async function batchRetry() {
  const ids = failedSelected.value.length ? failedSelected.value : selectedIds.value.filter(id => {
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
  const ids = cancellableSelected.value.length ? cancellableSelected.value : selectedIds.value.filter(id => {
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
  <div class="task-page" v-loading="loading">
    <div class="toolbar soft-card">
      <div class="toolbar-left">
        <el-select v-model="status" clearable placeholder="状态筛选" style="width: 130px" @change="() => { page = 1; load() }">
          <el-option label="Queued" value="queued" />
          <el-option label="Running" value="running" />
          <el-option label="Failed" value="failed" />
          <el-option label="Completed" value="completed" />
          <el-option label="Cancelled" value="cancelled" />
        </el-select>
        <span class="count">共 {{ total }} 条</span>
      </div>
      <div class="toolbar-right">
        <el-button type="primary" plain size="small" @click="batchRetry">批量重试失败任务</el-button>
        <el-button type="danger" plain size="small" @click="batchCancel">批量终止</el-button>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="table-card soft-card">
      <el-table :data="rows" size="small" row-key="id" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="42" />
        <el-table-column label="任务" min-width="140">
          <template #default="{ row }">
            <div class="cell-main">文献 #{{ row.paper_id }}</div>
            <div class="cell-sub">用户 #{{ row.user_id }} · {{ row.task_type }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="64" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="status-badge" :class="row.status">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="72" />
        <el-table-column prop="retry_count" label="重试" width="56" />
        <el-table-column label="时间" width="150">
          <template #default="{ row }">
            <div class="cell-sub">{{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'failed'" link type="primary" size="small" @click="toggleError(row)">
              {{ expandedId === row.id ? '收起日志' : '查看错误日志' }}
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

      <div class="pager">
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
  </div>
</template>

<style scoped>
.task-page {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.count {
  font-size: 12px;
  color: var(--academic-text-muted);
}

.table-card {
  padding: 0;
  overflow: hidden;
}

.cell-main {
  font-size: 13px;
  font-weight: 600;
  color: var(--academic-text-main);
}

.cell-sub {
  font-size: 11px;
  color: var(--academic-text-muted);
  margin-top: 2px;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.status-badge.completed { background: #dcfce7; color: #15803d; }
.status-badge.failed { background: #fee2e2; color: #dc2626; }
.status-badge.running {
  background: #dbeafe;
  color: #1d4ed8;
  animation: pulse-running 1.5s ease-in-out infinite;
}
.status-badge.queued { background: #f3f4f6; color: #6b7280; }
.status-badge.cancelled { background: #fef3c7; color: #b45309; }

@keyframes pulse-running {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.65; }
}

.error-expand {
  margin: 0 12px 12px;
  padding: 10px 12px;
  background: #1e1e1e;
  border-radius: 8px;
  overflow: auto;
  max-height: 200px;
}

.error-expand pre {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: #fca5a5;
  white-space: pre-wrap;
  word-break: break-word;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding: 10px 12px;
  border-top: 1px solid var(--academic-border);
}

:deep(.el-table) {
  --el-table-header-bg-color: #f8f9fb;
}
</style>
