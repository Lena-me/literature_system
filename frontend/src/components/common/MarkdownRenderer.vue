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

.markdown-body {

  color: #334155;

  line-height: 1.82;

  font-size: 17px;

  letter-spacing: 0.01em;

}



.markdown-body :deep(h1),

.markdown-body :deep(h2),

.markdown-body :deep(h3) {

  color: var(--text-heading);

  font-weight: 600;

  line-height: 1.4;

}



.markdown-body :deep(h1) {

  margin: 0 0 14px;

  font-size: 1.6em;

}



.markdown-body :deep(h2) {

  margin: 32px 0 12px;

  font-size: 1.35em;

}



.markdown-body :deep(h3) {

  margin: 24px 0 10px;

  font-size: 1.12em;

  color: #475569;

}



.markdown-body :deep(code) {

  background: var(--border-lighter);

  color: #0e7490;

  padding: 2px 6px;

  border-radius: 4px;

  font-size: 0.9em;

  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;

  font-weight: 500;

}



.markdown-body :deep(pre) {

  background: var(--bg-canvas);

  border: 1px solid var(--border-light);

  border-radius: var(--radius-md);

  padding: 14px;

  overflow: auto;

}



.markdown-body :deep(pre code) {

  background: transparent;

  color: var(--text-primary);

  padding: 0;

}



.markdown-body :deep(blockquote) {

  margin: 16px 0;

  padding: 12px 16px;

  border-left: 3px solid var(--el-color-primary);

  background: var(--bg-canvas);

  border-radius: 0 8px 8px 0;

  color: var(--text-secondary);

  font-style: normal;

}



.markdown-body :deep(table) {

  width: 100%;

  border-collapse: collapse;

  overflow: hidden;

  border-radius: var(--radius-md);

}



.markdown-body :deep(td),

.markdown-body :deep(th) {

  border: 1px solid var(--border-light);

  padding: 10px 12px;

  font-size: 14px;

}



.markdown-body :deep(th) {

  background: var(--bg-canvas);

  color: var(--text-heading);

  font-weight: 600;

}



.markdown-body :deep(a) {

  color: var(--el-color-primary);

}



.markdown-body :deep(a.scholarly-link),

.markdown-body :deep(a.scholarly-link strong),

.markdown-body :deep(a:has(> strong)) {

  color: var(--el-color-primary);

  font-weight: 600;

  text-decoration: none;

  border-bottom: 1px dashed rgba(37, 99, 235, 0.35);

}



.markdown-body :deep(a.scholarly-link:hover),

.markdown-body :deep(a.scholarly-link:hover strong),

.markdown-body :deep(a:has(> strong):hover) {

  color: var(--el-color-primary-hover);

  border-bottom-color: rgba(37, 99, 235, 0.55);

}



.markdown-body :deep(ul),

.markdown-body :deep(ol) {

  padding-left: 24px;

}



.markdown-body :deep(li) {

  margin: 6px 0;

}



.markdown-body :deep(p) {

  margin: 12px 0;

}



.markdown-body :deep(hr) {

  border: none;

  border-top: 1px solid var(--border-lighter);

  margin: 20px 0;

}



.markdown-body :deep(.formula-display) {

  margin: 12px 0;

  padding: 12px 16px;

  overflow-x: auto;

  text-align: center;

  background: rgba(37, 99, 235, 0.04);

  border-radius: var(--radius-sm);

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



.markdown-body :deep(.citation-mark) {

  display: inline;

  color: var(--el-color-primary);

  font-size: 0.72em;

  font-weight: 600;

  cursor: pointer;

  padding: 0;

  margin: 0 1px;

  border-radius: 0;

  background: transparent;

  transition: color 0.15s, text-decoration-color 0.15s;

  vertical-align: super;

  line-height: 1;

  text-decoration: none;

  user-select: none;

}



.markdown-body :deep(.citation-mark:hover) {

  color: var(--el-color-primary-hover);

  text-decoration: underline;

  text-decoration-color: rgba(37, 99, 235, 0.35);

  text-underline-offset: 2px;

  transform: none;

  box-shadow: none;

}



.markdown-body :deep(.scholarly-link) {

  color: var(--el-color-primary);

  text-decoration: none;

  border-bottom: 1px dashed rgba(37, 99, 235, 0.35);

}



.markdown-body :deep(.scholarly-link:hover) {

  color: var(--el-color-primary-hover);

  border-bottom-color: rgba(37, 99, 235, 0.55);

}

</style>

