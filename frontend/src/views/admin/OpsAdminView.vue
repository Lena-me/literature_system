<!-- frontend/src/views/admin/OpsAdminView.vue -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api/admin'

const vector = ref<any>({})
const logs = ref<any[]>([])
const backups = ref<any[]>([])
const loading = ref(true)

const vectorEntries = computed(() => Object.entries(vector.value || {}))

async function load() {
  loading.value = true
  try {
    const [v, l, b] = await Promise.all([
      adminApi.vectorStats().catch(() => ({})),
      adminApi.logs(),
      adminApi.vectorBackups().catch(() => []),
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
  }
  return map[String(key)] || String(key)
}

function resultClass(result: string) {
  return result === 'success' ? 'is-success' : 'is-danger'
}
</script>

<template>
  <div class="admin-page" v-loading="loading">
    <section v-if="vectorEntries.length" class="admin-metrics-bar is-wrap">
      <template v-for="(entry, idx) in vectorEntries" :key="String(entry[0])">
        <div v-if="idx > 0" class="admin-metric-divider" />
        <div class="admin-metric">
          <span class="admin-metric-label">{{ formatKey(entry[0]) }}</span>
          <span class="admin-metric-value metric-value-sm">{{ entry[1] }}</span>
        </div>
      </template>
    </section>

    <div class="admin-page-body">
      <section class="admin-section">
        <div class="admin-section-header">
          <div>
            <h2 class="admin-section-title">向量库备份</h2>
            <span class="admin-section-meta">{{ backups.length }} 条记录</span>
          </div>
          <el-button text type="primary" @click="createBackup">手动备份</el-button>
        </div>
        <div class="admin-el-table flush-x">
          <el-table :data="backups" size="default">
            <el-table-column prop="id" label="ID" width="72" />
            <el-table-column prop="backup_type" label="类型" width="100" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <span class="admin-status" :class="row.status === 'completed' ? 'is-success' : 'is-warning'">
                  {{ row.status === 'completed' ? '已完成' : row.status }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="file_location" label="位置" show-overflow-tooltip />
            <el-table-column label="操作" width="88">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="restoreBackup(row.id)">恢复</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>

      <section class="admin-section">
        <div class="admin-section-header">
          <div>
            <h2 class="admin-section-title">操作日志 / 行为审计</h2>
            <span class="admin-section-meta">{{ logs.length }} 条</span>
          </div>
          <el-button text @click="load">刷新</el-button>
        </div>
        <div class="admin-el-table flush-x">
          <el-table :data="logs" size="default" height="calc(100vh - 420px)">
            <el-table-column prop="id" label="ID" width="72" />
            <el-table-column prop="user_id" label="用户 ID" width="96" />
            <el-table-column prop="module" label="模块" width="110" />
            <el-table-column prop="operation_type" label="操作" min-width="120" />
            <el-table-column prop="operation_result" label="结果" width="88">
              <template #default="{ row }">
                <span class="admin-status" :class="resultClass(row.operation_result)">
                  {{ row.operation_result === 'success' ? '成功' : '失败' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="ip_address" label="IP" width="130" />
            <el-table-column prop="created_at" label="时间" width="168" />
          </el-table>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.metric-value-sm {
  font-size: 1.25rem;
}

.admin-el-table.flush-x {
  padding: 0;
  margin: 0 -0.25rem;
}
</style>
