<script lang="ts">
import StreamProgress from '@/components/notebook/StreamProgress.vue'
import ThinkingBlock from '@/components/notebook/ThinkingBlock.vue'
import ToolArtifacts from '@/components/notebook/ToolArtifacts.vue'
import CitationMenu from '@/components/notebook/CitationMenu.vue'

export default {
  components: { StreamProgress, ThinkingBlock, ToolArtifacts, CitationMenu },
}
</script>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useNotebookStore } from '@/stores/notebook'
import type { ChatMessage, RelatedVisual, Source } from '@/types/domain'
import { visualLabel } from '@/utils/sourceNavigation'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import { officialLinkLabel, resolveOfficialPaperUrl } from '@/utils/paperOfficialUrl'

const notebook = useNotebookStore()
const emit = defineEmits<{
  sourceClick: [source: Source]
  visualClick: [source: Source, visual: RelatedVisual]
}>()

const listRef = ref<HTMLElement | null>(null)
const stickToBottom = ref(true)
const bottomAnchor = ref<HTMLElement | null>(null)
const citationMenu = ref<{ source: Source; anchor: { x: number; y: number } } | null>(null)

interface GroupedChunk extends Source {
  ref_index: number
  ref_label: string
}

interface PaperGroup {
  paper_id: number
  paper_title: string
  official_url: string | null
  chunk_count: number
  chunks: GroupedChunk[]
}

function groupSourcesByPaper(sources: Source[]): PaperGroup[] {
  if (!sources?.length) return []

  const paperMap = new Map<number, string>()
  for (const p of notebook.activeSources) {
    paperMap.set(p.id, p.title || p.original_filename || `文献 ${p.id}`)
  }

  const groups = new Map<number, GroupedChunk[]>()
  sources.forEach((s, i) => {
    if (!groups.has(s.paper_id)) groups.set(s.paper_id, [])
    const refIndex = (s as GroupedChunk).ref_index ?? i
    const refLabel = (s as GroupedChunk).ref_label ?? `[${i + 1}]`
    groups.get(s.paper_id)!.push({ ...s, ref_index: refIndex, ref_label: refLabel })
  })

  return Array.from(groups.entries()).map(([paper_id, chunks]) => ({
    paper_id,
    paper_title: chunks[0]?.paper_title || paperMap.get(paper_id) || `文献 ${paper_id}`,
    official_url: resolveOfficialPaperUrl({
      doi: chunks[0]?.doi,
      official_url: chunks[0]?.official_url,
    }),
    chunk_count: chunks.length,
    chunks,
  }))
}

function collectPaperVisuals(chunks: GroupedChunk[]): RelatedVisual[] {
  const seen = new Set<number>()
  const visuals: RelatedVisual[] = []
  for (const chunk of chunks) {
    for (const v of chunk.related_figures ?? []) {
      if (seen.has(v.id)) continue
      seen.add(v.id)
      visuals.push(v)
    }
  }
  return visuals
}

function countPaperVisuals(sources: Source[]): number {
  const seen = new Set<number>()
  for (const s of sources) {
    for (const v of s.related_figures ?? []) {
      seen.add(v.id)
    }
  }
  return seen.size
}

function onListScroll() {
  const el = listRef.value
  if (!el) return
  stickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 100
}

async function scrollToBottom(force = false) {
  if (!force && !stickToBottom.value) return
  await nextTick()
  bottomAnchor.value?.scrollIntoView({
    behavior: notebook.isStreaming ? 'auto' : 'smooth',
    block: 'end',
  })
}

async function scrollToLatestExchange(force = true) {
  stickToBottom.value = true
  await nextTick()
  const msgs = notebook.activeMessages
  if (!msgs.length) return

  let targetIdx = msgs.length - 1
  for (let i = msgs.length - 1; i >= 0; i -= 1) {
    if (msgs[i].role === 'user') {
      targetIdx = i
      break
    }
  }

  const el = listRef.value?.querySelector(`[data-message-index="${targetIdx}"]`)
  if (el) {
    el.scrollIntoView({
      behavior: force ? 'auto' : 'smooth',
      block: 'start',
    })
    return
  }
  await scrollToBottom(force)
}

function scrollToLatest(force = true) {
  stickToBottom.value = true
  scrollToBottom(force)
}

function isLastAssistant(index: number, m: ChatMessage) {
  if (m.role !== 'assistant') return false
  for (let i = notebook.activeMessages.length - 1; i >= 0; i--) {
    if (notebook.activeMessages[i].role === 'assistant') return i === index
  }
  return false
}

/** 流式生成期间不展示工具卡片，避免插入 DOM 导致正文抖动 */
function shouldShowArtifacts(m: ChatMessage, index: number) {
  if (!m.artifacts?.length) return false
  if (!notebook.isStreaming) return true
  return !isLastAssistant(index, m)
}

function canEditUser(m: ChatMessage, index: number) {
  return m.role === 'user' && m.id && index === notebook.activeMessages.length - 2 && !notebook.isStreaming
}

watch(
  () => notebook.scrollTick,
  async () => {
    if (notebook.scrollForce) {
      if (notebook.isStreaming) {
        await scrollToBottom(true)
      } else {
        await scrollToLatestExchange(true)
      }
    } else {
      await scrollToBottom(false)
    }
  },
)

watch(
  () => notebook.activeSessionId,
  () => {
    stickToBottom.value = true
    scrollToLatest(true)
  },
)

onMounted(() => scrollToLatest(false))

function handleCitationClick(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest('.citation-mark') as HTMLElement | null
  if (!el) return

  e.preventDefault()
  e.stopPropagation()

  const indexStr = el.getAttribute('data-source-index') || ''
  const index = parseInt(indexStr)
  if (isNaN(index)) return

  const msgWrapper = el.closest('[data-message-index]') as HTMLElement | null
  if (!msgWrapper) return

  const msgIndex = parseInt(msgWrapper.getAttribute('data-message-index') || '')
  if (isNaN(msgIndex)) return

  const msg = notebook.activeMessages[msgIndex]
  const source = msg?.sources?.[index]
  if (!source) return

  const rect = el.getBoundingClientRect()
  citationMenu.value = {
    source,
    anchor: { x: rect.left + rect.width / 2, y: rect.bottom },
  }
}

function openOfficialUrl(url: string | null | undefined) {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

function updateReasoningExpanded(index: number, expanded: boolean) {
  const m = notebook.activeMessages[index]
  if (!m) return
  notebook.activeMessages[index] = { ...m, reasoningExpanded: expanded }
}
</script>

<template>
  <div ref="listRef" class="message-list" @scroll="onListScroll" @click="handleCitationClick">
    <div v-if="notebook.activeMessages.length === 0" class="empty-state">
      <div class="spark">✦</div>
      <h3>开始你的研究对话</h3>
      <p v-if="notebook.activeSources.length">
        当前挂载了 <b>{{ notebook.activeSources.length }}</b> 篇文献，直接提问即可获得基于文献的精准回答。
      </p>
      <p v-else>还未挂载文献，你可以直接提问（AI 将基于自身知识回答），或者先上传文献。</p>
    </div>

    <div
      v-for="(m, i) in notebook.activeMessages"
      :key="m.id ?? `local-${i}`"
      class="message"
      :class="m.role"
      :data-message-index="i"
    >
      <template v-if="m.role === 'user'">
        <div class="bubble user-bubble">
          <p>{{ m.content }}</p>
        </div>
        <div v-if="canEditUser(m, i)" class="msg-actions">
          <button type="button" @click="notebook.startEditMessage(m.id!, m.content)">编辑</button>
        </div>
      </template>

      <template v-else>
        <div class="bubble assistant-bubble">
          <StreamProgress
            v-if="m.streamStage && notebook.isStreaming && isLastAssistant(i, m)"
            :stage="m.streamStage"
            :flow="m.streamFlow"
          />
          <ThinkingBlock
            v-if="(m.reasoning || '').trim()"
            :reasoning="m.reasoning"
            :expanded="m.reasoningExpanded ?? false"
            :streaming="notebook.isStreaming && isLastAssistant(i, m) && !(m.content || '').trim()"
            @update:expanded="updateReasoningExpanded(i, $event)"
          />
          <MarkdownRenderer
            v-if="m.content"
            :content="m.content"
            :paper-links="m.external_refs"
          />
          <p
            v-else-if="!notebook.isStreaming || !isLastAssistant(i, m)"
            class="assistant-empty-hint"
          >
            （暂无回答内容，请点击下方重新生成）
          </p>
        </div>

        <ToolArtifacts v-if="shouldShowArtifacts(m, i)" :artifacts="m.artifacts!" />

        <div v-if="isLastAssistant(i, m) && !notebook.isStreaming" class="msg-actions">
          <button
            type="button"
            class="regenerate-btn"
            :title="m.cancelled ? '继续生成' : '重新生成'"
            @click="notebook.regenerateLastResponse()"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
          </button>
        </div>

        <div v-if="m.sources?.length && countPaperVisuals(m.sources)" class="sources-section">
          <div class="sources-head">
            <span>
              📎 相关图表 — {{ countPaperVisuals(m.sources) }} 张
              · {{ groupSourcesByPaper(m.sources).length }} 篇文献
            </span>
          </div>

          <div
            v-for="group in groupSourcesByPaper(m.sources).filter(g => collectPaperVisuals(g.chunks).length)"
            :key="group.paper_id"
            class="paper-group"
          >
            <div class="paper-group-header">
              <span class="paper-icon">📄</span>
              <button
                v-if="group.official_url"
                type="button"
                class="paper-group-title link"
                :title="officialLinkLabel(group.official_url)"
                @click.stop="openOfficialUrl(group.official_url)"
              >
                {{ group.paper_title }}
              </button>
              <span v-else class="paper-group-title">{{ group.paper_title }}</span>
            </div>

            <div v-if="collectPaperVisuals(group.chunks).length" class="paper-visuals" @click.stop>
              <button
                v-for="visual in collectPaperVisuals(group.chunks)"
                :key="visual.id"
                type="button"
                class="visual-card"
                :title="visual.caption || ''"
                @click="emit('visualClick', { paper_id: group.paper_id }, visual)"
              >
                <img
                  v-if="visual.image_path"
                  :src="visual.image_path"
                  :alt="visual.caption || 'figure'"
                  class="visual-image"
                />
                <div v-else class="visual-placeholder">{{ visual.type === 'table' ? '表' : '图' }}</div>
                <span class="visual-caption">{{ visualLabel(visual) }}</span>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <div ref="bottomAnchor" class="scroll-anchor" />

    <CitationMenu
      v-if="citationMenu"
      :source="citationMenu.source"
      :anchor="citationMenu.anchor"
      @close="citationMenu = null"
      @open-library="emit('sourceClick', $event)"
    />
  </div>
</template>

<style scoped>
.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px var(--notebook-content-gutter, 16px) 32px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}

.scroll-anchor {
  width: 100%;
  height: 1px;
  flex-shrink: 0;
}

.empty-state {
  text-align: center;
  padding: 60px 24px;
  max-width: var(--notebook-content-max-width, 860px);
  width: 100%;
  margin: 0 auto;
}
.spark { font-size: 48px; color: var(--academic-primary); margin-bottom: 12px; }
.empty-state h3 { font-size: 18px; color: var(--academic-text-main); margin: 0 0 8px; }
.empty-state p { font-size: 14px; color: var(--academic-text-muted); line-height: 1.65; }
.empty-state b { color: var(--academic-primary); font-weight: 600; }

/* ========================================
   对话气泡重构 (MessageList.vue)
   ======================================== */
.message {
  width: 100%;
  max-width: var(--notebook-content-max-width, 860px);
  margin: 16px auto;
  display: flex;
  flex-direction: column;
}
.message.user { align-items: flex-end; }
.message.assistant { align-items: flex-start; }

.bubble {
  padding: 14px 20px;
  line-height: 1.75;
  font-size: 15px;
  box-shadow: var(--shadow-sm);
}

.user-bubble {
  max-width: 75%;
  background: var(--el-color-primary-light);
  border: 1px solid rgba(59, 130, 246, 0.35);
  border-radius: 20px 20px 4px 20px;
}

.user-bubble p {
  margin: 0;
  color: var(--text-primary);
  font-weight: 500;
  white-space: pre-wrap;
}

.assistant-bubble {
  width: 100%;
  max-width: 100%;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  border-radius: 4px 20px 20px 20px;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.7;
}

.assistant-bubble :deep(.markdown-body) {
  font-size: 14px;
  line-height: 1.7;
}

.assistant-empty-hint {
  margin: 0;
  padding: 4px 0;
  font-size: 13px;
  color: var(--academic-text-muted);
  line-height: 1.5;
}

.msg-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  padding-left: 4px;
}

.message.user .msg-actions {
  padding-right: 4px;
  padding-left: 0;
}

.msg-actions button {
  padding: 2px 8px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 12px;
  cursor: pointer;
}

.regenerate-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--text-tertiary);
  line-height: 0;
  transition: color 0.15s;
}

.regenerate-btn:hover {
  color: var(--el-color-primary);
}

.msg-actions button:hover {
  color: var(--academic-primary);
}

.sources-section { margin-top: 10px; width: 100%; }
.sources-head { font-size: 12px; color: var(--academic-text-muted); margin-bottom: 10px; padding-left: 2px; }

.paper-group {
  background: var(--academic-canvas);
  border: 1px solid var(--academic-border);
  border-radius: 10px;
  padding: 10px 12px 6px;
  margin-bottom: 8px;
}

.paper-group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--academic-border);
}

.paper-icon { font-size: 13px; flex-shrink: 0; }

.paper-group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--academic-text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.paper-group-title.link {
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
  text-align: left;
  color: #7c3aed;
}

.paper-group-title.link:hover {
  text-decoration: underline;
}

.paper-visuals {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 4px 0 8px;
}

.visual-card {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: 140px;
  padding: 0;
  border: 1px solid var(--academic-border);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.visual-card:hover {
  border-color: rgba(37, 99, 235, 0.4);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.08);
}

.visual-image {
  width: 100%;
  height: 96px;
  object-fit: cover;
  background: var(--bg-canvas);
}

.visual-placeholder {
  width: 100%;
  height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--border-lighter);
  color: var(--academic-text-muted);
  font-size: 24px;
  font-weight: 600;
}

.visual-caption {
  font-size: 11px;
  color: var(--academic-text-muted);
  padding: 6px 8px;
  line-height: 1.35;
  text-align: left;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
