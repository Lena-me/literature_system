<script setup lang="ts">
import { computed } from 'vue'
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
  weakCount: number
  topicCount: number
}

type GraphDisplayState = 'empty' | 'low' | 'normal' | 'weak'
interface GraphDisplayMessage { title: string; description: string; suggestion?: string }

const props = defineProps<{
  graph: LiteratureGraph | null
  selectedPanel: SelectedPanel
  graphStats: GraphStats
  filteredEdges: LiteratureGraphEdge[]
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
}>()

const selectedNode = computed(() => props.selectedPanel.kind === 'node' ? props.selectedPanel.node : null)
const selectedEdge = computed(() => props.selectedPanel.kind === 'edge' ? props.selectedPanel.edge : null)
const isOverview = computed(() => props.selectedPanel.kind === 'summary')

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
</script>

<template>
  <aside class="detail-panel">
    <template v-if="isOverview">
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
          <h3>关系概览</h3>
          <p>当前文献较少，图谱以主要关系和共同线索为重点展示。</p>
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
          <h3>关系较弱</h3>
          <p>当前论文之间尚未形成明确的方法承接或任务链路。</p>
          <p class="muted">可按研究任务、方法路线或应用场景重新组织为更聚焦的图谱。</p>
        </div>

        <div class="panel-section compact-panel">
          <h3>可能原因</h3>
          <ul class="reason-list compact-list">
            <li>主题边界较远。</li>
            <li>关键词重合度较低。</li>
            <li>研究方法或应用场景差异较大。</li>
          </ul>
        </div>

        <div class="panel-section compact-panel organize-section">
          <h3>整理建议</h3>
          <div class="organize-list">
            <span>按研究任务分组</span>
            <span>按方法路线分组</span>
            <span>重新选择同主题论文</span>
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
          <h3>主题线索</h3>
          <div v-if="props.graph?.summary?.themes?.length" class="tag-list">
            <span v-for="theme in props.graph?.summary?.themes?.slice(0, 6)" :key="theme">{{ theme }}</span>
          </div>
          <p v-else class="muted">暂无明确主题，可尝试选择更多同方向论文。</p>
        </div>

        <div class="panel-section">
          <h3>核心论文</h3>
          <button
            v-for="paper in (props.graph?.summary?.core_papers || []).slice(0, 3)"
            :key="paper.paper_id"
            class="related-paper"
            @click="emit('selectCorePaper', paper.paper_id)"
          >
            <strong>{{ paper.title }}</strong>
            <span>{{ paper.label || '论文节点' }}</span>
          </button>
          <p v-if="!props.graph?.summary?.core_papers?.length" class="muted">暂无核心论文。</p>
        </div>

        <div class="panel-section">
          <h3>关系解释</h3>
          <button
            v-for="edge in props.filteredEdges.slice(0, 4)"
            :key="edge.id"
            class="relation-line-item"
            @click="emit('selectEdge', edge)"
          >
            <span>{{ props.edgeLabel(edge) }} · {{ props.strengthText(edge.strength) }}</span>
            <strong>{{ props.findNode(edge.source)?.label || '论文 A' }} - {{ props.findNode(edge.target)?.label || '论文 B' }}</strong>
          </button>
          <p v-if="!props.filteredEdges.length" class="muted">暂无可解释关系，可切换关系类型查看其他关联。</p>
        </div>
      </template>
    </template>

    <template v-else-if="selectedNode">
      <div class="panel-section paper-head">
        <h2 class="paper-title">{{ selectedNode.title }}</h2>
        <p>{{ props.formatAuthors(selectedNode.authors) }}</p>
        <div class="paper-meta-line">
          <span>{{ selectedNode.year || '年份未知' }}</span>
          <span>{{ selectedNode.journal_conf || '来源未知' }}</span>
          <span>{{ props.parseStatusText(selectedNode.parse_status) }}</span>
        </div>
      </div>

      <div class="tag-list compact">
        <span v-for="kw in selectedNode.keywords || []" :key="kw">{{ kw }}</span>
        <span v-if="!(selectedNode.keywords || []).length">暂无关键词</span>
      </div>

      <div class="paper-abstract-block plain-abstract">
        <h3>摘要</h3>
        <p class="long-text">{{ selectedNode.abstract || '该论文暂无摘要信息。' }}</p>
      </div>

      <div class="panel-section">
        <h3>研究要点</h3>
        <dl class="paper-points">
          <dt>研究问题</dt><dd>{{ selectedNode.research_question || '暂无抽取结果' }}</dd>
          <dt>方法</dt><dd>{{ selectedNode.method || '暂无抽取结果' }}</dd>
          <dt>主要结果</dt><dd>{{ selectedNode.main_results || '暂无抽取结果' }}</dd>
        </dl>
      </div>

      <div class="panel-section">
        <h3>相关论文</h3>
        <button
          v-for="edge in props.relatedEdgesForNode(selectedNode)"
          :key="edge.id"
          class="related-paper"
          @click="emit('selectEdge', edge)"
        >
          <strong>{{ props.otherNodeTitle(edge, selectedNode) }}</strong>
          <span>{{ props.edgeLabel(edge) }} · {{ props.strengthText(edge.strength) }}</span>
        </button>
      </div>
    </template>

    <template v-else-if="selectedEdge">
      <div class="panel-section edge-head">
        <p class="eyebrow">关系解释</p>
        <h2>关系解释</h2>
        <p>{{ props.strengthText(selectedEdge.strength) }} · 强度 {{ selectedEdge.score.toFixed(2) }}</p>
      </div>

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
    </template>
  </aside>
</template>

<style scoped>
.detail-panel {
  min-height: 0;
  padding: 12px;
  overflow-y: auto;
  word-break: break-word;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(221, 230, 240, 0.92);
  border-radius: 22px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.045);
  font-size: 13.5px;
}

.eyebrow {
  margin: 0 0 5px;
  color: #6c7f95;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.panel-section {
  padding: 12px 13px;
  margin-bottom: 10px;
  border-radius: 15px;
  background: #fbfdff;
  border: 1px solid #edf3f8;
}

.hero-summary,
.paper-head,
.edge-head {
  background: linear-gradient(135deg, #f7fbff, #f8fffd);
  border-color: #e0edf5;
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

.state-summary,
.hero-summary,
.low-summary,
.normal-summary,
.weak-card {
  background: #fbfdff;
  border-color: #e6edf5;
  box-shadow: none;
}

.state-summary h3 {
  margin: 0 0 10px;
  color: #1a2a42;
  font-size: 14px;
  line-height: 1.25;
  font-weight: 800;
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

.weak-card {
  border-color: #ecd6b3;
  background: #fdfaf4;
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
  padding: 11px;
  border-radius: 14px;
  background: #fff;
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
  padding: 10px 11px;
  margin-top: 7px;
  text-align: left;
  border-radius: 13px;
  background: #fff;
  color: #1e293b;
  border: 1px solid #edf3f8;
  transition: border 0.16s, transform 0.16s, box-shadow 0.16s;
}

.related-paper:hover,
.relation-line-item:hover {
  transform: translateY(-1px);
  border-color: #c8d9ea;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
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
  margin: 0;
  color: #46586b;
  line-height: 1.75;
  white-space: pre-wrap;
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

.edge-papers button {
  min-height: 66px;
  padding: 10px;
  border-radius: 14px;
  background: #fff;
  color: #1e293b;
  border: 1px solid #dce5ee;
  line-height: 1.45;
}

.muted {
  color: #64748b;
  line-height: 1.65;
}

.detail-panel::-webkit-scrollbar {
  width: 6px;
}

.detail-panel::-webkit-scrollbar-thumb {
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
  border-radius: 12px;
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
