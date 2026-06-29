<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { adminApi } from '@/api/admin'
const rows=ref<any[]>([]); const visible=ref(false); const form=reactive<any>({ model_type:'llm', model_name:'', version:'', api_endpoint:'', config:{}, is_active:true })
async function load(){ rows.value = await adminApi.models() }
onMounted(load)
async function save(){ await adminApi.saveModel(form); visible.value=false; await load() }
</script>
<template>
  <section class="glass panel fade-slide"><div class="head"><h2 class="gradient-title">模型配置中心</h2><el-button class="is-glow" @click="visible=true">新增模型</el-button></div>
    <el-table :data="rows" height="calc(100vh - 190px)"><el-table-column prop="id" label="ID" width="70" /><el-table-column prop="model_type" label="类型" width="110" /><el-table-column prop="model_name" label="模型名称" /><el-table-column prop="version" label="版本" /><el-table-column prop="api_endpoint" label="调用地址" /><el-table-column prop="is_active" label="启用" width="90" /></el-table>
    <el-dialog v-model="visible" title="新增模型配置" width="620px"><el-form label-position="top"><el-form-item label="模型类型"><el-select v-model="form.model_type"><el-option label="解析模型" value="parse"/><el-option label="向量模型" value="vector"/><el-option label="重排模型" value="reranker"/><el-option label="大语言模型" value="llm"/></el-select></el-form-item><el-form-item label="模型名称"><el-input v-model="form.model_name" /></el-form-item><el-form-item label="版本"><el-input v-model="form.version" /></el-form-item><el-form-item label="调用地址"><el-input v-model="form.api_endpoint" /></el-form-item><el-form-item label="是否启用"><el-switch v-model="form.is_active" /></el-form-item></el-form><template #footer><el-button @click="visible=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog>
  </section>
</template>
<style scoped>.panel{border-radius:28px;padding:22px}.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}h2{margin:0;font-size:30px}</style>
