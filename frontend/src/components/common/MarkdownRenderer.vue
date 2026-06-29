<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import mk from 'markdown-it-katex'
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

const md = new MarkdownIt({ html: true, linkify: true, breaks: true }).use(mk)

const html = computed(() => {
  let raw = props.content || ''
  // ★ 将 [来源1]、[2] 等引用标记替换为可点击的 sup 角标
  // 先替换 [来源N]，再替换 [N]（避免 [来源1] 被误匹配两次）
  raw = raw.replace(
    /(?<![\w<])\[来源(\d{1,2})\](?![\w>])/g,
    (_match: string, num: string) => {
      const idx = parseInt(num) - 1
      return `<sup class="citation-mark" data-source-index="${idx}">[${num}]</sup>`
    },
  )
  raw = raw.replace(
    /(?<![\w<])\[(\d{1,2})\](?![\w>])/g,
    (_match: string, num: string) => {
      const idx = parseInt(num) - 1
      return `<sup class="citation-mark" data-source-index="${idx}">[${num}]</sup>`
    },
  )
  return md.render(raw)
})
</script>
<template><article class="markdown-body" v-html="html" /></template>
<style scoped>
.markdown-body { color: var(--academic-text-body); line-height: 1.78; font-size: 14px; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { color: var(--academic-text-main); margin: 18px 0 8px; font-weight: 600; }
.markdown-body :deep(code) { background: rgba(37, 99, 235, 0.08); color: var(--academic-primary); padding: 2px 6px; border-radius: 6px; font-size: 13px; }
.markdown-body :deep(pre) { background: var(--academic-canvas); border: 1px solid var(--academic-border); border-radius: 14px; padding: 14px; overflow: auto; }
.markdown-body :deep(pre code) { background: transparent; color: var(--academic-text-body); }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 8px 14px; border-left: 3px solid var(--academic-primary); background: var(--academic-primary-light); border-radius: 0 10px 10px 0; color: var(--academic-text-body); }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 12px; }
.markdown-body :deep(td), .markdown-body :deep(th) { border: 1px solid var(--academic-border); padding: 10px 12px; font-size: 13px; }
.markdown-body :deep(th) { background: var(--academic-canvas); color: var(--academic-text-main); font-weight: 600; }
.markdown-body :deep(a) { color: var(--academic-primary); }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 24px; }
.markdown-body :deep(li) { margin: 4px 0; }
.markdown-body :deep(p) { margin: 8px 0; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid var(--academic-border); margin: 16px 0; }

/* ★ 引用角标样式 */
.markdown-body :deep(.citation-mark) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--academic-primary);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  padding: 1px 5px;
  margin: 0 1px;
  border-radius: 6px;
  background: rgba(37, 99, 235, 0.08);
  transition: all 0.15s;
  vertical-align: super;
  line-height: 1;
  text-decoration: none;
  user-select: none;
}

.markdown-body :deep(.citation-mark:hover) {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.12);
}
</style>
