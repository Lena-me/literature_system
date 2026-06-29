<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import mk from 'markdown-it-katex'
import { computed } from 'vue'
const props = defineProps<{ content: string }>()
const md = new MarkdownIt({ html: false, linkify: true, breaks: true }).use(mk)
const html = computed(() => md.render(props.content || ''))
</script>
<template><article class="markdown-body" v-html="html" /></template>
<style scoped>
.markdown-body { color: #eaf4ff; line-height: 1.78; font-size: 14px; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { color: #fff; margin: 18px 0 8px; }
.markdown-body :deep(code) { background: rgba(102,231,255,.12); color: #aef6ff; padding: 2px 6px; border-radius: 6px; }
.markdown-body :deep(pre) { background: rgba(0,0,0,.28); border: 1px solid rgba(255,255,255,.08); border-radius: 14px; padding: 12px; overflow:auto; }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 8px 14px; border-left: 3px solid var(--brand); background: rgba(102,231,255,.08); border-radius: 10px; }
.markdown-body :deep(table) { width:100%; border-collapse: collapse; overflow:hidden; border-radius: 12px; }
.markdown-body :deep(td), .markdown-body :deep(th) { border: 1px solid rgba(255,255,255,.13); padding: 8px; }
.markdown-body :deep(th) { background: rgba(255,255,255,.1); }
</style>
