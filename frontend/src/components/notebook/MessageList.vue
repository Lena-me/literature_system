<script lang="ts">
import StreamProgress from '@/components/notebook/StreamProgress.vue'

export default {
  components: { StreamProgress },
}
</script>

<script setup lang="ts">
import { useNotebookStore } from '@/stores/notebook'
import type { RelatedVisual, Source } from '@/types/domain'
import { visualLabel } from '@/utils/sourceNavigation'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'

const notebook = useNotebookStore()
const emit = defineEmits<{
  sourceClick: [source: Source]
  visualClick: [source: Source, visual: RelatedVisual]
}>()

interface GroupedChunk extends Source {
  ref_index: number   // 原始 sources 数组中的位置 (0-based)
  ref_label: string   // [1], [2] ...
}

interface PaperGroup {
  paper_id: number
  paper_title: string
  chunk_count: number
  chunks: GroupedChunk[]
}

/**
 * ★ 按 paper_id 聚合 sources，消除同论文5个chunk的视觉冗余
 * 同时保留原始 index，确保点击事件链路不断
 */
function groupSourcesByPaper(sources: Source[]): PaperGroup[] {
  if (!sources?.length) return []

  // 构建 paper_id → title 映射
  const paperMap = new Map<number, string>()
  for (const p of notebook.activeSources) {
    paperMap.set(p.id, p.title || p.original_filename || `文献 ${p.id}`)
  }

  // 按 paper_id 分组，保留原始 index
  const groups = new Map<number, GroupedChunk[]>()
  sources.forEach((s, i) => {
    if (!groups.has(s.paper_id)) groups.set(s.paper_id, [])
    const refIndex = (s as GroupedChunk).ref_index ?? i
    const refLabel = (s as GroupedChunk).ref_label ?? `[${i + 1}]`
    groups.get(s.paper_id)!.push({ ...s, ref_index: refIndex, ref_label: refLabel })
  })

  return Array.from(groups.entries()).map(([paper_id, chunks]) => ({
    paper_id,
    paper_title: paperMap.get(paper_id) || `文献 ${paper_id}`,
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

/**
 * 事件委托：捕获 AI 回答中 <sup class="citation-mark"> 的点击
 */
function handleCitationClick(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest('.citation-mark') as HTMLElement | null
  if (!el) return

  const indexStr = el.getAttribute('data-source-index') || ''
  const index = parseInt(indexStr)
  if (isNaN(index)) return

  const msgWrapper = el.closest('[data-message-index]') as HTMLElement | null
  if (!msgWrapper) return

  const msgIndex = parseInt(msgWrapper.getAttribute('data-message-index') || '')
  if (isNaN(msgIndex)) return

  const msg = notebook.activeMessages[msgIndex]
  if (!msg?.sources?.[index]) return

  const source = msg.sources[index]
  console.log(`[citation-click] 角标[${index + 1}] → paper_id=${source.paper_id} | page=${source.page_number} | text="${(source.text || source.snippet || '').slice(0, 60)}..."`)
  emit('sourceClick', source)
}
</script>

<template>
  <div class="message-list" @click="handleCitationClick">

    <!-- ★ 冷启动 -->
    <div v-if="notebook.activeMessages.length === 0" class="empty-state">
      <div class="spark">✦</div>
      <h3>开始你的研究对话</h3>
      <p v-if="notebook.activeSources.length">
        当前挂载了 <b>{{ notebook.activeSources.length }}</b> 篇文献，直接提问即可获得基于文献的精准回答。
      </p>
      <p v-else>还未挂载文献，你可以直接提问（AI 将基于自身知识回答），或者先上传文献。</p>
    </div>

    <!-- ★ 消息列表 -->
    <div
      v-for="(m, i) in notebook.activeMessages"
      :key="i"
      class="message"
      :class="m.role"
      :data-message-index="i"
    >
      <template v-if="m.role === 'user'">
        <div class="bubble user-bubble">
          <p>{{ m.content }}</p>
        </div>
      </template>

      <template v-else>
        <div class="bubble assistant-bubble">
          <StreamProgress v-if="m.streamStage && !m.content" :stage="m.streamStage" />
          <MarkdownRenderer v-if="m.content" :content="m.content" />
        </div>

        <!-- ★ 引用图表：点击跳转 PDF 对应位置；正文 [n] 角标仍可定位文字 -->
        <div v-if="m.sources?.length && countPaperVisuals(m.sources)" class="sources-section">
          <div class="sources-head">
            <span>
              📎 相关图表 — {{ countPaperVisuals(m.sources) }} 张
              · {{ groupSourcesByPaper(m.sources).length }} 篇文献
            </span>
          </div>

          <!-- 父级：文献组 -->
          <div
            v-for="group in groupSourcesByPaper(m.sources).filter(g => collectPaperVisuals(g.chunks).length)"
            :key="group.paper_id"
            class="paper-group"
          >
            <div class="paper-group-header">
              <span class="paper-icon">📄</span>
              <span class="paper-group-title">{{ group.paper_title }}</span>
            </div>

            <div
              v-if="collectPaperVisuals(group.chunks).length"
              class="paper-visuals"
              @click.stop
            >
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
  </div>
</template>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

/* ===== 空状态 ===== */
.empty-state { text-align: center; padding: 60px 24px; max-width: 480px; }
.spark { font-size: 48px; color: var(--academic-primary); margin-bottom: 12px; }
.empty-state h3 { font-size: 18px; color: var(--academic-text-main); margin: 0 0 8px; }
.empty-state p { font-size: 14px; color: var(--academic-text-muted); line-height: 1.65; }
.empty-state b { color: var(--academic-primary); font-weight: 600; }

/* ===== 消息 ===== */
.message { width: 100%; max-width: 800px; margin: 12px 0; display: flex; flex-direction: column; }
.message.user { align-items: flex-end; }
.message.assistant { align-items: flex-start; }

/* ===== 气泡 ===== */
.bubble { max-width: 88%; padding: 14px 18px; border-radius: 16px; line-height: 1.65; }
.user-bubble { background: var(--academic-primary); border-bottom-right-radius: 6px; }
.user-bubble p { margin: 0; color: #fff; white-space: pre-wrap; }
.assistant-bubble { background: var(--academic-canvas); border: 1px solid var(--academic-border); border-bottom-left-radius: 6px; color: var(--academic-text-body); }

/* ===== 聚合引用来源 ===== */
.sources-section { margin-top: 10px; width: 100%; max-width: 800px; }
.sources-head { font-size: 12px; color: var(--academic-text-muted); margin-bottom: 10px; padding-left: 2px; }

/* 父级：文献组容器 */
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

/* 图表画廊 */
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
  background: #f8fafc;
}

.visual-placeholder {
  width: 100%;
  height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f1f5f9;
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

/* ===== 流式指示 ===== */
.typing-indicator {
  display: flex; align-items: center; gap: 8px; padding: 10px 0;
  align-self: flex-start; margin-left: 12px;
  color: var(--academic-text-muted); font-size: 13px;
}
.dots i { font-style: normal; animation: dotBounce 1.2s infinite; font-weight: 700; color: var(--academic-primary); }
.dots i:nth-child(2) { animation-delay: 0.2s; }
.dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes dotBounce { 0%, 80%, 100% { opacity: 0.3; } 40% { opacity: 1; } }
</style>
