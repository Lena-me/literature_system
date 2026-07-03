<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useNotebookStore } from '@/stores/notebook'
import { qaApi } from '@/api/qa'

const notebook = useNotebookStore()
const questions = ref<string[]>([])
const loading = ref(false)

// 当会话切换或文献变化时，重新获取推荐问题
watch(
  () => [notebook.activeSessionId, notebook.activeSources.map(p => p.id).join(',')] as const,
  async ([sessionId, sourceKey]) => {
    if (!sessionId || !sourceKey) {
      questions.value = []
      return
    }
    await fetchQuestions()
  },
  { immediate: true },
)

async function fetchQuestions() {
  if (!notebook.activeSessionId || notebook.activeSources.length === 0) return
  loading.value = true
  try {
    const res = await qaApi.suggestedQuestions(notebook.activeSessionId)
    questions.value = res.questions || []
  } catch {
    questions.value = []
  } finally {
    loading.value = false
  }
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
      <span class="sq-spark">💡</span>
      <span>基于挂载文献，推荐以下探索性问题：</span>
    </div>
    <div class="sq-list">
      <div v-if="loading" class="sq-loading">生成推荐问题中...</div>
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
  padding: 18px 24px 10px;
  max-width: 780px;
  margin: 0 auto;
  width: 100%;
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
