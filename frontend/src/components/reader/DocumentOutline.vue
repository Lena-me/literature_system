<script setup lang="ts">
import type { ContentItem } from '@/types/domain'
defineProps<{ items: ContentItem[] }>()
</script>
<template>
  <div class="outline slim-scroll">
    <div v-if="!items.length" class="empty">暂无结构化内容，解析完成后显示章节、摘要、图表和参考文献。</div>
    <div v-for="it in items" :key="it.id" class="item" :class="it.type">
      <div class="line"><span class="type">{{ it.type }}</span><span>p.{{ it.page_number || '-' }}</span></div>
      <p :style="{ paddingLeft: `${Math.min((it.level || 1) * 6, 24)}px` }">{{ it.content }}</p>
    </div>
  </div>
</template>
<style scoped>
.outline { height: 100%; overflow:auto; padding-right: 8px; }
.empty { color: rgba(238,246,255,.5); padding: 30px; text-align: center; }
.item { padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,.08); }
.line { display:flex; justify-content:space-between; font-size:11px; color: rgba(238,246,255,.45); margin-bottom:6px; }
.type { color: var(--brand); text-transform: uppercase; }
p { margin:0; line-height: 1.65; color: rgba(238,246,255,.88); display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; overflow:hidden; }
.item.heading p { color: #fff; font-weight: 800; }
</style>
