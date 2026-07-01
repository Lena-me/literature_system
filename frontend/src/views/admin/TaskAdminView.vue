<!-- frontend\src\views\admin\TaskAdminView.vue -->

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api/admin'

const rows = ref<any[]>([])
const cfg = ref<any>({})
const status = ref('')
const failure = ref<any>({})
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const [r, c, f] = await Promise.all([
      adminApi.tasks(status.value),
      adminApi.schedulerConfig(),
      adminApi.failureStats().catch(() => ({ failed_total: 0, by_reason: [] }))
    ])
    rows.value = r
    cfg.value = c
    failure.value = f
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function saveConfig() {
  await adminApi.saveSchedulerConfig(cfg.value)
  ElMessage.success('配置已保存')
}

function getStatusLabel(status: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    failed: '失败',
    running: '运行中',
    queued: '排队中'
  }
  return map[status] || status
}
</script>

<template>
  <div class="task-admin-page" v-loading="loading" element-loading-text="加载中...">
    <div class="page-header">
      <div>
        <h1 class="page-title">解析任务管理</h1>
        <p class="page-subtitle">监控和管理文献解析任务队列</p>
      </div>
      <div class="header-actions">
        <el-button class="btn-secondary" @click="load">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M4 20v-6h6"/><path d="M20.49 15a9 9 0 00-2.12-9.36L5 18"/></svg>
          <span>刷新</span>
        </el-button>
      </div>
    </div>

    <div class="content-grid">
      <div class="tasks-panel soft-card">
        <div class="panel-header">
          <h3 class="panel-title">任务列表</h3>
          <div class="panel-header-right">
            <span class="panel-count">共 {{ rows.length }} 条</span>
            <el-select v-model="status" clearable placeholder="状态筛选" @change="load" style="width: 120px; margin-left: 12px">
              <el-option label="排队中" value="queued" />
              <el-option label="运行中" value="running" />
              <el-option label="失败" value="failed" />
              <el-option label="已完成" value="completed" />
            </el-select>
          </div>
        </div>
        <div class="table-wrapper">
          <el-table :data="rows" height="100%">>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="paper_id" label="文献 ID" />
          <el-table-column prop="user_id" label="用户 ID" width="100" />
          <el-table-column prop="task_type" label="任务类型" width="110" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'running' ? 'warning' : 'info'"
                size="small"
              >
                {{ getStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="priority" label="优先级" width="100">
            <template #default="{ row }">
              <el-input-number v-model="row.priority" size="small" :min="0" :max="9" @change="adminApi.setTaskPriority(row.id, row.priority)" />
            </template>
          </el-table-column>
          <el-table-column prop="retry_count" label="重试次数" width="90" />
          <el-table-column prop="error_log" label="错误日志" show-overflow-tooltip />
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button size="small" @click="adminApi.cancelTask(row.id).then(load)">终止</el-button>
              <el-button size="small" type="primary" @click="adminApi.retryTask(row.id).then(load)">重试</el-button>
            </template>
          </el-table-column>
        </el-table>
        </div>
      </div>

      <div class="config-panel soft-card">
        <div class="config-section">
          <div class="panel-header">
            <h3 class="panel-title">调度策略</h3>
          </div>
          <el-form label-position="top" :model="cfg">
            <el-form-item label="最大并发任务数">
              <el-input-number v-model="cfg.max_concurrent_tasks" class="w-full" />
            </el-form-item>
            <el-form-item label="单用户并发限制">
              <el-input-number v-model="cfg.per_user_concurrent" class="w-full" />
            </el-form-item>
            <el-form-item label="超时秒数">
              <el-input-number v-model="cfg.timeout_seconds" class="w-full" />
            </el-form-item>
            <el-form-item>
              <el-button class="btn-primary w-full" @click="saveConfig">保存配置</el-button>
            </el-form-item>
          </el-form>
        </div>

        <el-divider />

        <div class="failure-section">
          <div class="panel-header">
            <h3 class="panel-title">失败原因分类</h3>
          </div>
          <div class="failure-summary">
            <div class="failure-stat">
              <span class="stat-value">{{ failure.failed_total || 0 }}</span>
              <span class="stat-label">失败总数</span>
            </div>
          </div>
          <div class="failure-tags">
            <div v-for="r in failure.by_reason" :key="r.reason" class="failure-item">
              <span class="reason-text">{{ r.reason }}</span>
              <span class="reason-count">× {{ r.count }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-admin-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  flex: 1;
  min-height: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--academic-text-main);
  margin: 0;
  letter-spacing: -0.01em;
}

.page-subtitle {
  font-size: 14px;
  color: var(--academic-text-muted);
  margin: 6px 0 0;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.btn-secondary {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  background: var(--academic-panel);
  border-color: var(--academic-border);
  color: var(--academic-text-body);
}

.btn-secondary:hover {
  background: var(--academic-primary-light);
  border-color: var(--academic-primary);
  color: var(--academic-primary);
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 20px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
  height: 0;
}

.tasks-panel {
  padding: 24px;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  overflow: hidden;
}

.table-wrapper {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin: 0;
}

.panel-count {
  font-size: 13px;
  color: var(--academic-text-muted);
}

.panel-header-right {
  display: flex;
  align-items: center;
}

.config-panel {
  padding: 24px;
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.config-section {
  flex-shrink: 0;
}

.failure-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.btn-primary {
  padding: 9px 18px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  background: var(--academic-primary);
  border-color: var(--academic-primary);
  color: #fff;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: var(--academic-primary-hover);
  border-color: var(--academic-primary-hover);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

.failure-summary {
  margin-bottom: 16px;
}

.failure-stat {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.failure-stat .stat-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--danger);
}

.failure-stat .stat-label {
  font-size: 13px;
  color: var(--academic-text-muted);
}

/* 失败列表大容器 */
.failure-tags {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 100%;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden; /* 彻底禁用横向滚动 */
  /* Firefox 滚动条 */
  scrollbar-width: thin;
  scrollbar-color: #c0c4cc transparent;
}
/* Chrome / Edge 滚动条样式，和 el-table 原生滚动条一致 */
.failure-tags::-webkit-scrollbar {
  width: 6px;
}
.failure-tags::-webkit-scrollbar-track {
  background: transparent;
}
.failure-tags::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}
.failure-tags::-webkit-scrollbar-thumb:hover {
  background: #909399;
}

/* 每一个独立的报错条目样式 */
.failure-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start; /* 顶部对齐 */
  gap: 12px;
  padding: 8px 12px;
  background-color: #fef2f2; /* 浅红底色，类似 plain danger tag */
  border: 1px solid #fee2e2;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
}

/* 报错文本：允许彻底换行，撑开高度 */
.reason-text {
  color: #ef4444; /* 红色高亮 */
  word-break: break-all;
  white-space: pre-wrap; /* 保持文本天然换行与空格 */
  flex: 1; /* 撑满左侧剩余空间 */
}

/* 错误次数角标 */
.reason-count {
  font-weight: 600;
  color: #b91c1c;
  background: #fca5a5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  white-space: nowrap; /* 数量不换行 */
  margin-top: 2px;
}

:deep(.el-table) {
  --el-table-header-bg-color: var(--academic-canvas);
  --el-table-row-hover-bg-color: var(--academic-primary-light);
}
</style>