<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type {
  LiteratureGraph,
  LiteratureGraphEdge,
  LiteratureGraphNode,
  RelationStrength,
} from '@/api/knowledge'

type SelectedPanel =
  | { kind: 'summary' }
  | { kind: 'node'; node: LiteratureGraphNode }
  | { kind: 'edge'; edge: LiteratureGraphEdge }

interface GraphStats {
  paperCount: number
  relationCount: number
  strongCount: number
  mediumCount: number
  weakCount: number
  topicCount: number
}

type RightPanelMode = 'overview' | 'node' | 'edge' | 'empty'
type EmptyReason = 'insufficient' | 'no_edges' | 'threshold' | 'filter' | 'weak_only' | 'filtered_empty'
type GraphDisplayState = 'empty' | 'low' | 'normal' | 'weak'
interface GraphDisplayMessage { title: string; description: string; suggestion?: string }

const props = defineProps<{
  graph: LiteratureGraph | null
  panelMode: RightPanelMode
  selectedPanel: SelectedPanel
  graphStats: GraphStats
  filteredEdges: LiteratureGraphEdge[]
  totalEdges: number
  emptyReason: EmptyReason
  relationFilter: string
  minScore: number
  hiddenByTypeCount: number
  hiddenByThresholdCount: number
  hasOnlyWeakEdges: boolean
  displayState: GraphDisplayState
  displayMessage: GraphDisplayMessage
  singlePaper: LiteratureGraphNode | null
  formatAuthors: (value?: string | null) => string
  parseStatusText: (status?: string | null) => string
  relatedEdgesForNode: (node: LiteratureGraphNode) => LiteratureGraphEdge[]
  otherNodeTitle: (edge: LiteratureGraphEdge, node: LiteratureGraphNode) => string
  edgeLabel: (edge: LiteratureGraphEdge) => string
  strengthText: (strength?: RelationStrength) => string
  findNode: (id: string | number) => LiteratureGraphNode | undefined
}>()

const emit = defineEmits<{
  (event: 'selectCorePaper', paperId: number): void
  (event: 'selectEdge', edge: LiteratureGraphEdge): void
  (event: 'selectNodeById', id: string | number): void
  (event: 'openPaper', node: LiteratureGraphNode): void
  (event: 'createReport', node: LiteratureGraphNode): void
  (event: 'compareGraph'): void
  (event: 'backToOverview'): void
}>()

const selectedNode = computed(() => props.selectedPanel.kind === 'node' ? props.selectedPanel.node : null)
const selectedEdge = computed(() => props.selectedPanel.kind === 'edge' ? props.selectedPanel.edge : null)
const isOverview = computed(() => props.panelMode === 'overview')
const actionRailExpanded = ref(false)

watch(selectedNode, node => {
  actionRailExpanded.value = false
})

function toggleActionRail() {
  actionRailExpanded.value = !actionRailExpanded.value
}

function runNodeAction(action: 'open' | 'report' | 'compare') {
  if (!selectedNode.value) return
  if (action === 'open') emit('openPaper', selectedNode.value)
  else if (action === 'report') emit('createReport', selectedNode.value)
  else emit('compareGraph')
  actionRailExpanded.value = false
}

const bestEdge = computed(() => [...props.filteredEdges].sort((a, b) => (b.score || 0) - (a.score || 0))[0] || null)
const bestPairLabel = computed(() => {
  if (!bestEdge.value) return '暂无明确最相近论文'
  const source = props.findNode(bestEdge.value.source)
  const target = props.findNode(bestEdge.value.target)
  return `${source?.label || source?.title || '论文 A'} ↔ ${target?.label || target?.title || '论文 B'}`
})
const overviewKeywords = computed(() => {
  if (bestEdge.value) {
    const terms = bestEdge.value.shared_keywords?.length ? bestEdge.value.shared_keywords : bestEdge.value.shared_terms || []
    if (terms.length) return terms.slice(0, 8)
  }
  return props.graph?.summary?.themes?.slice(0, 8) || []
})

const bestRelationTypes = computed(() => {
  return (bestEdge.value?.relation_types || []).slice(0, 5)
})
const splitSuggestions = computed(() => {
  const themes = props.graph?.summary?.themes || []
  if (themes.length) return themes.slice(0, 4).map(theme => `${theme} 相关论文组`)
  return ['方法框架相关论文组', '应用场景相关论文组', '综述与背景论文组']
})

const overviewSummaryText = computed(() => {
  const paperCount = props.graphStats.paperCount || props.graph?.nodes?.length || 0
  const rawName = (props.graph?.name || '').trim()
  const graphName = rawName && !rawName.includes('未命名') ? rawName : '当前主题'
  const corePapers = props.graph?.summary?.core_papers || []
  const coreNames = corePapers
    .slice(0, 2)
    .map(paper => paper.label || paper.title)
    .filter(Boolean)
  const coreText = coreNames.length ? `${coreNames.join(' 与 ')} 为核心节点` : '核心节点已按本地中心性识别'
  return `基于 ${paperCount} 篇本地论文构建的 ${graphName} 研究脉络。${coreText}，关联强度以论文相似为主。`
})

const emptyTitle = computed(() => {
  if (props.totalEdges > 0 && props.filteredEdges.length === 0) return '当前筛选下暂无可见关联'
  return '文献之间的关联较弱'
})

const emptyDescription = computed(() => {
  if (props.totalEdges > 0 && props.filteredEdges.length === 0) {
    return '请尝试切换关联类型，或放宽筛选条件。'
  }
  return '系统暂未发现明显的研究关联，可补充同主题文献后重试。'
})

const coreNodes = computed(() => {
  const degreeMap = new Map<string, number>()
  for (const edge of props.graph?.edges || []) {
    degreeMap.set(String(edge.source), (degreeMap.get(String(edge.source)) || 0) + 1)
    degreeMap.set(String(edge.target), (degreeMap.get(String(edge.target)) || 0) + 1)
  }
  return [...(props.graph?.nodes || [])]
    .sort((a, b) => ((b.centrality || 0) - (a.centrality || 0)) || ((degreeMap.get(String(b.id)) || 0) - (degreeMap.get(String(a.id)) || 0)))
    .slice(0, 3)
})

const weakNodes = computed(() => {
  const weakIds = new Set<string>()
  const strongIds = new Set<string>()
  for (const edge of props.graph?.edges || []) {
    const target = edge.strength === 'weak' ? weakIds : strongIds
    target.add(String(edge.source))
    target.add(String(edge.target))
  }
  return (props.graph?.nodes || []).filter(node => weakIds.has(String(node.id)) && !strongIds.has(String(node.id))).slice(0, 3)
})

function shortTitle(node?: LiteratureGraphNode) {
  const title = node?.label || node?.title || node?.name || '论文节点'
  return title.length > 34 ? `${title.slice(0, 32)}…` : title
}

const relationFilterLabel = computed(() => {
  const labels: Record<string, string> = {
    all: '全部关联',
    strong: '强关联',
    weak: '弱关联',
    semantic: '语义相近',
    keyword: '关键词相近',
    method: '方法相近',
  }
  return labels[props.relationFilter] || '当前筛选'
})

function edgeEvidence(edge: LiteratureGraphEdge) {
  const propsValue = edge.properties || {}
  const raw = propsValue.evidence || propsValue.evidences || propsValue.source_snippets || propsValue.snippets || []
  return Array.isArray(raw) ? raw.map(String).filter(Boolean).slice(0, 3) : String(raw || '').trim() ? [String(raw)] : []
}
</script>

<template>
  <aside class="detail-panel" :class="{ 'node-detail-mode': !!selectedNode }">
    <template v-if="props.panelMode === 'empty'">
      <div class="detail-scroll">
      <div class="panel-section hero-summary state-card">
        <p class="eyebrow">当前状态</p>
        <h2>{{ emptyTitle }}</h2>
        <p>{{ emptyDescription }}</p>
      </div>

      <div v-if="props.totalEdges > 0" class="panel-section">
        <h3>为什么看不到连线</h3>
        <ul class="reason-list compact-list">
          <li v-if="props.relationFilter !== 'all'">当前筛选为「{{ relationFilterLabel }}」。</li>
          <li v-if="props.hasOnlyWeakEdges">当前关联整体偏弱，建议保留浅色虚线作为线索。</li>
          <li v-if="!props.hiddenByThresholdCount && props.relationFilter === 'all'">当前筛选条件下没有可展示的关联。</li>
        </ul>
      </div>

      <div v-else class="panel-section">
        <h3>可能原因</h3>
        <ul class="reason-list compact-list">
          <li>文献主题跨度较大</li>
          <li>研究方法或应用场景不同</li>
          <li>共同关键词较少</li>
          <li>文献数量偏少，线索尚不充分</li>
        </ul>
      </div>

      <div class="panel-section">
        <h3>建议</h3>
        <ol class="advice-list">
          <li v-if="props.relationFilter !== 'all'">切换为「全部关联」查看</li>
          <li>补充同主题、同任务的文献</li>
          <li>按研究方向重新分组后再生成</li>
        </ol>
      </div>

      <div v-if="overviewKeywords.length" class="panel-section">
        <h3>仍可参考的主题线索</h3>
        <div class="tag-list compact">
          <span v-for="kw in overviewKeywords.slice(0, 8)" :key="kw">{{ kw }}</span>
        </div>
      </div>
      </div>
    </template>

    <template v-else-if="isOverview">
      <div class="detail-scroll">
      <template v-if="props.displayState === 'empty'">
        <div class="panel-section hero-summary state-card">
          <p class="eyebrow">当前状态</p>
          <h2>暂不能构建文献关系</h2>
          <p>{{ props.displayMessage.title }}</p>
          <p class="muted">{{ props.displayMessage.description }}</p>
        </div>

        <div class="panel-section progress-card">
          <h3>图谱生成进度</h3>
          <div class="paper-progress"><span :style="{ width: `${Math.min(100, props.graphStats.paperCount * 50)}%` }"></span></div>
          <p>当前 {{ props.graphStats.paperCount }} / 2 篇，继续补充论文后即可生成文献关系。</p>
        </div>

        <div v-if="props.singlePaper" class="panel-section">
          <h3>单篇论文信息</h3>
          <button class="related-paper" @click="emit('selectNodeById', props.singlePaper.id)">
            <strong>{{ props.singlePaper.title }}</strong>
            <span>{{ props.formatAuthors(props.singlePaper.authors) }} · {{ props.singlePaper.year || '年份未知' }}</span>
          </button>
          <p class="long-text">{{ props.singlePaper.abstract || '该论文暂无摘要信息。' }}</p>
        </div>

        <div class="panel-section">
          <h3>下一步建议</h3>
          <ol class="advice-list">
            <li>继续上传或选择同主题论文，至少达到 2 篇。</li>
            <li>优先补充综述、方法论文或同一任务场景论文。</li>
            <li>生成后可点击节点查看论文详情，点击边查看关系解释。</li>
          </ol>
        </div>
      </template>

      <template v-else-if="props.displayState === 'low'">
        <div class="panel-section state-summary low-summary">
          <h3>{{ props.graphStats.paperCount === 2 ? '二元关系分析' : '小规模图谱概览' }}</h3>
          <p v-if="props.graphStats.paperCount === 2">当前为 2 篇论文，重点查看两者是否共享任务、方法或关键词线索。</p>
          <p v-else>当前为 3-5 篇论文，适合观察小组内的共同主题和局部差异。</p>
        </div>

        <div class="panel-section">
          <h3>关系分布</h3>
          <div class="summary-grid compact-stats">
            <div><b>{{ props.totalEdges }}</b><span>全部</span></div>
            <div><b>{{ props.graphStats.strongCount }}</b><span>强</span></div>
            <div><b>{{ props.graphStats.mediumCount }}</b><span>中</span></div>
            <div><b>{{ props.graphStats.weakCount }}</b><span>弱</span></div>
          </div>
        </div>

        <div class="panel-section emphasis-section">
          <h3>最相近论文</h3>
          <p class="long-text">{{ bestPairLabel }}</p>
          <p class="muted">{{ bestEdge ? `关系强度 ${bestEdge.score.toFixed(2)}` : '暂无明确关系强度' }}</p>
        </div>

        <div class="panel-section">
          <h3>关系依据</h3>
          <p class="long-text">{{ bestEdge?.explanation || '系统主要依据共同关键词、语义相似度和研究任务相近性判断论文之间存在关联。' }}</p>
          <div v-if="bestRelationTypes.length" class="tag-list compact relation-tags">
            <span v-for="type in bestRelationTypes" :key="type">{{ type }}</span>
          </div>
        </div>

        <div class="panel-section">
          <h3>共同关键词</h3>
          <div v-if="overviewKeywords.length" class="tag-list">
            <span v-for="kw in overviewKeywords.slice(0, 6)" :key="kw">{{ kw }}</span>
          </div>
          <p v-else class="muted">暂无明确共同关键词。</p>
        </div>

        <p class="compact-suggestion">建议继续补充同主题文献，以获得更稳定的研究脉络。</p>
      </template>

      <template v-else-if="props.displayState === 'weak'">
        <div class="panel-section state-summary weak-card">
          <h3>关联线索较少</h3>
          <p>当前文献之间以浅层关联为主，画布会以虚线保留这些线索。</p>
          <p class="muted">这不代表没有价值，可按研究方向重新聚焦后再看。</p>
        </div>

        <div class="panel-section compact-panel">
          <h3>可能原因</h3>
          <ul class="reason-list compact-list">
            <li>主题边界较远</li>
            <li>共同关键词较少</li>
            <li>方法或应用场景差异较大</li>
          </ul>
        </div>

        <div class="panel-section compact-panel organize-section">
          <h3>整理建议</h3>
          <div class="organize-list">
            <span>按研究任务分组</span>
            <span>按方法路线分组</span>
            <span>补充同主题文献</span>
          </div>
        </div>

        <div class="panel-section compact-panel">
          <h3>关系线索</h3>
          <div v-if="overviewKeywords.length" class="tag-list compact">
            <span v-for="kw in overviewKeywords.slice(0, 6)" :key="kw">{{ kw }}</span>
          </div>
          <p v-else class="muted">当前文献之间暂无稳定共同线索。</p>
        </div>
      </template>

      <template v-else>
        <div class="panel-section state-summary normal-summary">
          <h3>图谱摘要</h3>
          <p>{{ overviewSummaryText }}</p>
        </div>

        <div class="panel-section">
          <h3>关联概况</h3>
          <div class="summary-grid compact-stats">
            <div><b>{{ props.graphStats.paperCount }}</b><span>文献</span></div>
            <div><b>{{ props.graphStats.strongCount }}</b><span>强</span></div>
            <div><b>{{ props.graphStats.mediumCount }}</b><span>中</span></div>
            <div><b>{{ props.graphStats.weakCount }}</b><span>弱</span></div>
          </div>
          <p class="muted">共识别 {{ props.totalEdges }} 组研究关联。</p>
        </div>

        <div class="panel-section">
          <h3>主题线索</h3>
          <div v-if="props.graph?.summary?.themes?.length" class="tag-list">
            <span v-for="theme in props.graph?.summary?.themes?.slice(0, 6)" :key="theme">{{ theme }}</span>
          </div>
          <p v-else class="muted">暂无明确主题，可尝试选择更多同方向论文。</p>
        </div>

        <div class="panel-section">
          <h3>核心文献</h3>
          <button
            v-for="paper in coreNodes"
            :key="paper.id"
            class="related-paper"
            @click="emit('selectNodeById', paper.id)"
          >
            <strong>{{ shortTitle(paper) }}</strong>
            <span>{{ props.formatAuthors(paper.authors) }} · {{ paper.year || '年份未解析' }}</span>
          </button>
          <p v-if="!coreNodes.length" class="muted">暂无核心文献。</p>
        </div>

        <div v-if="weakNodes.length" class="panel-section">
          <h3>关联偏弱文献</h3>
          <button
            v-for="paper in weakNodes"
            :key="paper.id"
            class="related-paper"
            @click="emit('selectNodeById', paper.id)"
          >
            <strong>{{ shortTitle(paper) }}</strong>
            <span>目前仅形成浅层线索</span>
          </button>
        </div>

        <div class="panel-section">
          <h3>关联说明</h3>
          <button
            v-for="edge in props.filteredEdges.slice(0, 4)"
            :key="edge.id"
            class="relation-line-item"
            @click="emit('selectEdge', edge)"
          >
            <span>{{ props.edgeLabel(edge) }} · {{ props.strengthText(edge.strength) }}</span>
            <strong>{{ props.findNode(edge.source)?.label || '论文 A' }} - {{ props.findNode(edge.target)?.label || '论文 B' }}</strong>
          </button>
          <p v-if="!props.filteredEdges.length" class="muted">暂无可展示的关联说明，可切换筛选条件查看。</p>
        </div>
      </template>
      </div>
    </template>

    <template v-else-if="selectedNode">
      <div class="detail-scroll node-detail-body">
        <button type="button" class="back-link node-back-link" @click="emit('backToOverview')">← 返回概览</button>

        <div class="paper-head-flat">
          <h2 class="paper-title">{{ selectedNode.title }}</h2>
          <p class="paper-authors">{{ props.formatAuthors(selectedNode.authors) }}</p>
          <div class="paper-meta-line">
            <span>{{ selectedNode.year || '年份待补充' }}</span>
            <span>{{ selectedNode.journal_conf || '来源待补充' }}</span>
            <span>{{ props.parseStatusText(selectedNode.parse_status) }}</span>
          </div>
        </div>

        <div class="tag-list compact">
          <span v-for="kw in selectedNode.keywords || []" :key="kw">{{ kw }}</span>
          <span v-if="!(selectedNode.keywords || []).length" class="tag-muted">暂无关键词</span>
        </div>

        <section class="detail-block">
          <h3>摘要</h3>
          <p class="long-text readable-text">{{ selectedNode.abstract || '该论文暂无摘要信息。' }}</p>
        </section>

        <section class="detail-block detail-block-last">
          <h3>研究要点</h3>
          <dl class="paper-points-flat">
            <div class="point-row">
              <dt>研究问题</dt>
              <dd>{{ selectedNode.research_question || '-' }}</dd>
            </div>
            <div class="point-row">
              <dt>方法</dt>
              <dd>{{ selectedNode.method || '-' }}</dd>
            </div>
            <div class="point-row">
              <dt>主要结果</dt>
              <dd>{{ selectedNode.main_results || '-' }}</dd>
            </div>
          </dl>
        </section>
      </div>

      <div
        class="detail-action-rail"
        :class="{ expanded: actionRailExpanded }"
        aria-label="快捷操作"
      >
        <button
          type="button"
          class="detail-action-rail-handle"
          :aria-expanded="actionRailExpanded"
          aria-label="展开或收起快捷操作"
          @click.stop="toggleActionRail"
        >
          <span class="handle-bar" />
          <span class="handle-bar" />
          <span class="handle-bar" />
        </button>
        <div class="detail-action-rail-menu">
          <button type="button" class="detail-action-tab" @click="runNodeAction('open')">打开论文原文</button>
          <button type="button" class="detail-action-tab" @click="runNodeAction('report')">生成研读报告</button>
          <button type="button" class="detail-action-tab" @click="runNodeAction('compare')">加入多文献对比</button>
        </div>
      </div>
    </template>

    <template v-else-if="selectedEdge">
      <header class="detail-topbar edge-topbar">
        <button type="button" class="back-link" @click="emit('backToOverview')">← 返回概览</button>
        <p class="eyebrow">关系解释</p>
        <h2 class="edge-title">{{ props.strengthText(selectedEdge.strength) }} · 强度 {{ selectedEdge.score.toFixed(2) }}</h2>
      </header>

      <div class="detail-scroll">
      <div class="edge-papers">
        <button @click="emit('selectNodeById', selectedEdge.source)">
          {{ props.findNode(selectedEdge.source)?.title || '论文 A' }}
        </button>
        <span>↔</span>
        <button @click="emit('selectNodeById', selectedEdge.target)">
          {{ props.findNode(selectedEdge.target)?.title || '论文 B' }}
        </button>
      </div>

      <div class="panel-section">
        <h3>关系类型</h3>
        <div class="tag-list compact">
          <span v-for="type in selectedEdge.relation_types || []" :key="type">{{ type }}</span>
        </div>
      </div>

      <div class="panel-section">
        <h3>共同线索</h3>
        <div class="tag-list compact">
          <span v-for="kw in (selectedEdge.shared_keywords?.length ? selectedEdge.shared_keywords : selectedEdge.shared_terms || [])" :key="kw">{{ kw }}</span>
          <span v-if="!(selectedEdge.shared_keywords?.length || selectedEdge.shared_terms?.length)">暂无共同关键词</span>
        </div>
      </div>

      <div class="panel-section">
        <h3>关联原因</h3>
        <p class="long-text">{{ selectedEdge.explanation || '系统根据文本相似度和关键词线索判断两篇论文存在关联。' }}</p>
      </div>

      <div class="panel-section">
        <h3>差异提示</h3>
        <p class="long-text">{{ selectedEdge.difference || '建议结合原文进一步比较两篇论文的研究问题、方法与实验设置。' }}</p>
      </div>

      <div v-if="edgeEvidence(selectedEdge).length" class="panel-section">
        <h3>证据片段</h3>
        <p v-for="snippet in edgeEvidence(selectedEdge)" :key="snippet" class="long-text evidence-snippet">{{ snippet }}</p>
      </div>

      <div class="panel-section">
        <h3>操作</h3>
        <div class="action-stack inline-actions">
          <button type="button" class="action-secondary" @click="emit('selectEdge', selectedEdge)">查看证据</button>
          <button type="button" class="action-secondary" @click="emit('compareGraph')">加入对比</button>
        </div>
      </div>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.detail-panel {
  --graph-blue: #2563eb;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  word-break: break-word;
  background: #fff;
  border: none;
  border-radius: 0;
  box-shadow: none;
  font-size: 13.5px;
}

.detail-panel.node-detail-mode {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18px;
  align-items: stretch;
  overflow: hidden;
}

.detail-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px 20px;
}

.detail-topbar {
  flex-shrink: 0;
  padding: 12px 16px;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
}

.edge-topbar .edge-title {
  margin: 6px 0 0;
  color: #14233b;
  font-size: 16px;
  line-height: 1.3;
}

.back-link {
  display: inline-flex;
  align-items: center;
  margin-bottom: 10px;
  padding: 0;
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.back-link:hover {
  color: #2563eb;
}

.node-back-link {
  margin-bottom: 12px;
}

.detail-action-rail {
  position: relative;
  grid-column: 2;
  grid-row: 1;
  align-self: center;
  z-index: 30;
  pointer-events: auto;
}

.detail-action-rail-handle,
.detail-action-rail-menu {
  pointer-events: auto;
}

.detail-action-rail-handle {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: 18px;
  min-height: 96px;
  padding: 12px 0;
  border: none;
  border-radius: 10px 0 0 10px;
  background: #dbeafe;
  cursor: pointer;
  box-shadow: -2px 0 10px rgba(37, 99, 235, 0.12);
  transition: background 0.15s ease;
}

.detail-action-rail-handle:hover {
  background: #bfdbfe;
}

.detail-action-rail-handle .handle-bar {
  display: block;
  width: 3px;
  height: 16px;
  border-radius: 999px;
  background: #2563eb;
  opacity: 0.85;
}

.detail-action-rail-menu {
  position: absolute;
  top: 50%;
  right: calc(100% + 8px);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 136px;
  padding: 10px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px 0 0 10px;
  box-shadow: -8px 0 28px rgba(15, 23, 42, 0.1);
  opacity: 0;
  pointer-events: none;
  transform: translateY(-50%) translateX(12px);
  transition:
    transform 0.32s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.24s ease;
}

.detail-action-rail.expanded .detail-action-rail-menu {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(-50%) translateX(0);
}

.detail-action-tab {
  padding: 9px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.detail-action-tab:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #2563eb;
}

.node-detail-body {
  grid-column: 1;
  grid-row: 1;
  position: relative;
  z-index: 1;
  min-height: 0;
  padding-right: 16px;
}

.detail-block {
  padding-bottom: 0;
  margin-bottom: 20px;
  border-bottom: none;
}

.detail-block:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.detail-block h3 {
  margin: 0 0 12px;
  padding-left: 10px;
  border-left: 3px solid var(--graph-blue);
  color: #475569;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
}

.section-hint {
  margin: 0 0 12px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.paper-head-flat {
  margin-bottom: 12px;
}

.paper-authors {
  margin: 0 0 10px;
  color: #506173;
  font-size: 13px;
  line-height: 1.55;
}

.paper-points-flat {
  margin: 0;
}

.point-row {
  margin-bottom: 16px;
  padding: 0;
}

.point-row:last-child {
  margin-bottom: 0;
}

.point-row dt {
  margin: 0 0 8px;
  padding-left: 10px;
  border-left: 3px solid var(--graph-blue);
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.point-row dd {
  margin: 0;
  color: #334155;
  font-size: 13.5px;
  line-height: 1.8;
}

.action-stack {
  display: grid;
  gap: 10px;
}

.action-primary,
.action-secondary {
  width: 100%;
  min-height: 40px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.action-primary {
  border: 1px solid #2563eb;
  background: #2563eb;
  color: #fff;
}

.action-primary:hover {
  background: #1d4ed8;
  border-color: #1d4ed8;
}

.action-secondary {
  border: 1px solid #dbe7f3;
  background: #fff;
  color: #2563eb;
}

.action-secondary:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.inline-actions {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.tag-muted {
  background: #f1f5f9 !important;
  color: #94a3b8 !important;
}

.eyebrow {
  margin: 0 0 5px;
  color: #6c7f95;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.panel-section {
  padding: 0 0 14px;
  margin-bottom: 14px;
  border: none;
  border-bottom: 1px solid #edf3f8;
  border-radius: 0;
  background: transparent;
}

.panel-section:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.hero-summary,
.paper-head,
.edge-head,
.state-summary,
.low-summary,
.normal-summary,
.weak-card,
.emphasis-section,
.progress-card,
.organize-section {
  background: transparent;
  border: none;
  box-shadow: none;
}

.panel-section h2,
.panel-section h3 {
  margin: 0 0 9px;
  color: #14233b;
}

.panel-section h2 {
  font-size: 18px;
  line-height: 1.2;
}

.panel-section h3 {
  font-size: 14px;
  line-height: 1.25;
}

.state-summary h3 {
  margin: 0 0 10px;
  color: #1a2a42;
  font-size: 14px;
  line-height: 1.25;
  font-weight: 800;
}

.weak-card {
  border-bottom: 1px solid #edf3f8;
}

.paper-head .tag-list {
  margin-bottom: 16px;
}

.paper-title {
  margin-bottom: 10px;
  line-height: 1.22;
}

.plain-abstract {
  padding: 2px 0 0;
  margin: 0 0 14px;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
}

.compact-panel {
  min-height: 0;
}

.low-summary p,
.normal-summary p,
.weak-card p {
  color: #506173;
  font-size: 13px;
  line-height: 1.6;
}

.panel-section p {
  margin-top: 0;
  font-size: 13px;
}

.source-note strong {
  display: block;
  margin-bottom: 6px;
  color: #253449;
}

.source-note p {
  margin: 0;
  color: #64748b;
  line-height: 1.65;
  font-size: 13px;
}

.encoding-row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: -2px 0 12px;
}

.encoding-row span {
  padding: 6px 9px;
  border-radius: 999px;
  background: #f1f7fb;
  border: 1px solid #e1ebf4;
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
}

.summary-grid,
.two-metrics {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 10px;
}

.summary-grid.compact-stats {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.summary-grid.inline-stats {
  margin-bottom: 10px;
}

.summary-grid div,
.two-metrics div {
  padding: 10px;
  border-radius: 6px;
  background: #f8fafc;
  border: 1px solid #edf3f8;
}

.summary-grid.compact-stats div {
  padding: 9px 7px;
  text-align: center;
}

.summary-grid b,
.two-metrics b {
  display: block;
  color: #0f6b83;
  font-size: 22px;
}

.summary-grid.compact-stats b {
  font-size: 18px;
}

.summary-grid span,
.two-metrics span {
  color: #7d8b9c;
  font-size: 12px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 10px 0 8px;
}

.tag-list span {
  padding: 5px 9px;
  border-radius: 999px;
  background: #e8faf7;
  color: #0f766e;
  font-size: 11.5px;
  font-weight: 800;
}

.tag-list.compact span {
  padding: 5px 8px;
  font-size: 11px;
}

.related-paper,
.relation-line-item,
.edge-papers button {
  border: none;
  cursor: pointer;
  font-family: inherit;
}

.related-paper,
.relation-line-item {
  width: 100%;
  padding: 10px 12px;
  margin-top: 8px;
  text-align: left;
  border-radius: 6px;
  background: #f8fafc;
  color: #1e293b;
  border: 1px solid #edf3f8;
  transition: border-color 0.16s, background 0.16s;
}

.related-paper:hover,
.relation-line-item:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.related-paper strong,
.relation-line-item strong {
  display: block;
  line-height: 1.4;
}

.related-paper span,
.relation-line-item span {
  display: block;
  margin-bottom: 4px;
  color: #6b7d93;
  font-size: 12px;
  font-weight: 750;
}

.paper-meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.paper-meta-line span {
  padding: 5px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #557086;
  font-size: 12px;
}

.long-text {
  margin: 0 0 16px;
  color: #46586b;
  line-height: 1.8;
  white-space: pre-wrap;
}

.readable-text:last-child {
  margin-bottom: 0;
}

.paper-points {
  margin: 0;
}

.paper-points dt {
  margin-top: 10px;
  color: #1e293b;
  font-weight: 850;
}

.paper-points dd {
  margin: 4px 0 0;
  color: #5b6c7d;
  line-height: 1.65;
}

.edge-papers {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.action-row button {
  border: 1px solid #dbe7f3;
  border-radius: 10px;
  background: #fff;
  color: #2563eb;
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
  padding: 8px 10px;
}

.action-row button:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.evidence-snippet {
  padding: 9px 10px;
  margin-top: 8px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #edf3f8;
}

.edge-papers button {
  min-height: 66px;
  padding: 10px 12px;
  border-radius: 6px;
  background: #f8fafc;
  color: #1e293b;
  border: 1px solid #dce5ee;
  line-height: 1.45;
}

.muted {
  color: #64748b;
  line-height: 1.65;
}

.detail-scroll::-webkit-scrollbar {
  width: 6px;
}

.detail-scroll::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 999px;
}


.state-card h2,
.weak-card h2 {
  margin-bottom: 8px;
}

.progress-card p {
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.6;
}

.paper-progress {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e8f0;
}

.paper-progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2563eb, #14b8a6);
}

.advice-list,
.reason-list {
  margin: 0;
  padding-left: 18px;
  color: #526175;
  line-height: 1.75;
}

.weak-card {
  background: #fbfdff;
  border-color: #edf3f8;
  border-left: none;
}

.priority-actions {
  background: linear-gradient(135deg, #f8fbff, #eef6ff);
  border-color: #cfe0ff;
}

.split-section .split-pill:nth-of-type(n + 4) {
  display: none;
}

.emphasis-section {
  background: linear-gradient(135deg, #f8fbff, #eff6ff);
  border-color: #cfe0ff;
}

.relation-tags {
  margin-top: 10px;
}

.action-section strong {
  display: inline-flex;
  margin-bottom: 8px;
  padding: 5px 9px;
  border-radius: 999px;
  background: #dcfce7;
  color: #0f766e;
  font-size: 12px;
}

.action-pill {
  width: 100%;
  margin-top: 7px;
  padding: 9px 12px;
  border-radius: 13px;
  border: 1px solid #dbe6f0;
  background: #fff;
  color: #334155;
  font-weight: 850;
  font-family: inherit;
}

.action-pill.primary {
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  color: #fff;
  border-color: transparent;
}

.split-pill {
  display: block;
  width: 100%;
  margin-top: 7px;
  padding: 8px 11px;
  border: 1px solid #e2e8f0;
  border-radius: 13px;
  background: #fff;
  color: #1e293b;
  text-align: left;
  font-weight: 800;
  cursor: default;
}


.paper-abstract-block {
  padding: 4px 2px 14px;
  margin-bottom: 10px;
  border-bottom: 1px solid #edf3f8;
}

.paper-abstract-block h3 {
  margin: 0 0 8px;
  color: #14233b;
  font-size: 14px;
}

.compact-suggestion {
  margin: 2px 2px 0;
  color: #64748b;
  font-size: 12.5px;
  line-height: 1.6;
}

.organize-section {
  background: #fbfdff;
}

.organize-list {
  display: grid;
  gap: 8px;
}

.organize-list span {
  padding: 8px 10px;
  border-radius: 6px;
  background: #f4f8fb;
  color: #344960;
  font-size: 12.5px;
  font-weight: 780;
}

.compact-list li {
  margin-bottom: 4px;
}


.normal-summary p {
  margin-bottom: 0;
  color: #40566c;
  font-size: 13.5px;
  line-height: 1.58;
}

.plain-abstract .long-text {
  color: #43556a;
  font-size: 13.5px;
  line-height: 1.68;
}

.paper-points {
  display: grid;
  gap: 0;
}

.paper-points dt {
  margin-top: 8px;
  padding: 10px 11px 2px;
  color: #1e293b;
  font-size: 13px;
  font-weight: 850;
  background: #fff;
  border: 1px solid #edf3f8;
  border-bottom: 0;
  border-radius: 13px 13px 0 0;
}

.paper-points dd {
  margin: 0;
  padding: 0 11px 10px;
  color: #5b6c7d;
  font-size: 13px;
  line-height: 1.55;
  background: #fff;
  border: 1px solid #edf3f8;
  border-top: 0;
  border-radius: 0 0 13px 13px;
}

.reason-list {
  font-size: 13px;
  line-height: 1.55;
}

.compact-list li {
  margin-bottom: 3px;
}

.organize-list {
  gap: 6px;
}

.organize-list span {
  padding: 7px 9px;
  font-size: 12.5px;
  background: #f6f9fc;
}

@media (max-width: 1180px) {
  .detail-panel {
    min-height: 320px;
  }
  .summary-grid.compact-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
