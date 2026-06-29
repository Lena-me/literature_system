<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { usePaperStore } from '@/stores/papers'
import { papersApi } from '@/api/papers'
const store = usePaperStore(); const editVisible = ref(false); const form = reactive<any>({})
onMounted(() => store.load())
function edit(row:any){ Object.assign(form,row); editVisible.value=true }
async function save(){ await papersApi.update(form.id, form); editVisible.value=false; await store.load() }
</script>
<template>
  <div class="library glass fade-slide">
    <div class="head"><h2 class="gradient-title">文献库管理</h2><el-button class="is-glow" @click="store.load">刷新</el-button></div>
    <el-table :data="store.list" height="calc(100vh - 190px)" row-key="id">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="论文标题" min-width="260"><template #default="{row}"><b>{{ row.title || row.original_filename }}</b><p>{{ row.original_filename }}</p></template></el-table-column>
      <el-table-column prop="parse_status" label="解析状态" width="110" />
      <el-table-column prop="journal_conf" label="期刊/会议" width="180" />
      <el-table-column prop="publication_year" label="年份" width="90" />
      <el-table-column label="操作" width="220"><template #default="{row}"><el-button size="small" @click="edit(row)">编辑</el-button><el-button size="small" @click="papersApi.reparse(row.id)">重解析</el-button><el-button size="small" type="danger" @click="papersApi.remove(row.id).then(()=>store.load())">删除</el-button></template></el-table-column>
    </el-table>
    <el-dialog v-model="editVisible" title="编辑文献元数据" width="620px">
      <el-form label-position="top"><el-form-item label="标题"><el-input v-model="form.title" /></el-form-item><el-form-item label="DOI"><el-input v-model="form.doi" /></el-form-item><el-form-item label="期刊/会议"><el-input v-model="form.journal_conf" /></el-form-item><el-form-item label="年份"><el-input-number v-model="form.publication_year" /></el-form-item><el-form-item label="备注"><el-input v-model="form.notes" type="textarea" /></el-form-item></el-form>
      <template #footer><el-button @click="editVisible=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<style scoped>.library{border-radius:30px;padding:24px}.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}h2{margin:0;font-size:30px}p{margin:4px 0 0;color:#8798b6;font-size:12px}</style>
