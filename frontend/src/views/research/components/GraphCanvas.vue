<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { LiteratureGraphEdge, LiteratureGraphNode } from '@/api/knowledge'

interface LayoutNode extends LiteratureGraphNode {
  x: number
  y: number
  radius: number
  color: string
}

interface LayoutEdge extends LiteratureGraphEdge {
  x1: number
  y1: number
  x2: number
  y2: number
}

type SelectedPanel =
  | { kind: 'summary' }
  | { kind: 'node'; node: LiteratureGraphNode }
  | { kind: 'edge'; edge: LiteratureGraphEdge }

type GraphDisplayState = 'empty' | 'low' | 'normal' | 'weak'
interface GraphDisplayMessage { title: string; description: string; suggestion?: string }

const props = defineProps<{
  loading: boolean
  layoutEdges: LayoutEdge[]
  layoutNodes: LayoutNode[]
  selectedPanel: SelectedPanel
  selectedNodeForPanel: LiteratureGraphNode | null
  filteredEdges: LiteratureGraphEdge[]
  graphNodes: LiteratureGraphNode[]
  yearRange: [number, number]
  edgeStroke: (edge: LiteratureGraphEdge) => string
  edgeWidth: (edge: LiteratureGraphEdge) => number
  edgeOpacity: (edge: LiteratureGraphEdge) => number
  nodeOpacity: (node: LayoutNode) => number
  nodePrimaryLabel: (node: LiteratureGraphNode) => string
  nodeYearLabel: (node: LiteratureGraphNode) => string
  nodeCaption: (node: LiteratureGraphNode) => string
  formatAuthors: (value?: string | null) => string
  displayState: GraphDisplayState
  displayMessage: GraphDisplayMessage
  singlePaper: LiteratureGraphNode | null
}>()

const emit = defineEmits<{
  (e: 'select-summary'): void
  (e: 'select-edge', edge: LiteratureGraphEdge): void
  (e: 'select-node', node: LiteratureGraphNode): void
  (e: 'open-create'): void
  (e: 'open-library'): void
}>()

function isNodeSelected(node: LayoutNode) {
  return props.selectedPanel.kind === 'node' && String(props.selectedNodeForPanel?.id) === String(node.id)
}

function nodeSelectedTransform(node: LayoutNode) {
  if (!isNodeSelected(node)) return undefined
  return `translate(${node.x} ${node.y}) scale(1.02) translate(${-node.x} ${-node.y})`
}

const bestEdge = computed(() => {
  return [...props.filteredEdges].sort((a, b) => (b.score || 0) - (a.score || 0))[0] || null
})

const bestPairLabel = computed(() => {
  if (!bestEdge.value) return '暂无明确最相近论文'
  const source = props.graphNodes.find(node => String(node.id) === String(bestEdge.value?.source))
  const target = props.graphNodes.find(node => String(node.id) === String(bestEdge.value?.target))
  return `${source?.label || source?.title || '论文 A'} ↔ ${target?.label || target?.title || '论文 B'}`
})

const bestSharedKeywords = computed(() => {
  if (!bestEdge.value) return [] as string[]
  return (bestEdge.value.shared_keywords?.length ? bestEdge.value.shared_keywords : bestEdge.value.shared_terms || []).slice(0, 8)
})

const paperKeywords = computed(() => props.singlePaper?.keywords?.slice(0, 8) || [])

const canvasRef = ref<HTMLElement | null>(null)
const panX = ref(0)
const panY = ref(0)
const zoom = ref(1)
const isPanning = ref(false)
const panMoved = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const activePointerId = ref<number | null>(null)

const MIN_ZOOM = 0.35
const MAX_ZOOM = 3

const contentBounds = computed(() => {
  const nodes = props.layoutNodes
  if (!nodes.length) {
    return { minX: 0, minY: 0, maxX: 960, maxY: 640, width: 960, height: 640, cx: 480, cy: 320 }
  }

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  for (const node of nodes) {
    const labelPad = node.radius + 34
    minX = Math.min(minX, node.x - node.radius - 24)
    maxX = Math.max(maxX, node.x + node.radius + 24)
    minY = Math.min(minY, node.y - node.radius - 24)
    maxY = Math.max(maxY, node.y + labelPad)
  }

  const width = Math.max(320, maxX - minX)
  const height = Math.max(240, maxY - minY)
  return {
    minX,
    minY,
    maxX,
    maxY,
    width,
    height,
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
  }
})

const svgViewBox = computed(() => {
  const bounds = contentBounds.value
  const pad = props.layoutNodes.length > 8 ? 56 : 40
  return `${bounds.minX - pad} ${bounds.minY - pad} ${bounds.width + pad * 2} ${bounds.height + pad * 2}`
})

const viewportTransform = computed(() => {
  const { cx, cy } = contentBounds.value
  return `translate(${panX.value + cx} ${panY.value + cy}) scale(${zoom.value}) translate(${-cx} ${-cy})`
})

watch(
  () => [props.layoutNodes.length, props.filteredEdges.length, props.displayState],
  () => resetView(),
)

function resetView() {
  panX.value = 0
  panY.value = 0
  zoom.value = 1
}

function clampZoom(value: number) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value))
}

function zoomBy(factor: number) {
  zoom.value = clampZoom(zoom.value * factor)
}

function pixelDeltaToSvg(dx: number, dy: number) {
  const svg = canvasRef.value?.querySelector('svg')
  if (!svg) return { dx, dy }
  const rect = svg.getBoundingClientRect()
  const [, , vbWidth, vbHeight] = svgViewBox.value.split(' ').map(Number)
  if (!rect.width || !rect.height) return { dx, dy }
  return {
    dx: (dx / rect.width) * vbWidth,
    dy: (dy / rect.height) * vbHeight,
  }
}

function onWheel(event: WheelEvent) {
  event.preventDefault()
  const factor = event.deltaY > 0 ? 0.92 : 1.08
  zoom.value = clampZoom(zoom.value * factor)
}

function onWindowPointerEnd(event: PointerEvent) {
  if (activePointerId.value != null && event.pointerId !== activePointerId.value) return
  endPan()
}

function bindPanWindowListeners() {
  window.addEventListener('pointerup', onWindowPointerEnd)
  window.addEventListener('pointercancel', onWindowPointerEnd)
}

function unbindPanWindowListeners() {
  window.removeEventListener('pointerup', onWindowPointerEnd)
  window.removeEventListener('pointercancel', onWindowPointerEnd)
}

function endPan() {
  if (!isPanning.value) return
  isPanning.value = false
  if (activePointerId.value != null && canvasRef.value) {
    try {
      canvasRef.value.releasePointerCapture(activePointerId.value)
    } catch {
      // ignore if capture was already released
    }
  }
  activePointerId.value = null
  unbindPanWindowListeners()
}

function onPanStart(event: PointerEvent) {
  if (event.button !== 0) return
  const target = event.target as Element | null
  if (target?.closest('.node-group') || target?.closest('.edge-line') || target?.closest('.canvas-toolbar')) return

  isPanning.value = true
  panMoved.value = false
  activePointerId.value = event.pointerId
  panStart.value = {
    x: event.clientX,
    y: event.clientY,
    panX: panX.value,
    panY: panY.value,
  }

  bindPanWindowListeners()
  try {
    canvasRef.value?.setPointerCapture(event.pointerId)
  } catch {
    // pointer capture may fail in some browsers; window listeners still clean up
  }
}

function onPanMove(event: PointerEvent) {
  if (!isPanning.value) return
  if (activePointerId.value != null && event.pointerId !== activePointerId.value) return
  const dx = event.clientX - panStart.value.x
  const dy = event.clientY - panStart.value.y
  if (Math.abs(dx) > 4 || Math.abs(dy) > 4) panMoved.value = true
  const delta = pixelDeltaToSvg(dx, dy)
  panX.value = panStart.value.panX + delta.dx
  panY.value = panStart.value.panY + delta.dy
}

function onPanEnd(event: PointerEvent) {
  if (activePointerId.value != null && event.pointerId !== activePointerId.value) return
  endPan()
}

function onLostPointerCapture() {
  endPan()
}

onBeforeUnmount(() => {
  endPan()
})

function onCanvasClick() {
  if (panMoved.value) return
  emit('select-summary')
}

function compactText(value?: string | null, fallback = '暂无抽取结果') {
  const text = (value || '').trim()
  if (!text) return fallback
  return text.length > 120 ? `${text.slice(0, 120)}...` : text
}
</script>

<template>
  <div
    v-if="props.displayState === 'empty'"
    class="graph-empty-state"
    @click.stop
  >
    <div class="empty-visual" aria-hidden="true">
      <span class="empty-node main"></span>
      <span class="empty-node sub left"></span>
      <span class="empty-node sub right"></span>
      <span class="empty-line left"></span>
      <span class="empty-line right"></span>
    </div>
    <div class="empty-copy">
      <h3>{{ props.displayMessage.title }}</h3>
      <p>{{ props.displayMessage.description }}</p>
      <div class="empty-actions">
        <button class="ghost-action" @click="emit('open-library')">选择更多文献</button>
        <button class="primary-action" @click="emit('open-create')">继续上传 / 新建图谱</button>
      </div>
    </div>

    <article v-if="props.singlePaper" class="single-paper-card">
      <div class="single-paper-head">
        <p>单篇论文要点概览</p>
        <h4>{{ props.singlePaper.title }}</h4>
        <span>{{ props.formatAuthors(props.singlePaper.authors) }} · {{ props.singlePaper.year || '年份未知' }}</span>
      </div>
      <dl>
        <dt>论文摘要</dt>
        <dd>{{ compactText(props.singlePaper.abstract, '该论文暂无摘要信息。') }}</dd>
        <dt>关键词</dt>
        <dd>
          <span v-for="kw in paperKeywords" :key="kw" class="keyword-pill">{{ kw }}</span>
          <span v-if="!paperKeywords.length">暂无关键词</span>
        </dd>
        <dt>研究问题</dt>
        <dd>{{ compactText(props.singlePaper.research_question) }}</dd>
        <dt>方法</dt>
        <dd>{{ compactText(props.singlePaper.method) }}</dd>
        <dt>贡献</dt>
        <dd>{{ compactText(props.singlePaper.innovations || props.singlePaper.main_results) }}</dd>
      </dl>
    </article>
  </div>

  <template v-else>
    <div
      ref="canvasRef"
      class="svg-shell"
      :class="{
        loading: props.loading,
        compact: props.displayState === 'low',
        weak: props.displayState === 'weak',
        panning: isPanning,
      }"
      @wheel.prevent="onWheel"
      @click="onCanvasClick"
      @pointerdown="onPanStart"
      @pointermove="onPanMove"
      @pointerup="onPanEnd"
      @pointercancel="onPanEnd"
      @lostpointercapture="onLostPointerCapture"
    >
      <div class="canvas-toolbar" @click.stop @pointerdown.stop>
        <button type="button" class="canvas-tool-btn" title="缩小" aria-label="缩小" @click="zoomBy(0.85)">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8h9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg>
        </button>
        <button type="button" class="canvas-tool-btn" title="放大" aria-label="放大" @click="zoomBy(1.15)">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.5v9M3.5 8h9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg>
        </button>
        <button type="button" class="canvas-tool-btn" title="适应画布" aria-label="适应画布" @click="resetView">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 5.5V3.5h2M10.5 3.5h2v2M12.5 10.5v2h-2M5.5 12.5h-2v-2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" /></svg>
        </button>
      </div>

      <svg
        :viewBox="svgViewBox"
        role="img"
        aria-label="文献关系图谱"
      >
        <defs>
          <filter id="nodeShadow" x="-40%" y="-40%" width="180%" height="180%">
            <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#0f172a" flood-opacity="0.16" />
          </filter>
        </defs>

        <g :transform="viewportTransform">
        <g class="edges-layer">
          <line
            v-for="edge in props.layoutEdges"
            :key="edge.id"
            :x1="edge.x1"
            :y1="edge.y1"
            :x2="edge.x2"
            :y2="edge.y2"
            :stroke="props.edgeStroke(edge)"
            :stroke-width="props.displayState === 'weak' ? Math.min(props.edgeWidth(edge), 2.2) : props.edgeWidth(edge)"
            :stroke-opacity="props.displayState === 'weak' ? 0.5 : props.edgeOpacity(edge)"
            :stroke-dasharray="edge.strength === 'weak' || props.displayState === 'weak' ? '8 8' : undefined"
            stroke-linecap="round"
            class="edge-line"
            @click.stop="emit('select-edge', edge)"
            @pointerdown.stop
          />
        </g>

        <g class="nodes-layer">
          <g
            v-for="node in props.layoutNodes"
            :key="node.id"
            class="node-group"
            :class="{ 'is-selected': isNodeSelected(node) }"
            :transform="nodeSelectedTransform(node)"
            :style="{ opacity: props.nodeOpacity(node) }"
            @click.stop="emit('select-node', node)"
            @pointerdown.stop
          >
            <circle
              v-if="isNodeSelected(node)"
              :cx="node.x"
              :cy="node.y"
              :r="node.radius + 3.5"
              class="node-select-ring"
            />
            <circle
              :cx="node.x"
              :cy="node.y"
              :r="node.radius + 5"
              class="node-soft-ring"
              :stroke="node.color"
            />
            <circle
              :cx="node.x"
              :cy="node.y"
              :r="node.radius"
              :fill="node.color"
              stroke="#ffffff"
              stroke-width="4.8"
              filter="url(#nodeShadow)"
            />
            <text :x="node.x" :y="node.y - 3" text-anchor="middle" class="node-core-label">{{ props.nodePrimaryLabel(node) }}</text>
            <text :x="node.x" :y="node.y + 14" text-anchor="middle" class="node-year-label">{{ props.nodeYearLabel(node) }}</text>
            <text
              :x="node.x"
              :y="node.y + node.radius + 26"
              text-anchor="middle"
              class="node-label"
            >{{ props.nodeCaption(node) }}</text>
            <title>{{ node.title }}&#10;{{ props.formatAuthors(node.authors) }}&#10;本地中心性：{{ node.centrality ?? 0 }}</title>
          </g>
        </g>
        </g>
      </svg>

      <div v-if="!props.filteredEdges.length && props.graphNodes.length > 1" class="canvas-empty-note">
        当前筛选下暂无可展示的关联，可切换关联类型查看。
      </div>
    </div>

    <div class="legend-row">
      <div class="legend-item"><span class="legend-line strong"></span>强关联</div>
      <div class="legend-item"><span class="legend-line medium"></span>中等关联</div>
      <div class="legend-item"><span class="legend-line weak"></span>弱关联</div>
      <div class="year-legend">
        <span>{{ props.yearRange[0] }}</span>
        <span class="year-gradient"></span>
        <span>{{ props.yearRange[1] }}</span>
        <span class="unknown-dot"></span>
        <span>年份未知</span>
      </div>
    </div>
  </template>
</template>

<style scoped>
.svg-shell {
  position: relative;
  flex: 1;
  min-height: 0;
  margin: 0;
  border-radius: 0;
  background: #f8fafc;
  border: none;
  border-top: 1px solid #eef2f7;
  overflow: hidden;
  cursor: grab;
  touch-action: none;
}

.svg-shell.panning {
  cursor: grabbing;
}

.canvas-toolbar {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(6px);
}

.canvas-tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.canvas-tool-btn svg {
  width: 13px;
  height: 13px;
}

.canvas-tool-btn:hover {
  background: #f1f5f9;
  color: #2563eb;
}

.svg-shell.compact svg {
  min-height: 500px;
}

.svg-shell.compact {
  flex: 1;
  min-height: 0;
}

.svg-shell.weak {
  background:
    radial-gradient(circle at 48% 40%, rgba(148, 163, 184, 0.10), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 253, 255, 0.96));
}

.svg-shell.weak svg {
  opacity: 0.82;
  filter: saturate(0.80);
}

.svg-shell svg {
  width: 100%;
  height: 100%;
  min-height: 530px;
  display: block;
  user-select: none;
}

.graph-empty-state {
  position: relative;
  flex: 1;
  min-height: 0;
  margin: 0;
  border-radius: 0;
  background: #f8fafc;
  border: none;
  border-top: 1px solid #eef2f7;
  overflow: hidden;
}

.edge-line {
  cursor: pointer;
  vector-effect: non-scaling-stroke;
  transition: stroke-opacity 0.16s, stroke-width 0.16s;
}

.edge-line:hover {
  stroke-opacity: 1;
}

.node-group {
  cursor: pointer;
  transition: opacity 0.16s ease;
}

.node-select-ring {
  fill: none;
  stroke: #2563eb;
  stroke-width: 2;
  pointer-events: none;
}

.node-soft-ring {
  fill: none;
  stroke-opacity: 0.20;
  stroke-width: 8;
}

.node-core-label,
.node-year-label {
  fill: #fff;
  font-weight: 850;
  paint-order: stroke;
  stroke: rgba(15, 23, 42, 0.12);
  stroke-width: 2px;
  stroke-linejoin: round;
}

.node-core-label {
  font-size: 14.5px;
}

.node-year-label {
  font-size: 14px;
}

.node-label {
  fill: #23334b;
  font-size: 13.8px;
  font-weight: 880;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.98);
  stroke-width: 5.5px;
  stroke-linejoin: round;
}

.canvas-empty-note {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  padding: 14px 18px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  color: #64748b;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.10);
}


.graph-empty-state {
  display: grid;
  grid-template-columns: minmax(230px, 0.8fr) minmax(280px, 1.1fr);
  gap: 22px;
  padding: 26px;
  align-items: center;
  overflow-y: auto;
}

.empty-visual {
  position: relative;
  min-height: 260px;
  border-radius: 22px;
  background: linear-gradient(135deg, #f8fbff, #eef7ff);
  border: 1px solid #dce8f6;
}

.empty-node,
.empty-line {
  position: absolute;
  display: block;
}

.empty-node {
  width: 58px;
  height: 58px;
  border-radius: 999px;
  background: #dbeafe;
  border: 3px solid #fff;
  box-shadow: 0 18px 35px rgba(37, 99, 235, 0.15);
}

.empty-node.main { left: 50%; top: 45%; transform: translate(-50%, -50%); background: #60a5fa; }
.empty-node.left { left: 22%; top: 58%; }
.empty-node.right { right: 22%; top: 58%; }
.empty-line { height: 2px; width: 92px; background: #cbd5e1; top: 57%; }
.empty-line.left { left: 31%; transform: rotate(-18deg); }
.empty-line.right { right: 31%; transform: rotate(18deg); }

.empty-copy h3 {
  margin: 0 0 8px;
  color: #0f1f3d;
  font-size: 22px;
}

.empty-copy p {
  margin: 0;
  color: #64748b;
  line-height: 1.75;
}

.empty-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.primary-action,
.ghost-action {
  border: none;
  border-radius: 999px;
  padding: 10px 16px;
  font-weight: 850;
  cursor: pointer;
}

.primary-action { background: #2563eb; color: #fff; }
.ghost-action { background: #fff; color: #2563eb; border: 1px solid #bfdbfe; }

.single-paper-card {
  grid-column: 1 / -1;
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #e2e8f0;
}

.single-paper-head p {
  margin: 0 0 4px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 850;
}

.single-paper-head h4 {
  margin: 0 0 6px;
  color: #16243a;
  font-size: 16px;
}

.single-paper-head span {
  color: #64748b;
  font-size: 12px;
}

.single-paper-card dl {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 10px 14px;
  margin: 16px 0 0;
}

.single-paper-card dt {
  color: #1e293b;
  font-weight: 850;
}

.single-paper-card dd {
  margin: 0;
  color: #526175;
  line-height: 1.65;
}

.keyword-pill {
  display: inline-block;
  margin: 0 6px 6px 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: #e8faf7;
  color: #0f766e;
  font-size: 12px;
  font-weight: 750;
}


.legend-row {
  display: flex;
  justify-content: center;
  gap: 18px;
  padding: 8px 14px 18px;
  margin-top: auto;
  color: #66788a;
  font-size: 12px;
  flex-wrap: wrap;
}

.legend-item,
.year-legend {
  display: flex;
  align-items: center;
  gap: 8px;
}

.legend-line {
  width: 34px;
  height: 0;
  border-top: 3px solid #2563eb;
}

.legend-line.medium {
  border-color: #7788a0;
  border-top-width: 2px;
}

.legend-line.weak {
  border-color: #aab7c8;
  border-top-width: 2px;
  border-top-style: dashed;
}

.year-gradient {
  width: 118px;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, #94a3b8, #14b8a6, #60a5fa, #6366f1);
}

.unknown-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #cbd5e1;
}

@media (max-width: 1180px) {
  .compact-relation-panel,
  .graph-empty-state {
    grid-template-columns: 1fr;
  }
}
</style>
