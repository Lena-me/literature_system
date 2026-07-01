<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '@/api/admin'

const rows = ref<any[]>([])
const loading = ref(false)
const visible = ref(false)
const resetDialogVisible = ref(false)
const resetPasswordData = ref<{ username: string; phone: string; newPassword: string; userId: number }>({
  username: '',
  phone: '',
  newPassword: '',
  userId: 0
})
const searchKeyword = ref('')
const sortBy = ref<string>('created_at')
const sortOrder = ref<string>('desc')

const form = reactive<any>({
  id: null,
  username: '',
  email: '',
  phone: '',
  status: 'active',
  quota: {
    single_file_max_mb: 200,
    total_papers: 1000,
    daily_qa_calls: 200,
    concurrent_tasks: 2,
    vector_storage_mb: 10240,
    alert_threshold: 0.8
  }
})

async function load() {
  loading.value = true
  try {
    const allUsers = await adminApi.users({
      keyword: searchKeyword.value || undefined,
      sort_by: sortBy.value,
      sort_order: sortOrder.value
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

onMounted(load)

function openCreate() {
  Object.assign(form, {
    id: null,
    username: '',
    email: '',
    phone: '',
    status: 'active',
    quota: {
      single_file_max_mb: 200,
      total_papers: 1000,
      daily_qa_calls: 200,
      concurrent_tasks: 2,
      vector_storage_mb: 10240,
      alert_threshold: 0.8
    }
  })
  visible.value = true
}

function openEdit(row: any) {
  Object.assign(form, {
    id: row.id,
    username: row.username,
    email: row.email,
    phone: row.phone,
    status: row.status,
    quota: {
      single_file_max_mb: 200,
      total_papers: 1000,
      daily_qa_calls: 200,
      concurrent_tasks: 2,
      vector_storage_mb: 10240,
      alert_threshold: 0.8,
      ...(row.quota || {})
    }
  })
  visible.value = true
}

async function save() {
  if (form.id) {
    await adminApi.updateUser(form.id, {
      email: form.email,
      status: form.status,
      quota: form.quota
    })
  } else {
    await adminApi.createUser({ ...form, role: 'researcher' })
  }
  visible.value = false
  await load()
  ElMessage.success('已保存')
}

async function toggle(row: any) {
  await adminApi.updateUser(row.id, {
    status: row.status === 'active' ? 'disabled' : 'active'
  })
  await load()
}

function generateRandomPassword(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let result = ''
  const array = new Uint32Array(16)
  crypto.getRandomValues(array)
  for (let i = 0; i < 16; i++) {
    result += chars[array[i] % chars.length]
  }
  return result
}

async function resetPassword(row: any) {
  const newPassword = generateRandomPassword()
  resetPasswordData.value = {
    username: row.username,
    phone: row.phone,
    newPassword: newPassword,
    userId: row.id
  }
  resetDialogVisible.value = true
}

async function confirmResetPassword() {
  await adminApi.resetPassword(resetPasswordData.value.userId, resetPasswordData.value.newPassword)
  resetDialogVisible.value = false
  ElMessage.success('密码已成功重置')
  await load()
}

async function copyResetPassword() {
  try {
    await navigator.clipboard.writeText(resetPasswordData.value.newPassword)
    ElMessage.success('密码已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

function getRowClassName({ row }: { row: any }) {
  return row.status === 'disabled' ? 'disabled-row' : ''
}
</script>

<template>
  <div class="user-admin-page" v-loading="loading" element-loading-text="加载中...">
    <div class="page-header">
      <h1 class="page-title">用户账号与资源配额</h1>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="用户名（模糊）、完整手机号、ID"
          clearable
          style="width: 280px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button class="btn-secondary" @click="handleSearch">搜索</el-button>
      </div>
    </div>

    <div class="content-panel soft-card">
      <el-table
        :data="rows"
        height="calc(100vh - 220px)"
        :row-class-name="getRowClassName"
      >
        <el-table-column prop="id" label="ID" width="70">
          <template #header>
            <span class="sort-header" @click="toggleSort('id')">
              ID
              <span class="sort-icon">
                <svg v-if="sortBy === 'id' && sortOrder === 'asc'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 9l-6-6-6 6"/></svg>
                <svg v-else-if="sortBy === 'id' && sortOrder === 'desc'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 15l6 6 6-6"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 9l-6-6-6 6"/><path d="M6 15l6 6 6-6"/></svg>
              </span>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="email" label="邮箱" min-width="280" />
        <el-table-column prop="status" label="状态" width="110">
          <template #header>
            <span class="sort-header" @click="toggleSort('status')">
              状态
              <span class="sort-icon">
                <svg v-if="sortBy === 'status' && sortOrder === 'asc'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 9l-6-6-6 6"/></svg>
                <svg v-else-if="sortBy === 'status' && sortOrder === 'desc'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 15l6 6 6-6"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 9l-6-6-6 6"/><path d="M6 15l6 6 6-6"/></svg>
              </span>
            </span>
          </template>
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'warning'" size="small">
              {{ row.status === 'active' ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #header>
            <span class="sort-header" @click="toggleSort('created_at')">
              创建时间
              <span class="sort-icon">
                <svg v-if="sortBy === 'created_at' && sortOrder === 'asc'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 9l-6-6-6 6"/></svg>
                <svg v-else-if="sortBy === 'created_at' && sortOrder === 'desc'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 15l6 6 6-6"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 9l-6-6-6 6"/><path d="M6 15l6 6 6-6"/></svg>
              </span>
            </span>
          </template>
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="上次登录时间" width="170">
          <template #header>
            <span class="sort-header" @click="toggleSort('last_login_at')">
              上次登录时间
              <span class="sort-icon">
                <svg v-if="sortBy === 'last_login_at' && sortOrder === 'asc'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 9l-6-6-6 6"/></svg>
                <svg v-else-if="sortBy === 'last_login_at' && sortOrder === 'desc'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 15l6 6 6-6"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 9l-6-6-6 6"/><path d="M6 15l6 6 6-6"/></svg>
              </span>
            </span>
          </template>
          <template #default="{ row }">
            {{ row.last_login_at ? new Date(row.last_login_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="上次登录IP" width="150">
          <template #default="{ row }">
            <div class="ip-cell" v-if="row.last_login_ip">
              <span>{{ row.showIp ? row.last_login_ip : '***.***.***.***' }}</span>
              <button class="eye-btn" @click.stop="row.showIp = !row.showIp" :title="row.showIp ? '隐藏IP' : '查看IP'">
                <svg v-if="!row.showIp" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                </svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                  <path d="M9 12l2 2 4-4"></path>
                </svg>
              </button>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggle(row)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-button size="small" @click="resetPassword(row)">
              重置密码
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="visible" title="账号与资源配额" width="720px" class="custom-dialog">
      <el-form label-position="top">
        <el-row :gutter="14">
          <el-col :span="12">
            <el-form-item label="手机号">
              <el-input v-model="form.phone" :disabled="!!form.id" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="form.username" :disabled="!!form.id" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="14">
          <el-col :span="12">
            <el-form-item label="邮箱">
              <el-input v-model="form.email" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="状态">
              <el-select v-model="form.status">
                <el-option value="active" label="启用" />
                <el-option value="disabled" label="禁用" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-divider>资源配额</el-divider>
        <el-row :gutter="14">
          <el-col :span="8">
            <el-form-item label="单文件上限MB">
              <el-input-number v-model="form.quota.single_file_max_mb" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="总文献数">
              <el-input-number v-model="form.quota.total_papers" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="每日问答次数">
              <el-input-number v-model="form.quota.daily_qa_calls" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="14">
          <el-col :span="8">
            <el-form-item label="并发任务数">
              <el-input-number v-model="form.quota.concurrent_tasks" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="向量空间MB">
              <el-input-number v-model="form.quota.vector_storage_mb" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="告警阈值">
              <el-input-number v-model="form.quota.alert_threshold" :step="0.05" :min="0" :max="1" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetDialogVisible" title="重置密码" width="500px" class="custom-dialog">
      <div class="reset-password-content">
        <p>是否将用户：<strong>{{ resetPasswordData.username }}</strong>，手机号：<strong>{{ resetPasswordData.phone }}</strong> 的密码重置为：</p>
        <div class="password-display">
          <span>{{ resetPasswordData.newPassword }}</span>
          <el-button size="small" @click="copyResetPassword">复制密码</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="resetDialogVisible = false">否</el-button>
        <el-button type="primary" @click="confirmResetPassword">是</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.user-admin-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--academic-text-main);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.btn-secondary {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
}

.btn-primary {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  background: var(--academic-primary);
  border-color: var(--academic-primary);
}

.btn-primary:hover {
  background: var(--academic-primary-hover);
  border-color: var(--academic-primary-hover);
}

.content-panel {
  padding: 0;
  overflow: hidden;
}

.disabled-row {
  opacity: 0.5;
}

:deep(.el-table) {
  --el-table-header-bg-color: var(--academic-canvas);
  --el-table-row-hover-bg-color: var(--academic-primary-light);
}

.sort-header {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s;
}

.sort-header:hover {
  background: var(--academic-primary-light);
}

.sort-icon {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: var(--academic-text-muted);
  transition: color 0.15s;
}

.sort-header:hover .sort-icon {
  color: var(--academic-primary);
}

.ip-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.eye-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--academic-text-muted);
  padding: 2px;
  border-radius: 4px;
  transition: all 0.15s;
}

.eye-btn:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

:deep(.custom-dialog .el-dialog__header) {
  padding: 20px 24px 16px;
}

:deep(.custom-dialog .el-dialog__body) {
  padding: 16px 24px;
}

:deep(.custom-dialog .el-dialog__footer) {
  padding: 16px 24px 20px;
}

.reset-password-content {
  padding: 12px 0;
}

.reset-password-content p {
  margin: 0 0 16px 0;
  line-height: 1.7;
}

.password-display {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: var(--academic-primary-light);
  border-radius: 8px;
  font-family: monospace;
  font-size: 14px;
  word-break: break-all;
}

.password-display span {
  flex: 1;
  color: var(--academic-primary);
}
</style>