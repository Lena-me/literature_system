<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  reasoning?: string
  expanded?: boolean
  streaming?: boolean
}>()

const emit = defineEmits<{ 'update:expanded': [value: boolean] }>()

const open = ref(props.expanded ?? false)

watch(
  () => props.expanded,
  (val) => {
    if (val !== undefined) open.value = val
  },
)

function onToggle(e: Event) {
  const el = e.target as HTMLDetailsElement
  open.value = el.open
  emit('update:expanded', el.open)
}

const charCount = computed(() => (props.reasoning || '').length)
</script>

<template>
  <details v-if="reasoning?.trim()" :open="open" class="thinking-block" @toggle="onToggle">
    <summary class="thinking-summary">
      <span class="thinking-label">
        {{ streaming ? '正在思考…' : '思考过程' }}
      </span>
      <span class="thinking-meta">{{ charCount }} 字 · 点击{{ open ? '收起' : '展开' }}</span>
    </summary>
    <div class="thinking-body">{{ reasoning }}</div>
  </details>
</template>

<style scoped>
.thinking-block {
  margin-bottom: 16px;
  border-radius: 8px;
  border: none;
  background: var(--bg-canvas);
  border-left: 3px solid var(--border-light);
  transition: all 0.2s ease;
  overflow: hidden;
}

.thinking-block[open] {
  border-left-color: var(--el-color-primary-light-3);
  background: #ffffff;
  box-shadow: var(--shadow-sm);
}

.thinking-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.thinking-summary::-webkit-details-marker {
  display: none;
}

.thinking-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.thinking-meta {
  font-size: 12px;
  color: var(--text-tertiary);
  opacity: 0.6;
}

.thinking-body {
  padding: 0 14px 14px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
  border-top: 1px solid transparent;
}
</style>
