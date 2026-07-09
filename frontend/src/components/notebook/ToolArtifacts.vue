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
/* ========================================
   附件卡片重构 (ToolArtifacts.vue)
   ======================================== */
.tool-artifacts {
  margin-top: 16px;
  width: 100%;
}

.tool-artifacts-head {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 8px;
  text-transform: uppercase;
}

.artifact-card {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 12px 16px;
  margin-bottom: 8px;
  border-radius: 12px;
  background: var(--bg-canvas);
  border: 1px solid var(--border-light);
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
}

.artifact-card:hover {
  background: var(--bg-surface);
  border-color: rgba(196, 154, 108, 0.4);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.artifact-icon {
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: #ffffff;
  border-radius: 10px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
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
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.artifact-arrow {
  color: var(--text-tertiary);
  font-size: 16px;
  transition: color 0.2s, transform 0.2s;
}

.artifact-card:hover .artifact-arrow {
  color: var(--el-color-primary);
  transform: translateX(4px);
}
</style>
