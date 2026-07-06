<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { QAToolArtifact } from '@/types/domain'

defineProps<{ artifacts: QAToolArtifact[] }>()

const router = useRouter()

function openArtifact(item: QAToolArtifact) {
  if (item.artifact_type === 'report') {
    if (item.report_id) {
      router.push({ path: '/reports', query: { id: String(item.report_id) } })
    } else {
      router.push('/reports')
    }
    return
  }
  if (item.artifact_type === 'graph' && item.graph_id) {
    router.push({ path: '/graph', query: { id: String(item.graph_id) } })
    return
  }
  if (item.artifact_type === 'comparison') {
    if (item.comparison_id) {
      router.push({ path: '/compare', query: { id: String(item.comparison_id) } })
    } else {
      router.push('/compare')
    }
  }
}

function label(item: QAToolArtifact): string {
  if (item.artifact_type === 'report') {
    return item.title || `研读报告 #${item.report_id ?? ''}`
  }
  if (item.artifact_type === 'graph') {
    return item.name || `知识图谱 #${item.graph_id ?? ''}`
  }
  return item.name || `文献对比 #${item.comparison_id ?? ''}`
}

function hint(item: QAToolArtifact): string {
  if (item.artifact_type === 'report') return '已生成报告，点击查看'
  if (item.artifact_type === 'graph') return '已构建图谱，点击查看可视化'
  return '对比结果已保存，点击查看'
}

function icon(item: QAToolArtifact): string {
  if (item.artifact_type === 'report') return '📋'
  if (item.artifact_type === 'graph') return '🕸️'
  return '⚖️'
}
</script>

<template>
  <div v-if="artifacts.length" class="tool-artifacts">
    <div class="tool-artifacts-head">工具产物</div>
    <button
      v-for="(item, idx) in artifacts"
      :key="`${item.artifact_type}-${item.report_id ?? item.graph_id ?? item.comparison_id ?? idx}`"
      type="button"
      class="artifact-card"
      @click="openArtifact(item)"
    >
      <span class="artifact-icon">{{ icon(item) }}</span>
      <span class="artifact-body">
        <span class="artifact-title">{{ label(item) }}</span>
        <span class="artifact-hint">{{ hint(item) }}</span>
      </span>
      <span class="artifact-arrow">→</span>
    </button>
  </div>
</template>

<style scoped>
.tool-artifacts {
  margin-top: 12px;
  width: 100%;
  max-width: 800px;
}

.tool-artifacts-head {
  font-size: 12px;
  color: var(--academic-text-muted);
  margin-bottom: 8px;
}

.artifact-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  margin-bottom: 8px;
  border-radius: 12px;
  border: 1px solid rgba(124, 58, 237, 0.25);
  background: linear-gradient(135deg, rgba(124, 58, 237, 0.06), rgba(99, 102, 241, 0.04));
  cursor: pointer;
  text-align: left;
  transition: all 0.18s ease;
}

.artifact-card:hover {
  border-color: rgba(124, 58, 237, 0.45);
  transform: translateX(3px);
}

.artifact-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.artifact-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.artifact-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--academic-text-body);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-hint {
  font-size: 12px;
  color: var(--academic-text-muted);
}

.artifact-arrow {
  color: #7c3aed;
  font-size: 16px;
}
</style>
