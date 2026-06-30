<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch, computed } from 'vue'
import { Graph } from '@antv/g6'
import type { KnowledgeGraph, GraphNode, GraphEdge } from '@/types/domain'

const props = withDefaults(defineProps<{
  graph?: KnowledgeGraph | null
  mode?: 'detail' | 'overview'
}>(), {
  mode: 'detail',
})

const emit = defineEmits<{
  (e: 'change-mode', mode: 'detail' | 'overview'): void
  (e: 'node-dblclick', nodeId: string, type: string): void
}>()

const el = ref<HTMLDivElement | null>(null)
let instance: any
const internalMode = ref(props.mode)

// ============================================================
// 实体类型 → 视觉配置
// ============================================================
const TYPE_CONFIG: Record<string, { color: string; size: number; rank: number; icon: string; label: string }> = {
  task:     { color: '#ff7a45', size: 48, rank: 0, icon: '🎯', label: '核心问题' },
  method:   { color: '#597ef7', size: 44, rank: 1, icon: '⚙️', label: '方法' },
  innovation:{ color: '#73d13d', size: 40, rank: 1, icon: '💡', label: '创新点' },
  paper:    { color: '#ffc53d', size: 40, rank: 2, icon: '📄', label: '论文' },
  dataset:  { color: '#36cfc9', size: 34, rank: 3, icon: '📊', label: '数据集' },
  metric:   { color: '#b37feb', size: 32, rank: 3, icon: '📈', label: '指标' },
  result:   { color: '#ff85c0', size: 32, rank: 3, icon: '📋', label: '结果' },
  limitation:{ color: '#ff9c6e', size: 30, rank: 3, icon: '⚠️', label: '局限' },
  author:   { color: '#5cdbd3', size: 28, rank: 3, icon: '👤', label: '作者' },
  __default__: { color: '#d9d9d9', size: 30, rank: 2, icon: '📌', label: '其他' },
}

function getTypeConfig(type?: string) {
  return TYPE_CONFIG[type || ''] || TYPE_CONFIG['__default__']
}

// ============================================================
// 构建 Dagre 层次布局数据
// ============================================================
function buildLayoutData(graph: KnowledgeGraph, viewMode: string) {
  if (viewMode === 'overview') {
    return buildOverviewData(graph)
  }
  return buildDetailData(graph)
}

function buildDetailData(graph: KnowledgeGraph) {
  const nodes = graph.nodes.map(n => ({
    id: String(n.id),
    data: {
      label: n.name,
      type: n.entity_type || n.type || 'paper',
    },
  }))

  const edges = graph.edges.map(e => ({
    source: String(e.source_node_id ?? e.source),
    target: String(e.target_node_id ?? e.target),
    data: { label: e.relation_type ?? 'related_to' },
  }))

  return { nodes, edges }
}

function buildOverviewData(graph: KnowledgeGraph) {
  // 按类型聚合
  const typeMap: Record<string, { count: number; examples: string[]; ids: string[] }> = {}
  for (const n of graph.nodes) {
    const t = (n.entity_type || n.type || 'paper')
    if (!typeMap[t]) typeMap[t] = { count: 0, examples: [], ids: [] }
    typeMap[t].count++
    typeMap[t].ids.push(String(n.id))
    if (typeMap[t].examples.length < 3) {
      typeMap[t].examples.push(n.name)
    }
  }

  const nodes = Object.entries(typeMap).map(([type, info]) => {
    const cfg = getTypeConfig(type)
    const displayedLabel = info.count === 1
      ? info.examples[0]
      : `${cfg.icon} ${cfg.label} (${info.count})`

    return {
      id: `group:${type}`,
      data: {
        label: displayedLabel,
        type,
        isGroup: true,
        groupIds: info.ids,
        groupCount: info.count,
        groupExamples: info.examples,
      },
    }
  })

  // 概览模式：按关系类型聚合（如果有边连接不同类型组）
  const typeSet = new Set(Object.keys(typeMap))
  const edges: any[] = []

  // 为不同类型组之间添加关系边（基于原始边的统计）
  const rawEdges = graph.edges || []
  const crossTypeEdges = new Set<string>()
  const nodeTypeMap: Record<string, string> = {}
  for (const n of graph.nodes) {
    nodeTypeMap[String(n.id)] = n.entity_type || n.type || 'paper'
  }

  for (const e of rawEdges) {
    const srcId = String(e.source_node_id ?? e.source)
    const tgtId = String(e.target_node_id ?? e.target)
    const srcType = nodeTypeMap[srcId] || 'paper'
    const tgtType = nodeTypeMap[tgtId] || 'paper'
    if (srcType !== tgtType) {
      const key = `${srcType}->${tgtType}`
      crossTypeEdges.add(key)
    }
  }

  for (const key of crossTypeEdges) {
    const [src, tgt] = key.split('->')
    edges.push({
      source: `group:${src}`,
      target: `group:${tgt}`,
      data: { label: '关联' },
    })
  }

  return { nodes, edges }
}

// ============================================================
// 渲染
// ============================================================
async function render() {
  if (!el.value || !props.graph || !props.graph.nodes?.length) return

  await nextTick()
  await new Promise(resolve => setTimeout(resolve, 80))

  instance?.destroy?.()

  const width = el.value.clientWidth || 800
  const height = el.value.clientHeight || 560
  internalMode.value = props.mode

  const data = buildLayoutData(props.graph, internalMode.value)

  const isOverview = internalMode.value === 'overview'

  instance = new Graph({
    container: el.value,
    width,
    height,
    data,
    node: {
      type: 'rect',
      style: (d: any) => {
        const t = d.data?.type || 'paper'
        const cfg = getTypeConfig(t)
        const rawLabel = d.data?.label || ''
        const text = rawLabel.length > 26 ? rawLabel.slice(0, 26) + '…' : rawLabel
        const isGroup = d.data?.isGroup

        if (isGroup) {
          return {
            size: [Math.min(220, Math.max(140, d.data.groupCount * 30 + 80)), 48],
            radius: 8,
            fill: cfg.color + '33',
            stroke: cfg.color,
            lineWidth: 2,
            labelText: text,
            labelFill: cfg.color,
            labelFontSize: 14,
            labelFontWeight: 'bold',
            labelPlacement: 'center',
            labelBackground: false,
          }
        }

        return {
          size: [Math.min(220, Math.max(90, text.length * 12)), 40],
          radius: 6,
          fill: '#1a2035',
          stroke: cfg.color,
          lineWidth: 2,
          labelText: text,
          labelFill: '#ffffff',
          labelFontSize: 13,
          labelFontWeight: 'normal',
          labelPlacement: 'center',
          labelBackground: true,
          labelBackgroundFill: '#0d1117',
          labelBackgroundRadius: 4,
          labelBackgroundPadding: [3, 8],
        }
      },
    },
    edge: {
      type: 'cubic-horizontal',
      labelText: (d: any) => d.data?.label || '',
      labelFill: '#c4d6f0',
      labelFontSize: 10,
      labelBackground: true,
      labelBackgroundFill: 'rgba(17,24,39,0.85)',
      labelBackgroundRadius: 3,
      labelBackgroundPadding: [1, 4],
      style: {
        stroke: 'rgba(255,255,255,.28)',
        lineWidth: 1.2,
        endArrow: true,
      },
    },
    layout: {
      type: 'dagre',
      rankdir: 'LR',
      nodesep: isOverview ? 60 : 40,
      ranksep: isOverview ? 120 : 100,
      ranker: 'tight-tree',
    },
    behaviors: [
      'drag-canvas',
      'zoom-canvas',
      'drag-element',
      {
        type: 'hover-activate',
        degree: 1,
        direction: 'both',
      },
    ],
  })

  // ★ 概览模式下双击组节点 → 展开为详细视图
  instance.on('node:dblclick', (evt: any) => {
    const nodeId = evt.target?.id
    if (!nodeId) return

    if (isOverview && nodeId.startsWith('group:')) {
      const type = nodeId.replace('group:', '')
      // 切换到详情模式
      internalMode.value = 'detail'
      emit('change-mode', 'detail')
      render()
    }
    emit('node-dblclick', nodeId, nodeId.replace('group:', ''))
  })

  instance.render()
}

// ============================================================
// 监听
// ============================================================
onMounted(render)
watch(() => props.graph, render, { deep: true })
watch(() => props.mode, (newMode) => {
  if (newMode !== internalMode.value) {
    internalMode.value = newMode
    render()
  }
})

onBeforeUnmount(() => {
  instance?.destroy?.()
})

// ============================================================
// 对外方法
// ============================================================
function toggleView() {
  internalMode.value = internalMode.value === 'overview' ? 'detail' : 'overview'
  emit('change-mode', internalMode.value)
  render()
}

function resetView() {
  instance?.fitView?.()
}

defineExpose({ toggleView, resetView, currentMode: internalMode })
</script>

<template>
  <div class="graph-container">
    <!-- 视图切换按钮 -->
    <div class="view-controls" v-if="graph && graph.nodes?.length">
      <button
        class="view-btn"
        :class="{ active: internalMode === 'overview' }"
        @click="internalMode = 'overview'; emit('change-mode', 'overview'); render()"
      >
        🗂️ 概览
      </button>
      <button
        class="view-btn"
        :class="{ active: internalMode === 'detail' }"
        @click="internalMode = 'detail'; emit('change-mode', 'detail'); render()"
      >
        🔬 详情
      </button>
      <button class="view-btn reset-btn" @click="resetView">⊞ 重置视野</button>
    </div>

    <div ref="el" class="graph-canvas">
      <div v-if="!graph" class="empty">Select a knowledge graph to view entity relations.</div>
      <div v-else-if="!graph.nodes || graph.nodes.length === 0" class="empty">
        The current graph has no nodes. Check extraction results or regenerate the graph.
      </div>
    </div>

    <!-- 图例 -->
    <div class="legend" v-if="graph && graph.nodes?.length && internalMode === 'detail'">
      <span v-for="(cfg, type) in TYPE_CONFIG" :key="type" class="legend-item"
        v-show="type !== '__default__'">
        <span class="legend-dot" :style="{ background: cfg.color }"></span>
        {{ cfg.label }}
      </span>
    </div>

    <!-- 概览模式提示 -->
    <div class="hint-bar" v-if="graph && graph.nodes?.length && internalMode === 'overview'">
      💡 双击任意类型节点可展开查看该类型的详细实体关系
    </div>
  </div>
</template>

<style scoped>
.graph-container {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.view-controls {
  position: absolute;
  top: 10px;
  left: 12px;
  z-index: 10;
  display: flex;
  gap: 6px;
}
.view-btn {
  padding: 3px 12px;
  border-radius: 4px;
  border: 1px solid rgba(255,255,255,.18);
  background: rgba(17,28,51,.9);
  color: #9fb1cc;
  font-size: 12px;
  cursor: pointer;
  transition: all .2s;
  backdrop-filter: blur(6px);
}
.view-btn.active {
  background: rgba(102,231,255,.18);
  border-color: rgba(102,231,255,.5);
  color: #66e7ff;
}
.view-btn:hover { border-color: rgba(255,255,255,.35); }
.reset-btn { margin-left: 8px; }

.graph-canvas {
  flex: 1;
  border-radius: 22px;
  background: radial-gradient(circle at center, rgba(102,231,255,.10), rgba(255,255,255,.03));
  border: 1px solid rgba(255,255,255,.10);
  overflow: hidden;
  position: relative;
  min-height: 480px;
}
.empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: rgba(238,246,255,.45);
  text-align: center;
  padding: 20px;
  font-size: 14px;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  padding: 8px 60px 0 12px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #9fb1cc;
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}

.hint-bar {
  text-align: center;
  padding: 6px 12px;
  font-size: 12px;
  color: #ffc53d;
  background: rgba(255,197,61,.08);
  border-top: 1px solid rgba(255,197,61,.2);
  border-radius: 0 0 8px 8px;
}
</style>
