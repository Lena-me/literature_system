<script setup lang="ts">
import type { Paper } from '@/types/domain'
defineProps<{ paper: Paper; selected?: boolean }>()
defineEmits<{ open: [Paper]; toggle: [number] }>()
function statusText(s: string) {
  const map: Record<string,string> = { uploaded: '待解析', queued: '队列中', parsing: '解析中', extracting: '抽取中', vectorizing: '向量化', completed: '已解析', indexed: '索引就绪', failed: '解析失败' }
  return map[s] || s
}
</script>
<template>
  <div class="paper-card" :class="{ selected }" @click="$emit('open', paper)">
    <div class="paper-top">
      <el-checkbox :model-value="selected" @click.stop @change="$emit('toggle', paper.id)" />
      <div class="paper-title">{{ paper.title || paper.original_filename }}</div>
    </div>
    <div class="meta"><span>{{ paper.journal_conf || '未识别期刊/会议' }}</span><span>{{ paper.publication_year || '年份未知' }}</span></div>
    <div class="tags">
      <el-tag v-for="k in (Array.isArray(paper.keywords) ? paper.keywords.slice(0,3) : [])" :key="k" effect="dark" round>{{ k }}</el-tag>
    </div>
    <div class="status"><span class="status-dot" />{{ statusText(paper.parse_status) }}</div>
  </div>
</template>
<style scoped>
.paper-card { padding: 14px; border-radius: 18px; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.1); cursor: pointer; transition: .2s ease; }
.paper-card:hover, .paper-card.selected { transform: translateY(-2px); border-color: rgba(102,231,255,.6); background: rgba(102,231,255,.1); }
.paper-top { display:flex; gap:8px; align-items:flex-start; }
.paper-title { font-weight: 750; line-height:1.35; font-size: 14px; color:#fff; flex:1; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.meta { margin: 10px 0; display:flex; justify-content:space-between; gap:10px; color:rgba(238,246,255,.54); font-size:12px; }
.tags { display:flex; flex-wrap:wrap; gap:5px; min-height: 24px; }
.status { margin-top:10px; color: var(--muted); font-size:12px; }
</style>
