<!-- frontend\src\views\admin\OpsAdminView.vue -->

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api/admin'

const vector = ref<any>({})
const logs = ref<any[]>([])
const backups = ref<any[]>([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const [v, l, b] = await Promise.all([
      adminApi.vectorStats().catch(() => ({})),
      adminApi.logs(),
      adminApi.vectorBackups().catch(() => [])
    ])
    vector.value = v
    logs.value = l
    backups.value = b
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function createBackup() {
  await adminApi.createBackup()
  ElMessage.success('备份已创建')
  await load()
}

async function restoreBackup(id: number) {
  await adminApi.restoreBackup(id)
  ElMessage.success('备份已恢复')
  await load()
}

function formatKey(key: string | number) {
  const map: Record<string, string> = {
    total_vectors: '总向量数',
    used_memory_mb: '已用内存(MB)',
    collection_count: '集合数量',
    index_size: '索引大小',
    last_updated: '最后更新',
    collection: '集合名称',
    index_count: '索引数量',
    shard_count: '分片数量',
    storage_mb: '存储大小(MB)',
    avg_search_latency_ms: '平均搜索延迟(ms)',
    p95_search_latency_ms: 'P95搜索延迟(ms)',
    search_success_rate: '搜索成功率',
    recall_rate: '召回率',
    health_score: '健康评分',
    'index count': '索引数量',
    'shard count': '分片数量',
    'storage mb': '存储大小(MB)',
    'avg search latency ms': '平均搜索延迟(ms)',
    'p95 search latency ms': 'P95搜索延迟(ms)',
    'search success rate': '搜索成功率',
    'recall rate': '召回率',
    'health score': '健康评分'
  }
  return map[String(key)] || String(key)
}
</script>

<template>
  <div class="ops-admin-page" v-loading="loading" element-loading-text="加载中...">
    <div class="page-header">
      <div>
        <h1 class="page-title">向量库与日志</h1>
        <p class="page-subtitle">监控向量库资源使用情况与系统操作日志</p>
      </div>
      <el-button class="btn-secondary" @click="load">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M4 20v-6h6"/><path d="M20.49 15a9 9 0 00-2.12-9.36L5 18"/></svg>
        <span>刷新</span>
      </el-button>
    </div>

    <div class="content-grid">
      <div class="vector-panel soft-card">
        <div class="panel-header">
          <h3 class="panel-title">向量库资源监控</h3>
          <el-button class="btn-primary btn-sm" @click="createBackup">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            <span>手动备份</span>
          </el-button>
        </div>

        <div class="stats-grid">
          <div v-for="(v, k) in vector" :key="k" class="stat-item">
            <span class="stat-label">{{ formatKey(k) }}</span>
            <span class="stat-value">{{ v }}</span>
          </div>
        </div>

        <el-divider />

        <div class="panel-header">
          <h3 class="panel-title">备份记录</h3>
          <span class="panel-count">{{ backups.length }} 条</span>
        </div>
        <el-table :data="backups" height="200">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="backup_type" label="类型" width="100" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'completed' ? 'success' : 'warning'" size="small">
                {{ row.status === 'completed' ? '已完成' : row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="file_location" label="位置" show-overflow-tooltip />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="restoreBackup(row.id)">恢复</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="logs-panel soft-card">
        <div class="panel-header">
          <h3 class="panel-title">操作日志 / 行为审计</h3>
          <span class="panel-count">{{ logs.length }} 条</span>
        </div>
        <el-table :data="logs" height="calc(100vh - 320px)">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="user_id" label="用户 ID" width="100" />
          <el-table-column prop="module" label="模块" width="110" />
          <el-table-column prop="operation_type" label="操作" />
          <el-table-column prop="operation_result" label="结果" width="90">
            <template #default="{ row }">
              <el-tag :type="row.operation_result === 'success' ? 'success' : 'danger'" size="small">
                {{ row.operation_result === 'success' ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP" width="130" />
          <el-table-column prop="created_at" label="时间" width="160" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ops-admin-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
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
  grid-template-columns: 420px 1fr;
  gap: 20px;
}

.vector-panel,
.logs-panel {
  padding: 24px;
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

.btn-primary {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 7px 14px;
  border-radius: 8px;
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

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.stat-item {
  background: var(--academic-primary-light);
  border-radius: 14px;
  padding: 14px;
}

.stat-item .stat-label {
  display: block;
  font-size: 12px;
  color: var(--academic-text-muted);
  margin-bottom: 6px;
}

.stat-item .stat-value {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: var(--academic-text-main);
}

:deep(.el-table) {
  --el-table-header-bg-color: var(--academic-canvas);
  --el-table-row-hover-bg-color: var(--academic-primary-light);
}
</style>
