<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

// ============================================================
// Props：接收 Cypher 查询字符串 + Neo4j 连接信息
// ============================================================
const props = withDefaults(defineProps<{
  cypherQuery: string
  neo4jUri?: string
  neo4jUser?: string
  neo4jPassword?: string
  graphId?: number | null
}>(), {
  neo4jUri: '',
  neo4jUser: '',
  neo4jPassword: '',
  graphId: null,
})

const emit = defineEmits<{
  (e: 'ready'): void
  (e: 'error', message: string): void
}>()

const containerId = 'neo4j-viz-canvas'
const hasQuery = ref(false)
const errorMsg = ref('')
const loading = ref(false)
let neoVisInstance: any = null

// ============================================================
// 实体类型 → 学术科技感配色
// ============================================================
const LABEL_COLORS: Record<string, { background: string; border: string; highlightBg: string; highlightBorder: string; size: number }> = {
  Paper:      { background: '#ffc53d', border: '#d4a017', highlightBg: '#ffe58f', highlightBorder: '#d4a017', size: 40 },
  Method:     { background: '#597ef7', border: '#1d39c4', highlightBg: '#85a5ff', highlightBorder: '#1d39c4', size: 42 },
  Model:      { background: '#597ef7', border: '#1d39c4', highlightBg: '#85a5ff', highlightBorder: '#1d39c4', size: 42 },
  Task:       { background: '#ff7a45', border: '#d4380d', highlightBg: '#ffbb96', highlightBorder: '#d4380d', size: 44 },
  Dataset:    { background: '#36cfc9', border: '#08979c', highlightBg: '#87e8de', highlightBorder: '#08979c', size: 34 },
  Metric:     { background: '#b37feb', border: '#531dab', highlightBg: '#d3adf7', highlightBorder: '#531dab', size: 32 },
  Result:     { background: '#ff85c0', border: '#c41d7f', highlightBg: '#ffadd2', highlightBorder: '#c41d7f', size: 32 },
  Innovation: { background: '#73d13d', border: '#389e0d', highlightBg: '#b7eb8f', highlightBorder: '#389e0d', size: 36 },
  Limitation: { background: '#ff9c6e', border: '#d46b08', highlightBg: '#ffd591', highlightBorder: '#d46b08', size: 30 },
  Author:     { background: '#5cdbd3', border: '#006d75', highlightBg: '#b5f5ec', highlightBorder: '#006d75', size: 28 },
}

function getLabelConfig(label: string) {
  return LABEL_COLORS[label] || { background: '#bfbfbf', border: '#8c8c8c', highlightBg: '#d9d9d9', highlightBorder: '#8c8c8c', size: 30 }
}

// ============================================================
// 构建 neovis.js 配置
// ============================================================
function buildNeoVisConfig(query: string) {
  const uri = props.neo4jUri || import.meta.env.VITE_NEO4J_URI || 'bolt://127.0.0.1:7687'
  const user = props.neo4jUser || import.meta.env.VITE_NEO4J_USER || 'neo4j'
  const password = props.neo4jPassword || import.meta.env.VITE_NEO4J_PASSWORD || 'neo4j'

  // 动态构建 labels 配置
  const labels: Record<string, any> = {}
  for (const [label, colorCfg] of Object.entries(LABEL_COLORS)) {
    labels[label] = {
      caption: 'name',
      size: colorCfg.size,
      font: { size: 13, color: '#ffffff', face: 'Inter, system-ui, sans-serif' },
      color: {
        background: colorCfg.background,
        border: colorCfg.border,
        highlight: {
          background: colorCfg.highlightBg,
          border: colorCfg.highlightBorder,
        },
      },
    }
  }
  // 兜底：Entity 默认样式
  labels.Entity = {
    caption: 'name',
    size: 30,
    font: { size: 12, color: '#e6e6e6', face: 'Inter, system-ui, sans-serif' },
    color: {
      background: '#434343',
      border: '#666666',
      highlight: { background: '#595959', border: '#8c8c8c' },
    },
  }

  // 关系映射：显示关系类型名称
  const RELATION_NAMES = [
    'USES', 'STUDIES', 'ACHIEVES', 'PROPOSES', 'COMPARES_WITH',
    'IMPROVES_UPON', 'EVALUATED_ON', 'HAS_LIMITATION', 'BELONGS_TO',
    'RELATED_TO', 'REPORTS', 'CONTRIBUTES', 'EVALUATES_ON',
  ]
  const relationships: Record<string, any> = {}
  for (const rel of RELATION_NAMES) {
    relationships[rel] = {
      caption: true,
      thickness: '1.5px',
      font: { size: 10, color: '#c4d6f0', background: 'rgba(13,17,23,0.9)', strokeWidth: 0 },
    }
  }

  return {
    containerId,
    neo4j: { serverUrl: uri, serverUser: user, serverPassword: password },
    labels,
    relationships,
    initialCypher: query,
    visConfig: {
      physics: {
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -65,
          centralGravity: 0.005,
          springLength: 180,
          springConstant: 0.06,
          damping: 0.6,
        },
        stabilization: { iterations: 200, updateInterval: 25 },
        minVelocity: 0.5,
      },
      interaction: {
        navigationButtons: true,
        keyboard: { enabled: true, bindToWindow: false },
        hover: true,
        hoverConnectedEdges: true,
        selectConnectedEdges: true,
        dragNodes: true,
        dragView: true,
        zoomView: true,
        multiselect: true,
      },
      edges: {
        arrows: { to: { enabled: true, scaleFactor: 0.7 } },
        smooth: { type: 'continuous', roundness: 0.4 },
        color: { color: 'rgba(255,255,255,0.22)', highlight: 'rgba(102,231,255,0.6)' },
        width: 1.2,
        selectionWidth: 2,
      },
      nodes: {
        shape: 'dot',
        borderWidth: 2,
        borderWidthSelected: 3,
        shadow: { enabled: true, color: 'rgba(0,0,0,0.4)', size: 6 },
        font: { face: 'Inter, system-ui, sans-serif' },
      },
      layout: { improvedLayout: true },
      autoResize: true,
      height: '100%',
      width: '100%',
    },
  }
}

// ============================================================
// 初始化 / 重建 NeoVis 实例
// ============================================================
async function initNeoVis() {
  const query = props.cypherQuery?.trim()
  if (!query) {
    hasQuery.value = false
    errorMsg.value = ''
    loading.value = false
    return
  }
  hasQuery.value = true
  errorMsg.value = ''
  loading.value = true

  // 等待容器渲染
  await nextTick()
  await new Promise(r => setTimeout(r, 120))

  // 销毁旧实例
  destroyInstance()

  // 使用 CDN 加载的全局 NeoVis（window.NeoVis）
  const NeoVis = (window as any).NeoVis
  if (!NeoVis) {
    errorMsg.value = 'neovis.js CDN 未加载，请检查网络连接'
    loading.value = false
    emit('error', errorMsg.value)
    return
  }

  try {
    const config = buildNeoVisConfig(query)
    neoVisInstance = new NeoVis(config)
    neoVisInstance.render()
    loading.value = false

    // 渲染完成后通知父组件
    setTimeout(() => {
      // 验证渲染结果：嵌入的 vis.js network 对象是否存在
      const network = neoVisInstance?._network
      const nodeCount = network?.body?.data?.nodes?.length || 0
      if (nodeCount === 0) {
        errorMsg.value = '查询成功但图谱为空。请确认知识图谱已含内容。'
      }
      emit('ready')
    }, 1200)
  } catch (err: any) {
    errorMsg.value = err?.message || 'neovis.js 初始化失败'
    loading.value = false
    emit('error', errorMsg.value)
  }
}

function destroyInstance() {
  if (neoVisInstance) {
    try {
      // neovis.js 的销毁链路：清除 network → 清除容器
      if (typeof neoVisInstance._network?.destroy === 'function') {
        neoVisInstance._network.destroy()
      }
      if (typeof neoVisInstance.destroy === 'function') {
        neoVisInstance.destroy()
      }
    } catch {
      // 忽略销毁异常
    }
    neoVisInstance = null
  }
}

// ============================================================
// 生命周期
// ============================================================
watch(() => props.cypherQuery, () => {
  initNeoVis()
})

onMounted(() => {
  initNeoVis()
})

onBeforeUnmount(() => {
  destroyInstance()
})

// ============================================================
// 对外暴露
// ============================================================
function fitView() {
  neoVisInstance?._network?.fit?.({ animation: true })
}

function resetView() {
  neoVisInstance?._network?.fit?.({ animation: { duration: 600, easingFunction: 'easeInOutQuad' } })
}

defineExpose({ fitView, resetView })
</script>

<template>
  <div class="graph-canvas-wrapper">
    <!-- 工具栏 -->
    <div class="toolbar" v-if="hasQuery">
      <button class="tool-btn" @click="fitView" title="适应视野">⊞ 适应视野</button>
      <button class="tool-btn" @click="initNeoVis" title="刷新图谱">↻ 刷新</button>
    </div>

    <!-- neovis.js 渲染容器 -->
    <div
      :id="containerId"
      class="neo4j-viz"
      :class="{ loading: !hasQuery }"
    ></div>

    <!-- 占位提示 -->
    <div v-if="!hasQuery || errorMsg" class="empty-state">
      <div class="empty-icon">{{ errorMsg ? '⚠️' : '🔗' }}</div>
      <div class="empty-text">
        {{ errorMsg || '未提供 Cypher 查询语句。请先生成知识图谱。' }}
      </div>
    </div>

    <!-- 加载态 -->
    <div v-if="loading && !errorMsg" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">连接 Neo4j 并渲染图谱…</div>
    </div>

    <!-- 图例 -->
    <div class="legend-bar" v-if="hasQuery">
      <span
        v-for="(cfg, label) in LABEL_COLORS"
        :key="label"
        class="legend-tag"
      >
        <span class="legend-dot" :style="{ background: cfg.background }"></span>
        {{ label }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.graph-canvas-wrapper {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  background: radial-gradient(circle at 50% 40%, rgba(102,231,255,0.08), rgba(255,255,255,0.02));
  border: 1px solid rgba(255,255,255,0.08);
}

/* —— 工具栏 —— */
.toolbar {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 10;
  display: flex;
  gap: 6px;
}
.tool-btn {
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.15);
  background: rgba(13,17,23,0.85);
  color: #9fb1cc;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  backdrop-filter: blur(8px);
}
.tool-btn:hover {
  border-color: rgba(102,231,255,0.45);
  color: #66e7ff;
  background: rgba(102,231,255,0.08);
}

/* —— 画布容器 —— */
.neo4j-viz {
  flex: 1;
  min-height: 480px;
}
.neo4j-viz.loading {
  opacity: 0.3;
  pointer-events: none;
}

/* —— 加载态 —— */
.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(13,17,23,0.6);
  z-index: 5;
  backdrop-filter: blur(4px);
}
.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(255,255,255,0.15);
  border-top-color: #66e7ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.loading-text {
  color: rgba(238,246,255,0.5);
  font-size: 13px;
}

/* —— 占位 —— */
.empty-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  pointer-events: none;
}
.empty-icon {
  font-size: 40px;
  opacity: 0.6;
}
.empty-text {
  color: rgba(238,246,255,0.4);
  font-size: 14px;
  text-align: center;
  max-width: 260px;
  line-height: 1.6;
}

/* —— 图例 —— */
.legend-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  padding: 8px 14px;
  background: rgba(13,17,23,0.7);
  border-top: 1px solid rgba(255,255,255,0.06);
  backdrop-filter: blur(6px);
}
.legend-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #9fb1cc;
  white-space: nowrap;
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
  box-shadow: 0 0 4px currentColor;
}
</style>
