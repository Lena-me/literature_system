<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import StatCard from '@/components/common/StatCard.vue'
import { adminApi } from '@/api/admin'
const health = ref<any>({}); const ops = ref<any>({}); const chartEl = ref<HTMLDivElement | null>(null)
onMounted(async()=>{ health.value=await adminApi.systemHealth(); ops.value=await adminApi.operationStats().catch(()=>({})); setTimeout(render,50) })
function render(){ if(!chartEl.value) return; echarts.init(chartEl.value).setOption({ backgroundColor:'transparent', tooltip:{}, xAxis:{type:'category',data:['上传','解析','问答','报告','图谱'],axisLabel:{color:'#9fb1cc'}}, yAxis:{type:'value',axisLabel:{color:'#9fb1cc'},splitLine:{lineStyle:{color:'rgba(255,255,255,.08)'}}}, series:[{type:'bar',data:[ops.value.total_uploaded||0,ops.value.total_parsed||0,ops.value.total_qa_calls||0,ops.value.total_reports||0,ops.value.total_graphs||0]}] }) }
</script>
<template>
  <div class="admin-page fade-slide">
    <h1 class="gradient-title">系统运维总览</h1>
    <div class="stats"><StatCard label="服务状态" :value="health.status || 'ok'" /><StatCard label="Redis" :value="String(health.redis ?? '-')" /><StatCard label="向量库规模" :value="ops.vector_db_total || 0" /><StatCard label="问答调用" :value="ops.total_qa_calls || 0" /></div>
    <section class="glass chart-panel"><h3>核心业务趋势</h3><div ref="chartEl" class="chart" /></section>
  </div>
</template>
<style scoped>.admin-page{display:flex;flex-direction:column;gap:18px}h1{font-size:36px;margin:0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.chart-panel{border-radius:28px;padding:22px}.chart{height:420px}</style>
