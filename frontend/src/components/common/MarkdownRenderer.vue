<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'
import 'katex/dist/katex.min.css'
import { renderChatMarkdownHtml } from '@/utils/mathRender'
import { injectHeadingAnchors } from '@/utils/reportMarkdown'
import { linkifyScholarlyReferences, injectPaperTitleLinks, ensureExternalLinksOpenInNewTab } from '@/utils/paperOfficialUrl'
import type { ExternalReference } from '@/types/domain'

const props = defineProps<{
  content: string
  linkifyReferences?: boolean
  paperLinks?: ExternalReference[]
  headingAnchors?: boolean
}>()

const md = new MarkdownIt({ html: true, linkify: true, breaks: true })

const html = computed(() => {
  let raw = props.content || ''
  if (props.paperLinks?.length) {
    raw = injectPaperTitleLinks(raw, props.paperLinks)
  }

  // 引用角标 [1] / [来源1] — 在公式规范化之前处理，避免与 [ formula ] 冲突
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

  let rendered = renderChatMarkdownHtml(raw, s => md.render(s))
  if (props.headingAnchors) {
    rendered = injectHeadingAnchors(rendered)
  }
  if (props.linkifyReferences !== false) {
    rendered = linkifyScholarlyReferences(rendered)
  }
  rendered = ensureExternalLinksOpenInNewTab(rendered)
  return rendered
})
</script>
<template><article class="markdown-body" v-html="html" /></template>
<style scoped>
.markdown-body { color: var(--academic-text-body); line-height: 1.78; font-size: 16px; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { color: var(--academic-text-main); margin: 18px 0 8px; font-weight: 600; }
.markdown-body :deep(code) { background: rgba(37, 99, 235, 0.08); color: var(--academic-primary); padding: 2px 6px; border-radius: 6px; font-size: 14px; }
.markdown-body :deep(pre) { background: var(--academic-canvas); border: 1px solid var(--academic-border); border-radius: 14px; padding: 14px; overflow: auto; }
.markdown-body :deep(pre code) { background: transparent; color: var(--academic-text-body); }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 8px 14px; border-left: 3px solid var(--academic-primary); background: var(--academic-primary-light); border-radius: 0 10px 10px 0; color: var(--academic-text-body); }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 12px; }
.markdown-body :deep(td), .markdown-body :deep(th) { border: 1px solid var(--academic-border); padding: 10px 12px; font-size: 14px; }
.markdown-body :deep(th) { background: var(--academic-canvas); color: var(--academic-text-main); font-weight: 600; }
.markdown-body :deep(a) { color: var(--academic-primary); }
.markdown-body :deep(a.scholarly-link),
.markdown-body :deep(a.scholarly-link strong),
.markdown-body :deep(a:has(> strong)) {
  color: #2563eb;
  font-weight: 600;
  text-decoration: none;
  border-bottom: 1px dashed rgba(37, 99, 235, 0.35);
}
.markdown-body :deep(a.scholarly-link:hover),
.markdown-body :deep(a.scholarly-link:hover strong),
.markdown-body :deep(a:has(> strong):hover) {
  color: #1d4ed8;
  border-bottom-color: rgba(29, 78, 216, 0.55);
}
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 24px; }
.markdown-body :deep(li) { margin: 4px 0; }
.markdown-body :deep(p) { margin: 8px 0; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid var(--academic-border); margin: 16px 0; }

.markdown-body :deep(.formula-display) {
  margin: 12px 0;
  padding: 12px 16px;
  overflow-x: auto;
  text-align: center;
  background: rgba(37, 99, 235, 0.03);
  border-radius: 10px;
}

.markdown-body :deep(.katex-display) {
  margin: 0.6em 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.markdown-body :deep(.katex) {
  font-size: 1.05em;
}

.markdown-body :deep(.math-inline) {
  display: inline-block;
  vertical-align: middle;
  margin: 0 1px;
}

.markdown-body :deep(strong .math-inline) {
  font-weight: 700;
}

.markdown-body :deep(li .math-inline) {
  vertical-align: middle;
}

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

.markdown-body :deep(.scholarly-link) {
  color: #2563eb;
  text-decoration: none;
  border-bottom: 1px dashed rgba(37, 99, 235, 0.35);
}

.markdown-body :deep(.scholarly-link:hover) {
  color: #1d4ed8;
  border-bottom-color: rgba(29, 78, 216, 0.55);
}
</style>
