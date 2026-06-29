<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { adminApi } from '@/api/admin'
const vector=ref<any>({}); const logs=ref<any[]>([]); const backups=ref<any[]>([])
async function load(){ vector.value=await adminApi.vectorStats().catch(()=>({})); logs.value=await adminApi.logs(); backups.value=await adminApi.vectorBackups().catch(()=>[]) }
onMounted(load)
</script>
<template>
  <section class="ops fade-slide"><div class="glass panel"><div class="head"><h2 class="gradient-title">向量库资源监控</h2><el-button class="is-glow" @click="load">刷新</el-button></div><div class="kv"><div v-for="(v,k) in vector" :key="k"><span>{{ k }}</span><b>{{ v }}</b></div></div><el-button @click="adminApi.createBackup().then(load)">手动备份</el-button><el-table :data="backups" height="220"><el-table-column prop="id" label="ID"/><el-table-column prop="backup_type" label="类型"/><el-table-column prop="status" label="状态"/><el-table-column prop="file_location" label="位置"/><el-table-column label="操作"><template #default="{row}"><el-button size="small" @click="adminApi.restoreBackup(row.id).then(load)">恢复</el-button></template></el-table-column></el-table></div><div class="glass panel"><h2>操作日志 / 行为审计</h2><el-table :data="logs" height="calc(100vh - 260px)"><el-table-column prop="id" label="ID" width="70"/><el-table-column prop="user_id" label="用户"/><el-table-column prop="module" label="模块"/><el-table-column prop="operation_type" label="操作"/><el-table-column prop="operation_result" label="结果"/><el-table-column prop="ip_address" label="IP"/><el-table-column prop="created_at" label="时间"/></el-table></div></section>
</template>
<style scoped>.ops{display:grid;grid-template-columns:430px 1fr;gap:18px}.panel{border-radius:28px;padding:22px}.head{display:flex;justify-content:space-between;align-items:center}.kv{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}.kv div{background:rgba(255,255,255,.07);border-radius:16px;padding:14px}.kv span{display:block;color:var(--muted);font-size:12px}.kv b{display:block;font-size:22px;margin-top:8px}</style>
