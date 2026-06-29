<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import StatCard from '@/components/common/StatCard.vue'
import { featuresApi } from '@/api/features'
const overview = ref<any>({ paper_count:0, report_count:0, qa_count:0, records:[], recent_records:[] })
const chartRef = ref<HTMLDivElement | null>(null)
onMounted(async()=>{ overview.value = await featuresApi.overview(); overview.value.records = overview.value.records || overview.value.recent_records || []; setTimeout(render, 50) })
function render(){ if(!chartRef.value) return; const chart=echarts.init(chartRef.value); const data=Object.entries(overview.value.keyword_cloud || {RAG:8, Agent:6, 复现:5, 方法:10, 数据集:7}); chart.setOption({ backgroundColor:'transparent', tooltip:{}, series:[{ type:'pie', radius:['45%','72%'], data:data.map(([name,value])=>({name,value})), label:{color:'#eef6ff'} }] }) }
</script>
<template>
  <div class="archive fade-slide">
    <div class="stats"><StatCard label="文献阅读数量" :value="overview.paper_count" /><StatCard label="报告生成数量" :value="overview.report_count" /><StatCard label="问答次数" :value="overview.qa_count" /></div>
    <section class="grid2"><div class="glass panel"><h3>关键词分布</h3><div ref="chartRef" class="chart" /></div><div class="glass panel"><h3>历史操作记录</h3><el-timeline><el-timeline-item v-for="r in overview.records" :key="r.id" :timestamp="r.created_at">{{ r.event_type }} · paper {{ r.paper_id || '-' }}</el-timeline-item></el-timeline></div></section>
  </div>
</template>
<style scoped>.archive{display:flex;flex-direction:column;gap:18px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}.panel{border-radius:28px;padding:22px;min-height:500px}.chart{height:420px}</style>
