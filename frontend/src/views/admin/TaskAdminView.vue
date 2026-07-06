<!-- frontend/src/views/admin/TaskAdminView.vue -->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '@/api/admin'
import {
  formatDateTime,
  formatTaskStatus,
  formatTaskType,
  tableRowIndex,
} from '@/utils/adminDisplay'

const rows = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const status = ref('')
const loading = ref(true)
const selectedIds = ref<number[]>([])

const stats = ref({
  total: 0,
  running: 0,
  failed: 0,
  queued: 0,
  completed: 0,
  cancelled: 0,
})

const errorCard = ref<{ visible: boolean; text: string; x: number; y: number }>({
  visible: false,
  text: '',
  x: 0,
  y: 0,
})

const failedSelected = computed(() =>
  rows.value.filter(r => selectedIds.value.includes(r.id) && r.status === 'failed').map(r => r.id),
)
const cancellableSelected = computed(() =>
  rows.value.filter(r => selectedIds.value.includes(r.id) && !['completed', 'failed', 'cancelled'].includes(r.status)).map(r => r.id),
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
    if (res.stats) {
      stats.value = { ...stats.value, ...res.stats }
    }
    selectedIds.value = []
    errorCard.value.visible = false
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => document.removeEventListener('click', onDocumentClick))

function onSelectionChange(val: any[]) {
  selectedIds.value = val.map(v => v.id)
}

function openErrorLog(e: MouseEvent, row: any) {
  if (!row.error_log) return
  const cardW = 480
  const cardH = 400
  errorCard.value = {
    visible: true,
    text: row.error_log,
    x: Math.max(12, Math.min(e.clientX, window.innerWidth - cardW - 12)),
    y: Math.max(12, Math.min(e.clientY + 10, window.innerHeight - cardH - 12)),
  }
}

function closeErrorLog() {
  errorCard.value.visible = false
}

function onDocumentClick() {
  if (errorCard.value.visible) closeErrorLog()
}

function statusLabel(s: string) {
  return formatTaskStatus(s)
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
      <div class="admin-metric admin-metric--blue">
        <span class="admin-metric-label">任务总数</span>
        <span class="admin-metric-value is-accent">{{ total }}</span>
        <span class="admin-metric-sub">当前筛选结果</span>
      </div>
      <div class="admin-metric-divider" />
      <div class="admin-metric admin-metric--cyan">
        <span class="admin-metric-label">执行中</span>
        <span class="admin-metric-value is-accent">{{ stats.running }}</span>
        <span class="admin-metric-sub">全部执行中</span>
      </div>
      <div class="admin-metric-divider" />
      <div class="admin-metric admin-metric--rose">
        <span class="admin-metric-label">失败</span>
        <span class="admin-metric-value is-accent">{{ stats.failed }}</span>
        <span class="admin-metric-sub">全部失败</span>
      </div>
      <div class="admin-metric-divider" />
      <div class="admin-metric admin-metric--violet">
        <span class="admin-metric-label">已选</span>
        <span class="admin-metric-value is-accent">{{ selectedIds.length }}</span>
        <span class="admin-metric-sub">批量操作</span>
      </div>
    </section>

    <div class="admin-toolbar">
      <div class="admin-toolbar-left">
        <el-select
          v-model="status"
          clearable
          placeholder="状态筛选"
          style="width: 140px"
          @change="() => { page = 1; load() }"
        >
          <el-option label="排队中" value="queued" />
          <el-option label="执行中" value="running" />
          <el-option label="失败" value="failed" />
          <el-option label="已完成" value="completed" />
          <el-option label="已终止" value="cancelled" />
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
        <el-table-column label="序号" width="64" align="center">
          <template #default="{ $index }">{{ tableRowIndex(page, pageSize, $index) }}</template>
        </el-table-column>
        <el-table-column label="任务" min-width="220">
          <template #default="{ row }">
            <div class="cell-main">{{ row.paper_label || formatTaskType(row.task_type) }}</div>
            <div class="cell-sub">{{ row.username || '未知用户' }} · {{ formatDateTime(row.created_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="admin-status" :class="statusClass(row.status)">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" align="center" />
        <el-table-column prop="retry_count" label="重试" width="64" align="center" />
        <el-table-column label="时间" width="160">
          <template #default="{ row }">
            <span class="cell-sub">{{ formatDateTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'failed' && row.error_log"
              link
              type="primary"
              size="small"
              @click.stop="openErrorLog($event, row)"
            >
              错误日志
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
    </div>

    <Teleport to="body">
      <Transition name="admin-pop-fade">
        <div
          v-if="errorCard.visible"
          class="admin-error-popover"
          :style="{ left: `${errorCard.x}px`, top: `${errorCard.y}px` }"
          @click.stop
        >
          <div class="admin-error-popover__accent" aria-hidden="true" />
          <div class="admin-error-popover__inner">
            <div class="admin-error-popover__head">
              <span class="admin-error-popover__title">错误日志</span>
              <button type="button" class="admin-error-popover__close" aria-label="关闭" @click="closeErrorLog">×</button>
            </div>
            <pre class="admin-error-popover__log">{{ errorCard.text }}</pre>
          </div>
        </div>
      </Transition>
    </Teleport>

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
</style>
