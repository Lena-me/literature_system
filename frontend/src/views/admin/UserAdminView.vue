<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api/admin'
const rows = ref<any[]>([]); const loading = ref(false); const visible = ref(false)
const form = reactive<any>({ id:null, username:'', password:'', name:'', email:'', phone:'', role:'researcher', status:'active', quota:{ single_file_max_mb:200,total_papers:1000,daily_qa_calls:200,concurrent_tasks:2,vector_storage_mb:10240,alert_threshold:0.8 } })
async function load(){ loading.value=true; try{ rows.value=await adminApi.users() } finally{ loading.value=false } }
onMounted(load)
function openCreate(){ Object.assign(form,{ id:null, username:'', password:'', name:'', email:'', phone:'', role:'researcher', status:'active', quota:{ single_file_max_mb:200,total_papers:1000,daily_qa_calls:200,concurrent_tasks:2,vector_storage_mb:10240,alert_threshold:0.8 } }); visible.value=true }
function openEdit(row:any){ Object.assign(form,{ ...row, password:'', quota:{ single_file_max_mb:200,total_papers:1000,daily_qa_calls:200,concurrent_tasks:2,vector_storage_mb:10240,alert_threshold:0.8, ...(row.quota||{}) } }); visible.value=true }
async function save(){ if(form.id){ await adminApi.updateUser(form.id,{ name:form.name,email:form.email,phone:form.phone,role:form.role,status:form.status,quota:form.quota }) } else { await adminApi.createUser(form) } visible.value=false; await load(); ElMessage.success('已保存') }
async function toggle(row:any){ await adminApi.updateUser(row.id,{ status: row.status==='active'?'disabled':'active' }); await load() }
</script>
<template>
  <section class="glass panel fade-slide"><div class="head"><h2 class="gradient-title">用户账号与资源配额</h2><div><el-button @click="openCreate">新增用户</el-button><el-button class="is-glow" @click="load">刷新</el-button></div></div>
    <el-table :data="rows" v-loading="loading" height="calc(100vh - 190px)">
      <el-table-column prop="id" label="ID" width="70" /><el-table-column prop="username" label="账号" /><el-table-column prop="name" label="姓名" /><el-table-column prop="email" label="邮箱" /><el-table-column prop="phone" label="手机号" /><el-table-column prop="role" label="角色" width="120" /><el-table-column prop="status" label="状态" width="120" />
      <el-table-column label="配额" min-width="260"><template #default="{row}"><el-tag v-for="(v,k) in row.quota" :key="k" round>{{ k }}:{{ v }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="280"><template #default="{row}"><el-button size="small" @click="openEdit(row)">编辑/配额</el-button><el-button size="small" @click="toggle(row)">{{ row.status==='active'?'禁用':'启用' }}</el-button><el-button size="small" @click="adminApi.resetPassword(row.id,'admin123456')">重置密码</el-button></template></el-table-column>
    </el-table>
    <el-dialog v-model="visible" title="账号与资源配额" width="720px"><el-form label-position="top">
      <el-row :gutter="14"><el-col :span="12"><el-form-item label="用户名"><el-input v-model="form.username" :disabled="!!form.id" /></el-form-item></el-col><el-col :span="12"><el-form-item label="初始密码"><el-input v-model="form.password" :disabled="!!form.id" show-password /></el-form-item></el-col></el-row>
      <el-row :gutter="14"><el-col :span="12"><el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item></el-col><el-col :span="12"><el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item></el-col></el-row>
      <el-row :gutter="14"><el-col :span="12"><el-form-item label="手机号"><el-input v-model="form.phone" /></el-form-item></el-col><el-col :span="6"><el-form-item label="角色"><el-select v-model="form.role"><el-option value="researcher" label="科研人员"/><el-option value="admin" label="管理员"/></el-select></el-form-item></el-col><el-col :span="6"><el-form-item label="状态"><el-select v-model="form.status"><el-option value="active" label="启用"/><el-option value="disabled" label="禁用"/></el-select></el-form-item></el-col></el-row>
      <el-divider>资源配额</el-divider><el-row :gutter="14"><el-col :span="8"><el-form-item label="单文件上限MB"><el-input-number v-model="form.quota.single_file_max_mb" /></el-form-item></el-col><el-col :span="8"><el-form-item label="总文献数"><el-input-number v-model="form.quota.total_papers" /></el-form-item></el-col><el-col :span="8"><el-form-item label="每日问答次数"><el-input-number v-model="form.quota.daily_qa_calls" /></el-form-item></el-col></el-row>
      <el-row :gutter="14"><el-col :span="8"><el-form-item label="并发任务数"><el-input-number v-model="form.quota.concurrent_tasks" /></el-form-item></el-col><el-col :span="8"><el-form-item label="向量空间MB"><el-input-number v-model="form.quota.vector_storage_mb" /></el-form-item></el-col><el-col :span="8"><el-form-item label="告警阈值"><el-input-number v-model="form.quota.alert_threshold" :step="0.05" :min="0" :max="1" /></el-form-item></el-col></el-row>
    </el-form><template #footer><el-button @click="visible=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog>
  </section>
</template>
<style scoped>.panel{border-radius:28px;padding:22px}.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}h2{margin:0;font-size:30px}.el-tag{margin:2px}</style>
