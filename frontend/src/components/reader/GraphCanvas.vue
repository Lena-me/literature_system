<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Graph } from '@antv/g6'
import type { GraphEdge, GraphNode } from '@/types/domain'

// ===========================================================
// Props & Emits
// ===========================================================
const props = withDefaults(defineProps<{
  cypherQuery: string
  graphId?: number | null
  graphData?: { nodes: GraphNode[]; edges: GraphEdge[] } | null
}>(), {
  graphId: null,
  graphData: null,
})

const emit = defineEmits<{
  (e: 'ready'): void
  (e: 'error', message: string): void
}>()

const containerId = 'g6-canvas'

// ===========================================================
// 状态管理
// ===========================================================
const hasData = ref(false)
const layoutReady = ref(false)
const selectedNode = ref<any>(null)

const isLoading = computed(() => hasData.value && !layoutReady.value)
const showSidebar = computed(() => selectedNode.value !== null)

// G6 实例：保持纯净，绝不放入响应式
let graph: any = null
let pendingData: { nodes: GraphNode[]; edges: GraphEdge[] } | null = null

// ===========================================================
// 优雅学术风配色系统 (Light & Clean UI)
// 采用低饱和底色 + 高饱和描边，提供极佳的视觉呼吸感
// ===========================================================
const TYPE_STYLES: Record<string, { fill: string; stroke: string; size: number }> = {
  Paper:      { fill: '#EEF2FF', stroke: '#6366F1', size: 48 }, // 靛蓝
  Method:     { fill: '#ECFDF5', stroke: '#10B981', size: 44 }, // 翡翠绿
  Model:      { fill: '#ECFDF5', stroke: '#10B981', size: 44 }, 
  Task:       { fill: '#FFF7ED', stroke: '#F97316', size: 40 }, // 琥珀橙
  Dataset:    { fill: '#ECFEFF', stroke: '#06B6D4', size: 40 }, // 湖蓝
  Metric:     { fill: '#F5F3FF', stroke: '#8B5CF6', size: 36 }, // 紫罗兰
  Result:     { fill: '#FDF2F8', stroke: '#EC4899', size: 36 }, // 玫瑰粉
  Innovation: { fill: '#F7FEE7', stroke: '#84CC16', size: 36 }, // 柠檬绿
  Limitation: { fill: '#FEF2F2', stroke: '#EF4444', size: 36 }, // 珊瑚红
  Author:     { fill: '#F1F5F9', stroke: '#64748B', size: 32 }, // 高级灰
}

function getNodeStyle(type: string) {
  const t = type.charAt(0).toUpperCase() + type.slice(1)
  return TYPE_STYLES[t] || { fill: '#F8FAFC', stroke: '#94A3B8', size: 36 }
}

function cleanNodeName(raw: string): string {
  let cleaned = raw.trim().replace(/^\[?"?|"?\]?$/g, '').replace(/\s+/g, ' ')
  return cleaned || 'Unknown'
}

function truncateLabel(text: string): string {
  if (text.length <= 12) return text
  return text.slice(0, 10) + '...'
}

// ===========================================================
// 画布初始化
// ===========================================================
function initGraph() {
  const container = document.getElementById(containerId)
  if (!container || container.getBoundingClientRect().width === 0) {
    setTimeout(initGraph, 100)
    return
  }

  if (graph) {
    graph.destroy()
    graph = null
  }

  try {
    graph = new Graph({
      container: containerId,
      autoFit: 'view',
      animation: true,
      node: {
        type: 'circle',
        style: (d: any) => {
          const s = getNodeStyle(d.type || d.data?.type || '')
          return {
            fill: s.fill,
            stroke: s.stroke,
            lineWidth: 2,
            size: s.size,
            
            // --- 现代轻量化标签设计 ---
            labelText: d.label || d.id || '',
            labelFill: '#334155', // 深灰字，清晰但不刺眼
            labelFontSize: 12,
            labelFontWeight: 500,
            labelPlacement: 'bottom',
            labelOffsetY: 8,
            // 纯白半透明底衬，营造优雅悬浮感
            labelBackgroundFill: 'rgba(255, 255, 255, 0.85)',
            labelBackgroundRadius: 16,
            labelPadding: [4, 12],
            // 节点柔和微投影
            shadowColor: 'rgba(0, 0, 0, 0.06)',
            shadowBlur: 12,
            shadowOffsetY: 4,
          }
        },
        state: {
          active: { lineWidth: 3, shadowBlur: 16, shadowColor: 'rgba(0,0,0,0.1)' },
          // 选中态放大投影并加粗边缘
          selected: { lineWidth: 4, shadowBlur: 24, shadowColor: 'rgba(99, 102, 241, 0.3)' },
        },
      },
      edge: {
        type: 'quadratic',
        style: {
          stroke: '#CBD5E1', // 清爽的浅灰蓝色连线
          lineWidth: 1.5,
          endArrow: true,
          endArrowType: 'triangle',
          endArrowSize: 6,
        },
        state: {
          active: { stroke: '#60A5FA', lineWidth: 2 },
        },
      },
      // 增强型力导向布局，保持防重叠能力
      layout: {
        type: 'force',
        preventOverlap: true,
        nodeSize: 85, // 碰撞安全距离
        nodeSpacing: 20,
        linkDistance: 220,
        nodeStrength: -600,
        edgeStrength: 0.1,
        collideStrength: 1,
        alphaDecay: 0.015,
        animate: true,
      },
      behaviors: [
        'drag-canvas',
        'zoom-canvas',
        'drag-element',
        { type: 'hover-activate', degree: 1 },
      ],
      plugins: [
        {
          type: 'tooltip',
          key: 'node-tooltip',
          trigger: 'mouseenter',
          offset: [12, 12],
          getContent: (_event: any, items: any[]) => {
            const item = items?.[0]
            if (!item) return ''
            const fullName = item.data?._name || item.id || ''
            return `<div class="g6-tooltip-box">${fullName}</div>`
          },
          className: 'g6-clean-tooltip',
        },
      ],
      background: 'transparent',
    })

    graph.on('afterlayout', () => {
      if (!layoutReady.value) layoutReady.value = true
    })

    graph.on('node:click', (evt: any) => {
      const nodeId = evt.target?.id
      if (!nodeId) return
      const nodeData = graph.getNodeData(nodeId)
      if (nodeData) {
        selectedNode.value = nodeData
        graph.setElementState(nodeId, 'selected', true)
      }
    })

    graph.on('canvas:click', () => closeSidebar())

    // ★ 拖动节点时自动关闭右侧侧边栏，防止遮挡画布
    graph.on('node:dragstart', () => closeSidebar())
    graph.on('node:drag', () => closeSidebar())

    graph.render()
    emit('ready')

    if (pendingData) {
      setGraphData(pendingData)
      pendingData = null
    }
  } catch (err: any) {
    emit('error', err?.message || 'G6 初始化失败')
  }
}

// ===========================================================
// 数据写入 (防奇点重叠)
// ===========================================================
function setGraphData(data: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  if (!data) return
  if (!graph) {
    pendingData = data
    return
  }

  layoutReady.value = false
  closeSidebar()

  const container = document.getElementById(containerId)
  const width = container ? container.clientWidth : 800
  const height = container ? container.clientHeight : 600

  const g6Nodes = (data.nodes || []).map(n => {
    const fullName = cleanNodeName(n.name || 'Unknown')
    return {
      id: String(n.id),
      type: (n.type || n.entity_type || 'Entity').toLowerCase(),
      label: truncateLabel(fullName),
      // 初始轻微扰动，打破受力奇点
      x: (Math.random() - 0.5) * (width * 0.4) + (width / 2),
      y: (Math.random() - 0.5) * (height * 0.4) + (height / 2),
      data: {
        _id: String(n.id),
        _type: (n.type || n.entity_type || 'Entity'),
        _name: fullName,
        ...(n.properties || {}),
      },
    }
  })

  // ★ 构建节点ID集合，用于过滤孤儿边（source/target节点不存在的边会导致G6崩溃）
  const nodeIdSet = new Set(g6Nodes.map(n => n.id))

  const g6Edges = (data.edges || [])
    .filter(e => {
      const src = String(e.source), tgt = String(e.target)
      const valid = nodeIdSet.has(src) && nodeIdSet.has(tgt)
      if (!valid) console.warn('[GraphCanvas] 跳过孤儿边:', src, '->', tgt, '节点不存在')
      return valid
    })
    .map(e => ({
      id: String(e.id || ''),
      source: String(e.source),
      target: String(e.target),
      label: e.relation_type || '',
      data: { _relation: e.relation_type || '', ...(e.properties || {}) },
    }))

  try {
    graph.setData({ nodes: g6Nodes, edges: g6Edges })
    graph.render()
    graph.fitView({ animation: true })
    hasData.value = true
  } catch (err: any) {
    emit('error', err?.message || 'G6 数据渲染失败')
  }
}

// ===========================================================
// 侧边栏 & 辅助
// ===========================================================
function closeSidebar() {
  if (graph && selectedNode.value) {
    try { graph.setElementState(selectedNode.value.id, 'selected', false) } catch { /* */ }
  }
  selectedNode.value = null
}

function nodeAttributes(): { key: string; value: string }[] {
  const node = selectedNode.value
  if (!node) return []
  const attrs: { key: string; value: string }[] = []
  
  if (node.data?._name) attrs.push({ key: 'Name', value: node.data._name })
  if (node.data?._type) attrs.push({ key: 'Type', value: node.data._type })
  attrs.push({ key: 'Element ID', value: node.id || '' })

  if (node.data) {
    for (const [k, v] of Object.entries(node.data)) {
      if (k.startsWith('_')) continue
      attrs.push({ key: k, value: String(v ?? '—') })
    }
  }
  return attrs
}

watch(() => props.graphData, (data) => {
  if (data && (data.nodes?.length || data.edges?.length)) setGraphData(data)
}, { deep: true, immediate: true })

onMounted(() => initGraph())
onBeforeUnmount(() => {
  closeSidebar()
  pendingData = null // ★ 清理过期数据，防止重新挂载时渲染错误图谱
  if (graph) { graph.destroy(); graph = null }
})

function fitView() { graph?.fitView({ animation: true }) }
function refreshData() { if (props.graphData) setGraphData(props.graphData) }
defineExpose({ fitView, resetView: fitView })
</script>

<template>
  <div class="graph-canvas-wrapper">
    <!-- 悬浮工具栏 -->
    <div class="toolbar" v-if="hasData">
      <button class="tool-btn" @click="fitView" title="适应视野">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14v6h6M20 10V4h-6M10 4H4v6M14 20h6v-6"/></svg>
      </button>
      <button class="tool-btn" @click="refreshData" title="重新布局">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
      </button>
    </div>

    <!-- 画布主体 -->
    <div :id="containerId" class="g6-viz"></div>

    <!-- 柔和的 Loading 遮罩 -->
    <Transition name="fade">
      <div v-if="isLoading" class="layout-loading-overlay">
        <div class="elegant-spinner"></div>
        <span class="loading-text">正在编织知识网络...</span>
      </div>
    </Transition>

    <!-- 极简空状态 -->
    <Transition name="fade">
      <div v-if="!hasData" class="empty-state">
        <div class="empty-clean-card">
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="12" cy="12" r="10"/><path d="M8 12h8M12 8v8"/></svg>
          <div class="empty-text">
            {{ !graphData ? '图谱数据为空，请先抽取文献节点' : '知识图谱初始化中...' }}
          </div>
        </div>
      </div>
    </Transition>

    <!-- ★ 高质感侧边栏 (Modern Light Glassmorphism) -->
    <Transition name="sidebar-slide">
      <aside v-if="showSidebar" class="node-detail-sidebar">
        <div class="sidebar-header">
          <div class="sidebar-title-group">
            <span 
              class="type-indicator"
              :style="{ 
                background: (TYPE_STYLES[selectedNode?.data?._type?.charAt(0).toUpperCase() + selectedNode?.data?._type?.slice(1)] || {}).fill || '#F1F5F9',
                borderColor: (TYPE_STYLES[selectedNode?.data?._type?.charAt(0).toUpperCase() + selectedNode?.data?._type?.slice(1)] || {}).stroke || '#64748B'
              }"
            ></span>
            <h3 class="sidebar-title">{{ selectedNode?.data?._type || 'Entity' }}</h3>
          </div>
          <button class="sidebar-close" @click="closeSidebar" title="关闭">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <div class="sidebar-body">
          <div class="attr-list" v-if="nodeAttributes().length">
            <div class="attr-item" v-for="attr in nodeAttributes()" :key="attr.key">
              <div class="attr-key">{{ attr.key }}</div>
              <div class="attr-value">{{ attr.value }}</div>
            </div>
          </div>
          <div v-else class="sidebar-empty">无详细属性</div>
        </div>
      </aside>
    </Transition>

    <!-- 极简底部图例 -->
    <div class="legend-bar" v-if="hasData">
      <span v-for="(cfg, label) in TYPE_STYLES" :key="label" class="legend-pill">
        <span class="legend-color" :style="{ background: cfg.fill, borderColor: cfg.stroke }"></span>
        {{ label }}
      </span>
    </div>
  </div>
</template>

<style scoped>
/* ========== 全局容器：干净透气的呼吸感背景 ========== */
.graph-canvas-wrapper {
  position: relative;
  height: 100%;
  min-height: 500px;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  overflow: hidden;
  background-color: #F8FAFC; /* 极简的灰白底色，类似高级纸张 */
  /* 非常柔和的网格，提升专业感而不刺眼 */
  background-image: radial-gradient(#E2E8F0 1px, transparent 1px);
  background-size: 24px 24px;
  border: 1px solid #E2E8F0;
  box-shadow: inset 0 2px 20px rgba(0,0,0,0.02);
}

/* ========== 悬浮工具栏 ========== */
.toolbar {
  position: absolute;
  top: 20px;
  right: 20px;
  z-index: 10;
  display: flex;
  gap: 8px;
}
.tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.7);
  color: #64748B;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
}
.tool-btn:hover {
  color: #0F172A;
  background: #FFFFFF;
  border-color: #FFFFFF;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
}

/* ========== 画布 ========== */
.g6-viz {
  flex: 1;
  position: relative;
}

/* ========== 柔和的 Loading 遮罩 ========== */
.layout-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24px;
  background: rgba(248, 250, 252, 0.8);
  backdrop-filter: blur(12px);
}
.elegant-spinner {
  width: 44px;
  height: 44px;
  border: 3px solid #E2E8F0;
  border-top-color: #6366F1; /* 品牌色点缀 */
  border-radius: 50%;
  animation: spin 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text {
  color: #64748B;
  font-size: 15px;
  font-weight: 500;
  letter-spacing: 0.5px;
}

/* ========== 极简空状态 ========== */
.empty-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}
.empty-clean-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  padding: 48px 80px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(16px);
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.04);
}
.empty-icon {
  width: 56px;
  height: 56px;
  color: #94A3B8;
}
.empty-text {
  color: #64748B;
  font-size: 16px;
  font-weight: 500;
}

/* ========== 现代质感详情侧边栏 (Light Glassmorphism) ========== */
.node-detail-sidebar {
  position: absolute;
  top: 20px;
  right: 20px;
  bottom: 20px;
  width: 360px;
  z-index: 30;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(24px) saturate(120%);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 24px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.06), 0 0 0 1px rgba(15, 23, 42, 0.02);
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 28px 20px;
  border-bottom: 1px solid #F1F5F9;
}

.sidebar-title-group {
  display: flex;
  align-items: center;
  gap: 12px;
}
.type-indicator {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid;
}
.sidebar-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #0F172A;
  letter-spacing: 0.2px;
  text-transform: capitalize;
}

.sidebar-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: #F1F5F9;
  color: #64748B;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.sidebar-close:hover {
  background: #E2E8F0;
  color: #0F172A;
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 28px;
}
.sidebar-body::-webkit-scrollbar { width: 4px; }
.sidebar-body::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 4px; }

/* 留白更丰富的属性列表 */
.attr-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.attr-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.attr-key {
  font-size: 13px;
  font-weight: 600;
  color: #94A3B8;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}
.attr-value {
  font-size: 15px;
  color: #334155;
  line-height: 1.6;
  word-break: break-word;
}
/* 对特殊的 ID 字段使用柔和底色强调 */
.attr-item:nth-child(3) .attr-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #475569;
  background: #F1F5F9;
  padding: 4px 8px;
  border-radius: 6px;
  display: inline-block;
}

.sidebar-empty {
  color: #94A3B8;
  font-size: 15px;
  text-align: center;
  padding: 60px 0;
}

/* 侧边栏滑入动画 (轻盈弹簧感) */
.sidebar-slide-enter-active {
  transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}
.sidebar-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 1, 1);
}
.sidebar-slide-enter-from,
.sidebar-slide-leave-to {
  transform: translateX(120%) scale(0.98);
  opacity: 0;
}

/* ========== 底部极简图例 ========== */
.legend-bar {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 16px;
  padding: 14px 24px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.9);
  border-radius: 100px;
  backdrop-filter: blur(16px);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
  z-index: 10;
}
.legend-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #475569;
}
.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid;
}

/* 过渡 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>

<!-- =========================================================== -->
<!-- 全局悬浮提示 Tooltip (Light UI 样式) -->
<!-- =========================================================== -->
<style>
.g6-clean-tooltip {
  pointer-events: none;
}
.g6-tooltip-box {
  max-width: 280px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.95) !important;
  border: 1px solid rgba(226, 232, 240, 0.8) !important;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08) !important;
  border-radius: 12px !important;
  color: #1E293B !important;
  font-size: 14px !important;
  font-weight: 500 !important;
  line-height: 1.6 !important;
  backdrop-filter: blur(12px) !important;
}
</style>