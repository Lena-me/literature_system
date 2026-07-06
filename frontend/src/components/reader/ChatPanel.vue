<script lang="ts">
import StreamProgress from '@/components/notebook/StreamProgress.vue'
import ThinkingBlock from '@/components/notebook/ThinkingBlock.vue'

export default {
  components: { StreamProgress, ThinkingBlock },
}
</script>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { qaApi } from '@/api/qa'
import type { ChatMessage, Source, StreamFlow, StreamStage } from '@/types/domain'
import { inferStreamFlow } from '@/utils/streamStages'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
const props = defineProps<{ selectedIds: number[] }>()
const emit = defineEmits<{ report: []; graph: []; compare: []; guide: []; sourceClick: [source: Source] }>()
const question = ref('')
const messages = ref<ChatMessage[]>([])
const loading = ref(false)
const sessionId = ref<number | undefined>()
const box = ref<HTMLElement | null>(null)
async function ask(q?: string) {
  const text = (q || question.value).trim()
  if (!text || loading.value) return
  question.value = ''
  messages.value.push({ role: 'user', content: text })
  loading.value = true
  try {
    const assistantIndex = messages.value.length
    messages.value.push({ role: 'assistant', content: '', reasoning: '', sources: [], streamStage: 'classifying', streamFlow: undefined, reasoningExpanded: true })

    const patchAssistant = (patch: Partial<ChatMessage>) => {
      const current = messages.value[assistantIndex]
      if (!current || current.role !== 'assistant') return
      messages.value[assistantIndex] = { ...current, ...patch }
    }

    let receivedDone = false
    let streamInterrupted = false

    const streamResult = await qaApi.askStream({ question: text, paper_ids: props.selectedIds, session_id: sessionId.value }, async (event) => {
      if (event.type === 'session') sessionId.value = event.session_id
      if (event.type === 'sources') patchAssistant({ sources: event.sources })
      if (event.type === 'status' && event.stage) {
        const current = messages.value[assistantIndex]
        const stage = event.stage as StreamStage
        const streamFlow = inferStreamFlow(stage, current?.streamFlow)
        patchAssistant({ streamStage: stage, streamFlow })
      }
      if (event.type === 'delta' && event.content) {
        const current = messages.value[assistantIndex]
        const channel = event.channel || 'content'
        if (channel === 'reasoning') {
          patchAssistant({
            reasoning: (current?.reasoning || '') + event.content,
            reasoningExpanded: true,
          })
        } else {
          patchAssistant({
            content: (current?.content || '') + event.content,
            reasoningExpanded: (current?.reasoning || '').trim() ? false : (current?.reasoningExpanded ?? false),
          })
        }
      }
      if (event.type === 'done') {
        receivedDone = true
        const current = messages.value[assistantIndex]
        patchAssistant({
          streamStage: undefined,
          streamFlow: undefined,
          reasoningExpanded: false,
          id: event.message_id ?? current?.id,
          content: event.answer || current?.content || '',
          reasoning: event.reasoning ?? current?.reasoning ?? '',
          external_refs: event.external_refs?.length ? event.external_refs : current?.external_refs,
        })
      }
      if (event.type === 'stream_interrupted') {
        streamInterrupted = true
        patchAssistant({ streamStage: undefined, streamFlow: undefined, reasoningExpanded: false })
      }
      if (event.type === 'error') {
        patchAssistant({
          streamStage: undefined,
          content: `❌ 对话失败：${event.error}`,
        })
      }
      await nextTick(); box.value?.scrollTo({ top: box.value.scrollHeight, behavior: 'smooth' })
    })
    receivedDone = receivedDone || streamResult.receivedDone

    if (!receivedDone && streamInterrupted && sessionId.value) {
      try {
        const msgs = await qaApi.messages(sessionId.value, 100)
        if (msgs.length) messages.value = msgs
      } catch {
        // ignore
      }
    }
  } finally { loading.value = false }
}
defineExpose({ ask })
</script>
<template>
  <section class="chat glass">
    <div class="chat-head">
      <div><b>RAG 智能研读助手</b><span>已选择 {{ selectedIds.length }} 篇文献</span></div>
      <el-tag effect="dark">检索 → 重排 → 增强生成</el-tag>
    </div>
    <div class="quick-actions">
      <el-button @click="emit('report')" :disabled="selectedIds.length!==1">研读报告</el-button>
      <el-button @click="emit('graph')" :disabled="!selectedIds.length">知识图谱</el-button>
      <el-button @click="emit('compare')" :disabled="selectedIds.length<2">多文献对比</el-button>
      <el-button @click="emit('guide')" :disabled="selectedIds.length!==1">实验复现</el-button>
    </div>
    <div ref="box" class="messages slim-scroll">
      <div v-if="!messages.length" class="welcome">
        <div class="spark">✦</div>
        <h3>上传文献后，可以直接问研究问题、方法路线、数据集、实验结论或局限性。</h3>
        <p>答案会附带文献片段来源，方便回溯核验。</p>
      </div>
      <div v-for="(m,i) in messages" :key="i" class="msg" :class="m.role">
        <div class="bubble">
          <StreamProgress v-if="m.role === 'assistant' && m.streamStage && loading && i === messages.length - 1" :stage="m.streamStage" :flow="m.streamFlow" />
          <ThinkingBlock
            v-if="m.role === 'assistant' && (m.reasoning || '').trim()"
            :reasoning="m.reasoning"
            :expanded="m.reasoningExpanded ?? false"
            :streaming="loading && i === messages.length - 1 && !(m.content || '').trim()"
          />
          <MarkdownRenderer
            v-if="m.content"
            :content="m.content"
            :paper-links="m.external_refs"
          />
        </div>
        <div v-if="m.sources?.length" class="sources">
          <el-tag v-for="(s,idx) in m.sources.slice(0,4)" :key="idx" round class="source-tag" @click="emit('sourceClick', s)">paper {{ s.paper_id }} · p.{{ s.page_number || '-' }}</el-tag>
        </div>
      </div>
      <div v-if="loading" class="typing"><span /><span /><span /></div>
    </div>
    <div class="composer">
      <el-input v-model="question" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="请输入你的科研问题，例如：这篇论文的创新点是什么？实验是否容易复现？" @keydown.enter.exact.prevent="ask()" />
      <el-button class="is-glow" :loading="loading" @click="ask">发送</el-button>
    </div>
  </section>
</template>
<style scoped>
.chat { display:flex; flex-direction:column; border-radius: 28px; min-height: 0; height: 100%; overflow:hidden; }
.chat-head { padding: 18px 20px; border-bottom:1px solid rgba(255,255,255,.1); display:flex; justify-content:space-between; align-items:center; }
.chat-head b { display:block; font-size:17px; } .chat-head span { display:block; font-size:12px; color: var(--muted); margin-top:3px; }
.quick-actions { display:flex; gap:8px; flex-wrap:wrap; padding: 12px 16px; border-bottom:1px solid rgba(255,255,255,.08); }
.messages { flex:1; overflow:auto; padding: 20px; }
.welcome { text-align:center; padding:60px 24px; color:rgba(238,246,255,.72); }
.spark { font-size:48px; color: var(--brand); text-shadow:0 0 22px var(--brand); }
.msg { margin: 16px 0; display:flex; flex-direction:column; }
.msg.user { align-items:flex-end; }
.bubble { max-width: 82%; padding: 13px 16px; border-radius: 18px; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.1); }
.msg.user .bubble { background: linear-gradient(135deg, rgba(102,231,255,.32), rgba(138,124,255,.28)); }
.sources { margin-top:8px; display:flex; gap:6px; flex-wrap:wrap; }.source-tag{cursor:pointer;transition:.2s}.source-tag:hover{transform:translateY(-1px);box-shadow:0 0 16px rgba(102,231,255,.35)}
.composer { padding: 14px; display:flex; gap:10px; border-top:1px solid rgba(255,255,255,.1); align-items:flex-end; }
.typing span { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--brand); margin-right:6px; animation:pulseGlow 1s infinite; }
.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
</style>
