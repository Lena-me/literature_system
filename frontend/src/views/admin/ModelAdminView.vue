<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api/admin'

const rows = ref<any[]>([])
const visible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive<any>({
  model_type: 'llm',
  model_name: '',
  version: '',
  api_endpoint: '',
  config: {},
  is_active: true
})

async function load() {
  rows.value = await adminApi.models()
}

onMounted(load)

function openCreate() {
  editingId.value = null
  Object.assign(form, {
    model_type: 'llm',
    model_name: '',
    version: '',
    api_endpoint: '',
    config: {},
    is_active: true
  })
  visible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  Object.assign(form, {
    model_type: row.model_type,
    model_name: row.model_name,
    version: row.version,
    api_endpoint: row.api_endpoint,
    config: row.config || {},
    is_active: row.is_active
  })
  visible.value = true
}

async function save() {
  if (editingId.value) {
    await adminApi.updateModel(editingId.value, form)
    ElMessage.success('模型已更新')
  } else {
    await adminApi.saveModel(form)
    ElMessage.success('模型已添加')
  }
  visible.value = false
  await load()
}

async function handleToggle(row: any) {
  await adminApi.updateModel(row.id, { is_active: row.is_active })
  ElMessage.success('状态已更新')
}

function getRowClassName({ row }: { row: any }) {
  return !row.is_active ? 'disabled-row' : ''
}
</script>

<template>
  <div class="model-admin-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">模型配置中心</h1>
        <p class="page-subtitle">管理系统中使用的各类 AI 模型</p>
      </div>
      <el-button class="btn-primary" @click="openCreate">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        <span>新增模型</span>
      </el-button>
    </div>

    <div class="content-panel soft-card">
      <div class="panel-header">
        <h3 class="panel-title">模型列表</h3>
        <div class="panel-actions">
          <el-button class="btn-secondary" @click="load">刷新</el-button>
        </div>
      </div>
      <el-table :data="rows" height="calc(100vh - 280px)" :row-class-name="getRowClassName">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="model_type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="row.model_type === 'llm' ? 'danger' : row.model_type === 'vector' ? 'primary' : row.model_type === 'reranker' ? 'warning' : 'info'" size="small">
              {{ row.model_type === 'llm' ? '大语言模型' : row.model_type === 'vector' ? '向量模型' : row.model_type === 'reranker' ? '重排模型' : '解析模型' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型名称" />
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="api_endpoint" label="调用地址" />
        <el-table-column prop="is_active" label="状态" width="100">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" @change="handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="visible" :title="editingId ? '编辑模型配置' : '新增模型配置'" width="620px" class="custom-dialog">
      <el-form label-position="top" :model="form">
        <el-row :gutter="14">
          <el-col :span="12">
            <el-form-item label="模型类型">
              <el-select v-model="form.model_type" class="w-full">
                <el-option label="解析模型" value="parse" />
                <el-option label="向量模型" value="vector" />
                <el-option label="重排模型" value="reranker" />
                <el-option label="大语言模型" value="llm" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="版本">
              <el-input v-model="form.version" placeholder="如 v1.0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="模型名称">
          <el-input v-model="form.model_name" placeholder="输入模型名称" />
        </el-form-item>
        <el-form-item label="调用地址">
          <el-input v-model="form.api_endpoint" placeholder="API 端点地址" />
        </el-form-item>
        <el-form-item label="是否启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.model-admin-page {
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

.btn-primary {
  display: flex;
  align-items: center;
  gap: 6px;
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

.content-panel {
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

.panel-actions {
  display: flex;
  gap: 8px;
}

.btn-secondary {
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

.disabled-row {
  opacity: 0.5;
}

:deep(.el-table) {
  --el-table-header-bg-color: var(--academic-canvas);
  --el-table-row-hover-bg-color: var(--academic-primary-light);
}

:deep(.custom-dialog .el-dialog__header) {
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--academic-border);
}

:deep(.custom-dialog .el-dialog__body) {
  padding: 24px;
}

:deep(.custom-dialog .el-dialog__footer) {
  padding: 16px 24px 20px;
  border-top: 1px solid var(--academic-border);
}
</style>
