<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '@/api/admin'

const route = useRoute()
const rows = ref<any[]>([])
const loading = ref(false)
const drawerVisible = ref(false)
const drawerLoading = ref(false)
const detail = ref<any>(null)
const resetDialogVisible = ref(false)
const resetPasswordData = ref<{ username: string; phone: string; newPassword: string; userId: number }>({
  username: '',
  phone: '',
  newPassword: '',
  userId: 0,
})
const searchKeyword = ref('')
const sortBy = ref<string>('created_at')
const sortOrder = ref<string>('desc')

const quotaForm = reactive<any>({
  single_file_max_mb: 200,
  total_papers: 1000,
  daily_qa_calls: 200,
  concurrent_tasks: 2,
  vector_storage_mb: 10240,
  alert_threshold: 0.8,
})

async function load() {
  loading.value = true
  try {
    const allUsers = await adminApi.users({
      keyword: searchKeyword.value || undefined,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
    })
    rows.value = allUsers.filter((user: any) => user.role !== 'admin')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  load()
}

function toggleSort(prop: string) {
  if (['id', 'status', 'created_at', 'last_login_at'].includes(prop)) {
    if (sortBy.value === prop) {
      sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortBy.value = prop
      sortOrder.value = 'desc'
    }
    load()
  }
}

async function openDrawer(row: any) {
  drawerVisible.value = true
  drawerLoading.value = true
  detail.value = null
  try {
    detail.value = await adminApi.userDetail(row.id)
    Object.assign(quotaForm, detail.value.user?.quota || {})
  } finally {
    drawerLoading.value = false
  }
}

async function saveQuota() {
  if (!detail.value?.user?.id) return
  await adminApi.updateUser(detail.value.user.id, { quota: { ...quotaForm } })
  ElMessage.success('配额已更新')
  await openDrawer({ id: detail.value.user.id })
  await load()
}

async function toggleBan() {
  if (!detail.value?.user) return
  const u = detail.value.user
  const next = u.status === 'active' ? 'disabled' : 'active'
  const label = next === 'disabled' ? '封禁' : '解除封禁'
  try {
    await ElMessageBox.confirm(`确认${label}用户 ${u.username}？`, label, { type: 'warning' })
  } catch {
    return
  }
  await adminApi.updateUser(u.id, { status: next })
  ElMessage.success(`已${label}`)
  await openDrawer({ id: u.id })
  await load()
}

function generateRandomPassword(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let result = ''
  const array = new Uint32Array(16)
  crypto.getRandomValues(array)
  for (let i = 0; i < 16; i++) result += chars[array[i] % chars.length]
  return result
}

async function resetPassword(row: any) {
  resetPasswordData.value = {
    username: row.username,
    phone: row.phone,
    newPassword: generateRandomPassword(),
    userId: row.id,
  }
  resetDialogVisible.value = true
}

async function confirmResetPassword() {
  await adminApi.resetPassword(resetPasswordData.value.userId, resetPasswordData.value.newPassword)
  resetDialogVisible.value = false
  ElMessage.success('密码已成功重置')
}

async function copyResetPassword() {
  try {
    await navigator.clipboard.writeText(resetPasswordData.value.newPassword)
    ElMessage.success('密码已复制')
  } catch {
    ElMessage.warning('复制失败')
  }
}

function getRowClassName({ row }: { row: any }) {
  return row.status === 'disabled' ? 'disabled-row' : ''
}

onMounted(() => {
  if (route.query.keyword) {
    searchKeyword.value = String(route.query.keyword)
  }
  load()
})

watch(
  () => route.query.keyword,
  kw => {
    if (kw) {
      searchKeyword.value = String(kw)
      load()
    }
  },
)
</script>

<template>
  <div class="admin-page" v-loading="loading">
    <div class="admin-toolbar">
      <div class="admin-toolbar-left">
        <el-input
          v-model="searchKeyword"
          placeholder="用户名 / ID / 手机号"
          clearable
          style="width: 260px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button text @click="handleSearch">搜索</el-button>
      </div>
      <span class="admin-toolbar-meta">共 {{ rows.length }} 位用户</span>
    </div>

    <div class="admin-el-table is-clickable">
      <el-table :data="rows" size="default" height="calc(100vh - 168px)" :row-class-name="getRowClassName" @row-click="openDrawer">
        <el-table-column prop="id" label="ID" width="72">
          <template #header>
            <span class="sort-header" @click="toggleSort('id')">ID</span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="status" label="状态" width="88">
          <template #header>
            <span class="sort-header" @click="toggleSort('status')">状态</span>
          </template>
          <template #default="{ row }">
            <span class="admin-status" :class="row.status === 'active' ? 'is-success' : 'is-warning'">
              {{ row.status === 'active' ? '启用' : '禁用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="168">
          <template #header>
            <span class="sort-header" @click="toggleSort('created_at')">注册时间</span>
          </template>
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="168" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click.stop="openDrawer(row)">编辑</el-button>
            <el-button link size="small" @click.stop="resetPassword(row)">重置密码</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer v-model="drawerVisible" title="用户详情与配额" size="480px" destroy-on-close>
      <div v-loading="drawerLoading" class="drawer-body">
        <template v-if="detail?.user">
          <div class="drawer-section user-header">
            <div>
              <h3>{{ detail.user.username }}</h3>
              <p class="sub">ID {{ detail.user.id }} · {{ detail.user.phone || '—' }} · {{ detail.user.email || '—' }}</p>
            </div>
            <el-button
              :type="detail.user.status === 'active' ? 'danger' : 'success'"
              size="small"
              plain
              @click="toggleBan"
            >
              {{ detail.user.status === 'active' ? '封禁用户' : '解除封禁' }}
            </el-button>
          </div>

          <div class="drawer-section">
            <h4>配额调节</h4>
            <div class="quota-item">
              <label>单日问答次数上限</label>
              <el-slider v-model="quotaForm.daily_qa_calls" :min="10" :max="2000" :step="10" show-input />
            </div>
            <div class="quota-item">
              <label>并发解析数</label>
              <el-slider v-model="quotaForm.concurrent_tasks" :min="1" :max="20" show-input />
            </div>
            <div class="quota-row">
              <span>单文件上限 MB</span>
              <el-input-number v-model="quotaForm.single_file_max_mb" :min="10" :max="2048" size="small" />
            </div>
            <div class="quota-row">
              <span>总文献数</span>
              <el-input-number v-model="quotaForm.total_papers" :min="1" :max="10000" size="small" />
            </div>
            <el-button type="primary" size="small" @click="saveQuota">保存配额</el-button>
          </div>

          <div class="drawer-section">
            <h4>最近审计日志</h4>
            <el-timeline v-if="detail.audit_logs?.length">
              <el-timeline-item
                v-for="log in detail.audit_logs"
                :key="log.id"
                :timestamp="log.created_at ? new Date(log.created_at).toLocaleString('zh-CN') : ''"
                placement="top"
              >
                <div class="log-item">
                  <span class="log-type">{{ log.operation_type }}</span>
                  <p>{{ log.operation_content || '—' }}</p>
                </div>
              </el-timeline-item>
            </el-timeline>
            <div v-else class="admin-empty">暂无审计记录</div>
          </div>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="resetDialogVisible" title="重置密码" width="480px">
      <p>用户 <strong>{{ resetPasswordData.username }}</strong> 的新密码：</p>
      <div class="password-display">
        <span>{{ resetPasswordData.newPassword }}</span>
        <el-button size="small" @click="copyResetPassword">复制</el-button>
      </div>
      <template #footer>
        <el-button @click="resetDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmResetPassword">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.sort-header {
  cursor: pointer;
}

.sort-header:hover {
  color: #0f172a;
}

.disabled-row {
  opacity: 0.5;
}

.drawer-body {
  min-height: 200px;
}

.drawer-section {
  margin-bottom: 1.5rem;
}

.drawer-section h4 {
  margin: 0 0 0.75rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #0f172a;
}

.user-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #e5e7eb;
}

.user-header h3 {
  margin: 0 0 0.25rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: #0f172a;
}

.sub {
  margin: 0;
  font-size: 0.75rem;
  color: #64748b;
}

.quota-item {
  margin-bottom: 1rem;
}

.quota-item label {
  display: block;
  font-size: 0.75rem;
  color: #64748b;
  margin-bottom: 0.375rem;
}

.quota-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.625rem;
  font-size: 0.8125rem;
  color: #334155;
}

.log-item .log-type {
  font-size: 0.75rem;
  font-weight: 600;
  color: #0f172a;
}

.log-item p {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  color: #64748b;
}

.password-display {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid #f1f5f9;
  font-family: ui-monospace, monospace;
  font-size: 0.875rem;
}
</style>
