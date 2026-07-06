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
  margin-bottom: 12px;
  border-radius: 10px;
  border: 1px dashed var(--academic-border);
  background: #f8fafc;
  overflow: hidden;
}

.thinking-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.thinking-summary::-webkit-details-marker {
  display: none;
}

.thinking-label {
  font-size: 14px;
  font-weight: 600;
  color: #64748b;
}

.thinking-meta {
  font-size: 12px;
  color: #94a3b8;
}

.thinking-body {
  padding: 0 12px 12px;
  font-size: 15px;
  line-height: 1.65;
  color: #64748b;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}
</style>
