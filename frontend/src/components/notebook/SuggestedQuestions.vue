<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useNotebookStore } from '@/stores/notebook'
import { qaApi } from '@/api/qa'

const notebook = useNotebookStore()
const questions = ref<string[]>([])
const loading = ref(false)

/** 仅随会话 / 挂载文献 ID 变化，不受解析状态轮询影响 */
const suggestFetchKey = computed(() => {
  if (!notebook.activeSessionId || notebook.activeMessages.length > 0) return ''
  const paperIds = notebook.activeSources
    .map(p => p.id)
    .filter(id => Number.isFinite(id))
    .sort((a, b) => a - b)
    .join(',')
  if (!paperIds) return ''
  return `${notebook.activeSessionId}:${paperIds}`
})

let lastFetchedKey = ''
let fetchPromise: Promise<void> | null = null

watch(
  suggestFetchKey,
  async key => {
    if (!key) {
      questions.value = []
      lastFetchedKey = ''
      return
    }
    if (key === lastFetchedKey && questions.value.length > 0) return
    await fetchQuestions(key)
  },
  { immediate: true },
)

async function fetchQuestions(key: string) {
  if (!notebook.activeSessionId || notebook.activeSources.length === 0) return
  if (fetchPromise && lastFetchedKey === key) return fetchPromise

  loading.value = true
  lastFetchedKey = key
  fetchPromise = (async () => {
    try {
      const res = await qaApi.suggestedQuestions(notebook.activeSessionId!)
      if (suggestFetchKey.value !== key) return
      questions.value = res.questions || []
    } catch {
      if (suggestFetchKey.value === key) {
        questions.value = []
        lastFetchedKey = ''
      }
    } finally {
      if (suggestFetchKey.value === key) {
        loading.value = false
      }
      fetchPromise = null
    }
  })()

  return fetchPromise
}

// 只有会话刚开始且无消息时显示
const shouldShow = computed(() => {
  return (
    notebook.activeMessages.length === 0 &&
    notebook.activeSources.length > 0 &&
    (questions.value.length > 0 || loading.value)
  )
})

function askQuestion(q: string) {
  notebook.sendMessage(q)
}
</script>

<template>
  <div v-if="shouldShow" class="suggested-questions">
    <div class="sq-header">
      <span>基于挂载文献，推荐以下探索性问题：</span>
    </div>
    <div class="sq-list">
      <div v-if="loading && !questions.length" class="sq-loading">生成推荐问题中...</div>
      <button
        v-for="(q, i) in questions"
        :key="i"
        class="sq-btn"
        @click="askQuestion(q)"
      >
        {{ q }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.suggested-questions {
  padding: 0 var(--notebook-content-gutter, 16px) 10px;
  max-width: var(--notebook-content-max-width, 860px);
  margin: 0 auto;
  width: calc(100% - 2 * var(--notebook-content-gutter, 16px));
}

.sq-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--academic-text-muted);
  margin-bottom: 10px;
}

.sq-spark {
  font-size: 16px;
}

.sq-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sq-btn {
  display: block;
  width: 100%;
  text-align: left;
  padding: 12px 16px;
  border-radius: 14px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  line-height: var(--line-academic);
  box-shadow: var(--shadow-soft);
}

.sq-btn:hover {
  background: var(--academic-primary-light);
  border-color: var(--academic-primary);
  color: var(--academic-primary);
  transform: translateX(4px);
}

.sq-loading {
  padding: 12px 16px;
  color: var(--academic-text-muted);
  font-size: 13px;
}
</style>

