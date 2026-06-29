<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { reportsApi } from '@/api/reports'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import type { Report } from '@/types/domain'
const list = ref<Report[]>([]); const current = ref<Report | null>(null)
onMounted(async()=>{ list.value = await reportsApi.list(); current.value=list.value[0] || null })
function markdown(r: Report | null){ return r?.content?.markdown || JSON.stringify(r?.content || {}, null, 2) }
async function downloadReport(format: 'md' | 'docx' | 'pdf') {
  if (!current.value) return
  const res = await reportsApi.export(current.value.id, format)
  const contentType = String(res.headers['content-type'] || 'application/octet-stream')
  const blob = new Blob([res.data], { type: contentType })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${current.value.title || 'report'}.${format}`
  link.click()
  URL.revokeObjectURL(link.href)
}
</script>
<template>
  <div class="reports fade-slide">
    <aside class="glass"><h3>研读报告</h3><div v-for="r in list" :key="r.id" class="report-item" :class="{active:current?.id===r.id}" @click="current=r"><b>{{ r.title }}</b><span>{{ new Date(r.created_at).toLocaleString() }}</span></div></aside>
    <section class="glass reader"><div class="reader-head"><h2>{{ current?.title || '暂无报告' }}</h2><div><el-button :disabled="!current" @click="downloadReport('md')">导出 Markdown</el-button><el-button :disabled="!current" @click="downloadReport('docx')">导出 Word</el-button><el-button :disabled="!current" type="primary" @click="downloadReport('pdf')">导出 PDF</el-button></div></div><MarkdownRenderer :content="markdown(current)" /></section>
  </div>
</template>
<style scoped>.reports{display:grid;grid-template-columns:320px 1fr;gap:18px;height:calc(100vh - 40px)}aside,.reader{border-radius:28px;padding:22px;overflow:auto}.report-item{padding:14px;border-radius:16px;background:rgba(255,255,255,.06);margin-bottom:10px;cursor:pointer}.report-item.active{background:rgba(102,231,255,.16);border:1px solid rgba(102,231,255,.4)}.report-item b{display:block}.report-item span{font-size:12px;color:var(--muted)}.reader-head{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:16px}h2{font-size:28px}</style>
