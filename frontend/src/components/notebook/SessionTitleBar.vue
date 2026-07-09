<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useNotebookStore } from '@/stores/notebook'

const notebook = useNotebookStore()
const isEditing = ref(false)
const editTitle = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

const displayTitle = computed(() => {
  const id = notebook.activeSessionId
  if (!id) return '未命名会话'
  return (
    notebook.activeSessionDetail?.title
    || notebook.sessions.find(s => s.id === id)?.title
    || '新会话'
  )
})

watch(
  () => notebook.activeSessionId,
  () => {
    isEditing.value = false
  },
)

function startEdit() {
  if (!notebook.activeSessionId) return
  editTitle.value = displayTitle.value
  isEditing.value = true
  nextTick(() => {
    inputRef.value?.focus()
    inputRef.value?.select()
  })
}

async function finishEdit() {
  const id = notebook.activeSessionId
  if (!id || !isEditing.value) return
  isEditing.value = false
  const trimmed = editTitle.value.trim()
  if (trimmed && trimmed !== displayTitle.value) {
    await notebook.renameSession(id, trimmed)
  }
}

function cancelEdit() {
  isEditing.value = false
}
</script>

<template>
  <div v-if="notebook.activeSessionId" class="session-title-bar">
    <div v-if="isEditing" class="edit-wrap" @click.stop>
      <input
        ref="inputRef"
        v-model="editTitle"
        class="title-input"
        placeholder="输入会话标题"
        @keyup.enter="finishEdit"
        @keyup.escape="cancelEdit"
        @blur="finishEdit"
      />
    </div>
    <button
      v-else
      type="button"
      class="title-display"
      title="点击编辑标题"
      @click="startEdit"
    >
      {{ displayTitle }}
    </button>
  </div>
</template>

<style scoped>
.session-title-bar {
  flex: 1;
  min-width: 0;
}

.title-display {
  display: block;
  max-width: 100%;
  padding: 2px 6px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--academic-text-main);
  font-size: 15px;
  font-weight: 600;
  text-align: left;
  cursor: text;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: border-color 0.15s, background 0.15s;
}

.title-display:hover {
  border-color: rgba(148, 163, 184, 0.35);
  background: rgba(255, 255, 255, 0.5);
}

.edit-wrap {
  max-width: 420px;
}

.title-input {
  width: 100%;
  max-width: 420px;
  padding: 6px 10px;
  border: 1px solid rgba(37, 99, 235, 0.45);
  border-radius: 8px;
  background: var(--academic-panel);
  color: var(--academic-text-main);
  font-size: 15px;
  font-weight: 600;
  text-align: left;
  outline: none;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.title-input:focus {
  border-color: var(--academic-primary);
}
</style>
