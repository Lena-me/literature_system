<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import GraphCanvas from './components/GraphCanvas.vue'
import GraphRightPanel from './components/GraphRightPanel.vue'
import GraphWorkbench from './components/GraphWorkbench.vue'
import { knowledgeApi } from '@/api/knowledge'
import type {
  BuildMode,
  GraphListItem,
  LiteratureGraph,
  LiteratureGraphEdge,
  LiteratureGraphNode,
  RelationStrength,
} from '@/api/knowledge'
import { papersApi } from '@/api/papers'
import type { KnowledgeDomain, Paper } from '@/types/domain'

interface LibraryPaper extends Paper {
  abstract?: string | null
  year?: number | null
}

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

type LeftTab = 'all' | 'recent' | 'topic'
type RelationFilter = 'all' | 'strong' | 'weak' | 'semantic' | 'keyword' | 'method'
type SelectedPanel =
  | { kind: 'summary' }
  | { kind: 'node'; node: LiteratureGraphNode }
  | { kind: 'edge'; edge: LiteratureGraphEdge }

type RightPanelMode = 'overview' | 'node' | 'edge' | 'empty'
type GraphDisplayState = 'empty' | 'low' | 'normal' | 'weak'
interface GraphDisplayMessage { title: string; description: string; suggestion?: string }
type WizardStep = 1 | 2 | 3 | 4

const route = useRoute()
const router = useRouter()

const graphs = ref<GraphListItem[]>([])
const topics = ref<KnowledgeDomain[]>([])
const papers = ref<LibraryPaper[]>([])
const graph = ref<LiteratureGraph | null>(null)
const loading = ref(false)
const creating = ref(false)
const deletingGraphIds = ref<Set<number>>(new Set())
const sidebarCollapsed = ref(false)
const sidebarHovered = ref(false)
const leftTab = ref<LeftTab>('all')
const graphSearch = ref('')
const activeTopicId = ref<number | null>(null)
const selectedPanel = ref<SelectedPanel>({ kind: 'summary' })
const relationFilter = ref<RelationFilter>('all')
const DEFAULT_RELATION_SCORE = 0.05
const minScore = ref(DEFAULT_RELATION_SCORE)
const showCreateDialog = ref(false)
const wizardStep = ref<WizardStep>(1)
const selectedPaperIds = ref<number[]>([])
const paperSearch = ref('')
const formName = ref('')
const nameLoading = ref(false)
const formTopicName = ref('')
const formTopicId = ref<number | null>(null)
const formDescription = ref('')
const buildMode = ref<BuildMode>('fast')
const includeWeak = ref(true)
const generationStep = ref(0)

const generationSteps = [
  '读取论文元数据',
  '计算论文相似度',
  '识别关系类型',
  '生成图谱布局',
  '生成图谱摘要',
]

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const graphTitle = computed(() => graph.value?.name || '文献关系图谱')
const graphSummary = computed(() => graph.value?.summary)
const libraryStats = computed(() => ({
  graphCount: graphs.value.length,
  topicCount: topics.value.length,
  paperCount: papers.value.length,
}))

const filteredGraphs = computed(() => {
  const query = graphSearch.value.trim().toLowerCase()
  let list = graphs.value
  if (leftTab.value === 'recent') {
    list = [...list].sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
  }
  if (leftTab.value === 'topic' && activeTopicId.value) {
    list = list.filter(item => item.domain_id === activeTopicId.value)
  }
  if (query) {
    list = list.filter(item => {
      const name = item.name.toLowerCase()
      const topic = (item.domain_name || '').toLowerCase()
      return name.includes(query) || topic.includes(query)
    })
  }
  return list
})

const filteredPapers = computed(() => {
  const query = paperSearch.value.trim().toLowerCase()
  if (!query) return papers.value
  return papers.value.filter(p => {
    const title = paperTitle(p).toLowerCase()
    const authors = normalizeText(p.authors).toLowerCase()
    const keywords = normalizeTerms(p.keywords).join(' ').toLowerCase()
    return title.includes(query) || authors.includes(query) || keywords.includes(query)
  })
})

const selectedPapers = computed(() => {
  const selected = new Set(selectedPaperIds.value)
  return papers.value.filter(paper => selected.has(paper.id))
})

const canCreateInlineGraph = computed(() => selectedPaperIds.value.length >= 2 && !creating.value && !nameLoading.value)

const createButtonHint = computed(() => {
  if (creating.value) return '正在生成图谱，请稍候…'
  const count = selectedPaperIds.value.length
  if (count < 2) {
    return count === 0
      ? '请至少选择 2 篇论文（知识图谱无次数限制）'
      : `已选 ${count} 篇，还需再选 ${2 - count} 篇`
  }
  if (!formName.value.trim()) return '未填写名称时将由 AI 自动生成，也可先点击「AI 生成名称」'
  return '准备就绪，点击生成文献关系图谱'
})

const yearRange = computed<[number, number]>(() => {
  const years = graph.value?.nodes.map(n => n.year).filter((y): y is number => typeof y === 'number') || []
  if (!years.length) return [2020, 2026]
  return [Math.min(...years), Math.max(...years)]
})

const nodeMap = computed(() => {
  const map = new Map<string, LiteratureGraphNode>()
  for (const node of graph.value?.nodes || []) map.set(String(node.id), node)
  return map
})

const filteredEdges = computed(() => {
  const edges = graph.value?.edges || []
  return edges.filter(edge => {
    if ((edge.score || 0) < minScore.value) return false
    if (relationFilter.value === 'all') return true
    if (relationFilter.value === 'strong') return edge.strength === 'strong'
    if (relationFilter.value === 'weak') return edge.strength === 'weak'
    const types = edge.relation_types || []
    if (relationFilter.value === 'semantic') return types.includes('语义相似')
    if (relationFilter.value === 'keyword') return types.includes('关键词重合')
    if (relationFilter.value === 'method') return types.includes('方法相近')
    return true
  })
})

const totalEdges = computed(() => graph.value?.edges.length || 0)
const mediumEdgeCount = computed(() => graph.value?.edges.filter(edge => edge.strength === 'medium').length || 0)
const hiddenByThresholdCount = computed(() =>
  graph.value?.edges.filter(edge => (edge.score || 0) < minScore.value).length || 0
)
const hiddenByTypeCount = computed(() => {
  if (relationFilter.value === 'all') return 0
  const edges = graph.value?.edges || []
  return edges.filter(edge => {
    if ((edge.score || 0) < minScore.value) return false
    const types = edge.relation_types || []
    if (relationFilter.value === 'strong') return edge.strength !== 'strong'
    if (relationFilter.value === 'weak') return edge.strength !== 'weak'
    if (relationFilter.value === 'semantic') return !types.includes('语义相似')
    if (relationFilter.value === 'keyword') return !types.includes('关键词重合')
    if (relationFilter.value === 'method') return !types.includes('方法相近')
    return false
  }).length
})
const hasOnlyWeakEdges = computed(() =>
  totalEdges.value > 0 && (graph.value?.edges || []).every(edge => edge.strength === 'weak')
)

const connectedNodeIds = computed(() => {
  const ids = new Set<string>()
  for (const edge of filteredEdges.value) {
    ids.add(String(edge.source))
    ids.add(String(edge.target))
  }
  return ids
})

const layoutNodes = computed<LayoutNode[]>(() => {
  const nodes = graph.value?.nodes || []
  const width = 960
  const height = 640
  const cx = width / 2
  const cy = height / 2
  if (!nodes.length) return []

  const sorted = [...nodes].sort((a, b) => {
    const ya = a.year || 9999
    const yb = b.year || 9999
    if (ya !== yb) return ya - yb
    return (b.centrality || 0) - (a.centrality || 0)
  })

  if (nodes.length === 1) {
    const only = nodes[0]
    return [{ ...only, x: cx, y: cy, radius: nodeRadius(only), color: nodeColor(only.year) }]
  }

  if (nodes.length === 2) {
    return sorted.map((node, index) => ({
      ...node,
      x: cx + (index === 0 ? -190 : 190),
      y: cy,
      radius: nodeRadius(node),
      color: nodeColor(node.year),
    }))
  }

  const core = [...nodes].sort((a, b) => (b.centrality || 0) - (a.centrality || 0))[0]
  const coreId = nodes.length > 5 && totalEdges.value > 0 ? String(core.id) : ''
  const ringNodes = coreId ? sorted.filter(n => String(n.id) !== coreId) : sorted
  const count = nodes.length
  const radiusX = count <= 5 ? 240 : count <= 8 ? 300 : count <= 12 ? 360 : count <= 16 ? 430 : 500
  const radiusY = count <= 5 ? 180 : count <= 8 ? 210 : count <= 12 ? 260 : count <= 16 ? 310 : 360

  const positioned: LayoutNode[] = []
  if (coreId) {
    positioned.push({ ...core, x: cx, y: cy, radius: nodeRadius(core), color: nodeColor(core.year) })
  }

  ringNodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(1, ringNodes.length)
    const centralityOffset = 1 - Math.min(0.28, (node.centrality || 0) * 0.18)
    const jitter = ringNodes.length > 8 ? ((index % 3) - 1) * 18 : 0
    positioned.push({
      ...node,
      x: cx + Math.cos(angle) * radiusX * centralityOffset,
      y: cy + Math.sin(angle) * radiusY * centralityOffset + jitter,
      radius: nodeRadius(node),
      color: nodeColor(node.year),
    })
  })

  return positioned
})

const layoutNodeMap = computed(() => {
  const map = new Map<string, LayoutNode>()
  for (const node of layoutNodes.value) map.set(String(node.id), node)
  return map
})


const layoutEdges = computed<LayoutEdge[]>(() => {
  const map = layoutNodeMap.value
  const rows: LayoutEdge[] = []
  for (const edge of filteredEdges.value) {
    const source = map.get(String(edge.source))
    const target = map.get(String(edge.target))
    if (!source || !target) continue
    rows.push({ ...edge, x1: source.x, y1: source.y, x2: target.x, y2: target.y })
  }
  return rows
})

const selectedNodeIds = computed(() => {
  const ids = new Set<string>()
  if (selectedPanel.value.kind === 'node') {
    const nodeId = String(selectedPanel.value.node.id)
    ids.add(nodeId)
    for (const edge of filteredEdges.value) {
      if (String(edge.source) === nodeId) ids.add(String(edge.target))
      if (String(edge.target) === nodeId) ids.add(String(edge.source))
    }
  }
  if (selectedPanel.value.kind === 'edge') {
    ids.add(String(selectedPanel.value.edge.source))
    ids.add(String(selectedPanel.value.edge.target))
  }
  return ids
})

const graphStats = computed(() => ({
  paperCount: graphSummary.value?.paper_count ?? graph.value?.nodes.length ?? 0,
  relationCount: graphSummary.value?.relation_count ?? graph.value?.edges.length ?? 0,
  strongCount: graphSummary.value?.strong_count ?? graph.value?.edges.filter(e => e.strength === 'strong').length ?? 0,
  mediumCount: mediumEdgeCount.value,
  weakCount: graphSummary.value?.weak_count ?? graph.value?.edges.filter(e => e.strength === 'weak').length ?? 0,
  topicCount: graphSummary.value?.topic_count ?? 0,
}))

const graphDisplayState = computed<GraphDisplayState>(() => {
  const paperCount = graphStats.value.paperCount
  if (paperCount < 2) return 'empty'
  if (paperCount <= 5) return 'low'
  if (graphStats.value.strongCount === 0) return 'weak'
  return 'normal'
})

const graphDisplayMessage = computed<GraphDisplayMessage>(() => {
  if (graphDisplayState.value === 'empty') {
    return {
      title: '当前图谱至少需要 2 篇论文才能生成文献关系。',
      description: '请继续上传论文，或选择更多文献加入图谱。',
      suggestion: '单篇论文仍可查看摘要、关键词、研究问题、方法与贡献。',
    }
  }
  if (graphDisplayState.value === 'low') {
    return {
      title: '当前图谱文献数量较少，已采用紧凑关系图展示。',
      description: '图谱仅作为辅助视图，建议重点查看论文间的关系解释、共同关键词与差异点。',
      suggestion: '建议继续补充同主题文献，以获得更稳定的研究脉络。',
    }
  }
  if (graphDisplayState.value === 'weak') {
    return {
      title: '未发现强关联关系，已按主题相近度展示弱连接。',
      description: '这些论文可能分属不同研究方向，建议拆分为多个图谱。',
      suggestion: '可根据方法、任务或应用场景将当前论文拆成更聚焦的文献组。',
    }
  }
  return {
    title: '当前图谱已生成完整文献关系网络。',
    description: '可通过节点、边和右侧洞察面板查看核心论文、主题线索与关系解释。',
  }
})

const singlePaperForState = computed(() => graph.value?.nodes?.[0] ?? null)

// 右侧面板状态机：未选中节点时显示图谱级洞察；点击节点后显示论文详情；点击边后显示关系解释。
const rightPanelMode = computed<RightPanelMode>(() => {
  if (selectedPanel.value.kind === 'node') return 'node'
  if (selectedPanel.value.kind === 'edge') return 'edge'
  if (graph.value && graphStats.value.paperCount >= 2 && filteredEdges.value.length === 0) return 'empty'
  return 'overview'
})
const selectedNodeForPanel = computed(() => selectedPanel.value.kind === 'node' ? selectedPanel.value.node : null)
const selectedEdgeForPanel = computed(() => selectedPanel.value.kind === 'edge' ? selectedPanel.value.edge : null)
const isGraphOverview = computed(() => rightPanelMode.value === 'overview')
const isPaperDetail = computed(() => rightPanelMode.value === 'node')
const isRelationDetail = computed(() => rightPanelMode.value === 'edge')

const emptyPanelReason = computed(() => {
  if (!graph.value || graphStats.value.paperCount < 2) return 'insufficient'
  if (totalEdges.value === 0) return 'no_edges'
  if (filteredEdges.value.length === 0 && hiddenByThresholdCount.value >= totalEdges.value) return 'threshold'
  if (filteredEdges.value.length === 0 && relationFilter.value !== 'all') return 'filter'
  if (hasOnlyWeakEdges.value) return 'weak_only'
  return 'filtered_empty'
})

onMounted(async () => {
  await Promise.all([loadTopics(), loadGraphs(), loadPapers()])
  const id = Number(route.query.id)
  if (Number.isFinite(id) && id > 0) await openGraph(id)
})

async function loadTopics() {
  try {
    topics.value = await knowledgeApi.listDomains()
  } catch {
    topics.value = []
  }
}

async function loadGraphs() {
  try {
    graphs.value = await knowledgeApi.list()
  } catch {
    graphs.value = []
  }
}

async function loadPapers() {
  try {
    const res = await papersApi.list({ limit: 200 })
    papers.value = Array.isArray(res) ? res as LibraryPaper[] : []
  } catch {
    papers.value = []
  }
}

async function openGraph(id: number) {
  showCreateDialog.value = false
  loading.value = true
  try {
    graph.value = await knowledgeApi.get(id)
    selectSummary()
    router.replace({ query: { id } })
  } catch {
    ElMessage.error('图谱加载失败')
  } finally {
    loading.value = false
  }
}

const createHomePanelRef = ref<HTMLElement | null>(null)

function openCreateDialog() {
  wizardStep.value = 1
  selectedPaperIds.value = []
  paperSearch.value = ''
  formName.value = ''
  formDescription.value = ''
  formTopicName.value = ''
  formTopicId.value = activeTopicId.value
  buildMode.value = 'fast'
  includeWeak.value = true
  generationStep.value = 0
  showCreateDialog.value = false
  graph.value = null
  selectedPanel.value = { kind: 'summary' }
  router.replace({ query: {} }).finally(() => {
    nextTick(() => {
      createHomePanelRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  })
}

function closeCreateDialog() {
  if (creating.value) return
  showCreateDialog.value = false
}

function togglePaper(id: number) {
  const index = selectedPaperIds.value.indexOf(id)
  if (index >= 0) selectedPaperIds.value.splice(index, 1)
  else selectedPaperIds.value.push(id)
}

function setTopicFromId(id: number | null) {
  formTopicId.value = id
  if (id) {
    const topic = topics.value.find(t => t.id === id)
    formTopicName.value = topic?.name || ''
  } else {
    formTopicName.value = ''
  }
}

async function ensureTopicId(): Promise<number | null> {
  const topicName = formTopicName.value.trim()
  if (!topicName) return formTopicId.value || null
  const existing = topics.value.find(t => t.name.trim().toLowerCase() === topicName.toLowerCase())
  if (existing) return existing.id
  const created = await knowledgeApi.createDomain({
    name: topicName,
    description: formDescription.value.trim() || undefined,
    icon: 'folder',
  })
  topics.value.unshift(created)
  return created.id
}

async function createGraph() {
  if (selectedPaperIds.value.length < 2) {
    ElMessage.warning('至少选择 2 篇论文才能生成知识图谱')
    wizardStep.value = 2
    return
  }

  const graphName = await ensureGraphName(true)

  creating.value = true
  wizardStep.value = 4
  generationStep.value = 0
  try {
    const topicId = await ensureTopicId()
    for (let i = 0; i < generationSteps.length - 1; i += 1) {
      generationStep.value = i
      await delay(120)
    }
    const created = await knowledgeApi.create({
      paper_ids: selectedPaperIds.value,
      name: graphName,
      domain_id: topicId,
      build_mode: buildMode.value,
      include_weak: includeWeak.value,
    })
    generationStep.value = generationSteps.length - 1
    graph.value = created
    await loadGraphs()
    await loadTopics()
    showCreateDialog.value = false
    router.replace({ query: { id: created.id } })
    selectSummary()
    ElMessage.success('文献关系图谱已生成')
  } catch {
    ElMessage.error('图谱生成失败，请检查论文解析状态或后端日志')
    wizardStep.value = 3
  } finally {
    creating.value = false
  }
}

async function regenerateCurrentGraph() {
  if (!graph.value) return
  loading.value = true
  try {
    const updated = await knowledgeApi.regenerateGraph(graph.value.id)
    graph.value = updated
    selectSummary()
    await loadGraphs()
    ElMessage.success('图谱已重新生成')
  } catch {
    ElMessage.error('重新生成失败')
  } finally {
    loading.value = false
  }
}

async function deleteCurrentGraph(item: GraphListItem) {
  if (deletingGraphIds.value.has(item.id)) return
  deletingGraphIds.value.add(item.id)
  if (!window.confirm(`确定删除「${item.name}」吗？该操作不会删除原始论文。`)) {
    deletingGraphIds.value.delete(item.id)
    return
  }
  try {
    await knowledgeApi.deleteGraph(item.id)
    graphs.value = graphs.value.filter(g => g.id !== item.id)
    if (graph.value?.id === item.id) {
      graph.value = null
      selectSummary()
      router.replace({ query: {} })
    }
    ElMessage.success('图谱已删除')
  } catch {
    ElMessage.error('删除失败')
  } finally {
    deletingGraphIds.value.delete(item.id)
  }
}

function resetGraphView() {
  graph.value = null
  selectSummary()
  router.replace({ query: {} })
}

function selectNode(node: LiteratureGraphNode) {
  selectedPanel.value = { kind: 'node', node }
}

function selectEdge(edge: LiteratureGraphEdge) {
  selectedPanel.value = { kind: 'edge', edge }
}

function selectSummary() {
  selectedPanel.value = { kind: 'summary' }
}


function onTopicSelect(event: Event) {
  const target = event.target as HTMLSelectElement
  setTopicFromId(target.value ? Number(target.value) : null)
}

function previousStep() {
  if (wizardStep.value === 1) {
    closeCreateDialog()
    return
  }
  wizardStep.value = Math.max(1, wizardStep.value - 1) as WizardStep
}

function nextStep() {
  wizardStep.value = Math.min(4, wizardStep.value + 1) as WizardStep
}

function selectCorePaper(paperId: number) {
  const node = graph.value?.nodes.find(item => item.paper_id === paperId)
  if (node) selectNode(node)
}

function selectNodeById(id: string | number) {
  const node = findNode(id)
  if (node) selectNode(node)
}

function openPaperFromNode(node: LiteratureGraphNode) {
  router.push({ path: '/library', query: { paper_id: String(node.paper_id) } })
}

function createReportFromNode(node: LiteratureGraphNode) {
  router.push({ path: '/reports', query: { paper_id: String(node.paper_id) } })
}

function compareFromGraph() {
  const paperIds = graph.value?.nodes.map(node => node.paper_id).filter(Boolean).slice(0, 5) || []
  router.push({ path: '/compare', query: paperIds.length ? { paper_ids: paperIds.join(',') } : {} })
}

function relatedEdgesForNode(node: LiteratureGraphNode): LiteratureGraphEdge[] {
  return (graph.value?.edges || [])
    .filter(edge => String(edge.source) === String(node.id) || String(edge.target) === String(node.id))
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 6)
}

function otherNodeTitle(edge: LiteratureGraphEdge, node: LiteratureGraphNode): string {
  const otherId = String(edge.source) === String(node.id) ? edge.target : edge.source
  return findNode(otherId)?.title || '关联论文'
}

function findNode(id: string | number): LiteratureGraphNode | undefined {
  return nodeMap.value.get(String(id))
}

function edgeLabel(edge: LiteratureGraphEdge): string {
  const types = edge.relation_types || []
  if (types.length) return types.slice(0, 2).join(' / ')
  if (edge.strength === 'strong') return '强关联'
  if (edge.strength === 'medium') return '中等关联'
  return '弱关联'
}

function edgeStroke(edge: LiteratureGraphEdge): string {
  if (selectedPanel.value.kind === 'edge' && selectedPanel.value.edge.id === edge.id) return '#155EEF'
  if (edge.strength === 'strong') return '#155EEF'
  if (edge.strength === 'medium') return '#64748B'
  return '#94A3B8'
}

function edgeWidth(edge: LiteratureGraphEdge): number {
  if (edge.strength === 'strong') return 4.2
  if (edge.strength === 'medium') return 2.7
  return 1.9
}

function edgeOpacity(edge: LiteratureGraphEdge): number {
  if (selectedPanel.value.kind === 'summary') return edge.strength === 'weak' ? 0.62 : 0.9
  if (selectedPanel.value.kind === 'edge') return selectedPanel.value.edge.id === edge.id ? 1 : 0.2
  if (selectedPanel.value.kind === 'node') {
    const id = String(selectedPanel.value.node.id)
    return String(edge.source) === id || String(edge.target) === id ? 1 : 0.16
  }
  return 0.86
}

function nodeOpacity(node: LayoutNode): number {
  if (!connectedNodeIds.value.has(String(node.id)) && filteredEdges.value.length) return 0.28
  if (selectedPanel.value.kind === 'summary') return 1
  return selectedNodeIds.value.size === 0 || selectedNodeIds.value.has(String(node.id)) ? 1 : 0.22
}

function nodeRadius(node: LiteratureGraphNode): number {
  const base = typeof node.size === 'number' ? node.size * 0.96 : 36
  const centralityBoost = Math.min(11, Math.max(0, (node.centrality || 0) * 8.5))
  return Math.max(32, Math.min(62, base + centralityBoost))
}

function nodeColor(year?: number | null): string {
  if (!year) return '#7F91A6'
  const [minYear, maxYear] = yearRange.value
  const span = Math.max(1, maxYear - minYear)
  const t = Math.max(0, Math.min(1, (year - minYear) / span))
  if (t < 0.25) return '#6B7D93'
  if (t < 0.5) return '#14B8A6'
  if (t < 0.75) return '#3B82F6'
  return '#6366F1'
}

function paperTitle(paper: LibraryPaper): string {
  return paper.title || paper.original_filename || `论文 #${paper.id}`
}

function defaultGraphName(): string {
  const topic = formTopicName.value.trim()
  if (topic) return `${topic} · 文献关系图谱`
  const titles = selectedPapers.value.slice(0, 2).map(paperTitle)
  if (!titles.length) return '文献关系图谱'
  if (selectedPaperIds.value.length <= 2) {
    return `${titles.join(' / ')} · 关系图谱`
  }
  return `${titles[0]} 等 ${selectedPaperIds.value.length} 篇 · 关系图谱`
}

async function suggestGraphName() {
  if (selectedPaperIds.value.length < 2) {
    ElMessage.warning('至少选择 2 篇论文才能生成名称')
    return
  }
  nameLoading.value = true
  try {
    const res = await knowledgeApi.suggestName({
      paper_ids: selectedPaperIds.value,
      topic_name: formTopicName.value.trim() || undefined,
    })
    const candidate = String(res?.name || '').trim()
    formName.value = candidate || defaultGraphName()
    ElMessage.success('已生成图谱名称')
  } catch {
    formName.value = defaultGraphName()
    ElMessage.warning('AI 命名失败，已使用默认名称')
  } finally {
    nameLoading.value = false
  }
}

async function ensureGraphName(preferLlm = false): Promise<string> {
  const trimmed = formName.value.trim()
  if (trimmed) return trimmed
  if (preferLlm && selectedPaperIds.value.length >= 2) {
    nameLoading.value = true
    try {
      const res = await knowledgeApi.suggestName({
        paper_ids: selectedPaperIds.value,
        topic_name: formTopicName.value.trim() || undefined,
      })
      const candidate = String(res?.name || '').trim()
      if (candidate) {
        formName.value = candidate
        return candidate
      }
    } catch {
      // fall through to rule-based name
    } finally {
      nameLoading.value = false
    }
  }
  const generated = defaultGraphName()
  formName.value = generated
  return generated
}

function normalizeText(value: unknown): string {
  if (value == null) return ''
  if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean).join('、')
  return String(value).trim()
}

function normalizeTerms(value: unknown): string[] {
  if (value == null) return []
  if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean)
  return String(value)
    .split(/[;,，；、\n]+/)
    .map(item => item.trim())
    .filter(Boolean)
}

function nodePrimaryLabel(node: LiteratureGraphNode): string {
  const candidates = [node.label, node.name, node.title, formatAuthors(node.authors), '论文']
    .map(value => String(value || '').trim())
    .filter(value => value && !['未知', 'unknown', 'Unknown', '年份未知'].includes(value))
  const raw = candidates[0] || '论文'
  const first = raw.split(/[，,]/)[0]?.trim() || raw.trim()
  return first.length > 12 ? `${first.slice(0, 12)}…` : first
}

function nodeYearLabel(node: LiteratureGraphNode): string {
  return node.year ? String(node.year) : ''
}

function nodeCaption(node: LiteratureGraphNode): string {
  const candidates = [node.label, node.title, node.name, formatAuthors(node.authors), '论文节点']
    .map(value => String(value || '').trim())
    .filter(value => value && !['未知', 'unknown', 'Unknown', '年份未知'].includes(value))
  const source = candidates[0] || '论文节点'
  return source.length > 22 ? `${source.slice(0, 22)}…` : source
}

function formatDate(value?: string | null): string {
  if (!value) return '未知时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未知时间'
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function formatAuthors(value?: string | null): string {
  if (!value) return '作者未知'
  return value.length > 90 ? `${value.slice(0, 90)}...` : value
}

function strengthText(strength?: RelationStrength): string {
  if (strength === 'strong') return '强关联'
  if (strength === 'medium') return '中等关联'
  return '弱关联'
}

function parseStatusText(status?: string | null): string {
  if (!status) return '未知'
  const map: Record<string, string> = {
    parsed: '已解析',
    completed: '已解析',
    success: '已解析',
    parsing: '解析中',
    pending: '等待解析',
    failed: '解析失败',
  }
  return map[status] || status
}

function delay(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}
</script>

<template>
  <div class="literature-graph-page">
    <div
      class="graph-sidebar-wrapper"
      :class="{ collapsed: sidebarCollapsed }"
      @mouseenter="sidebarHovered = true"
      @mouseleave="sidebarHovered = false"
    >
      <GraphWorkbench
        v-model:graph-search="graphSearch"
        v-model:left-tab="leftTab"
        v-model:active-topic-id="activeTopicId"
        :library-stats="libraryStats"
        :topics="topics"
        :filtered-graphs="filteredGraphs"
        :current-graph-id="graph?.id ?? null"
        :format-date="formatDate"
        @refresh="loadGraphs"
        @open-create="openCreateDialog"
        @open-graph="openGraph"
        @delete-graph="deleteCurrentGraph"
      />
    </div>

    <button
      class="module-sidebar-toggle"
      :class="{ visible: sidebarHovered || sidebarCollapsed, collapsed: sidebarCollapsed }"
      :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
      @click="toggleSidebar"
      @mouseenter="sidebarHovered = true"
      @mouseleave="sidebarHovered = false"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline v-if="!sidebarCollapsed" points="15 18 9 12 15 6"/>
        <polyline v-else points="9 18 15 12 9 6"/>
      </svg>
    </button>

    <main class="graph-main">
      <section class="graph-toolbar">
        <div class="toolbar-copy">
          <div class="title-row compact-title-row">
            <h1>知识图谱</h1>
          </div>
        </div>
        <div class="toolbar-actions">
          <button v-if="graph" class="ghost-btn" @click="resetGraphView">返回列表</button>
          <button class="primary-btn" @click="openCreateDialog">新建图谱</button>
        </div>
      </section>

      <section v-if="!graph" ref="createHomePanelRef" class="create-home-panel">
        <div class="create-home-shell">
          <section class="create-paper-card">
            <header class="create-home-head">
              <h2>新建图谱</h2>
            </header>

            <div class="create-field-grid">
              <label class="inline-field name-field">
                <span>图谱名称</span>
                <div class="name-input-row">
                  <input v-model="formName" placeholder="例如：RAG 相关论文研究脉络" />
                  <button
                    type="button"
                    class="ghost-btn name-suggest-btn"
                    :disabled="nameLoading || selectedPaperIds.length < 2"
                    @click="suggestGraphName"
                  >
                    {{ nameLoading ? '生成中…' : 'AI 生成名称' }}
                  </button>
                </div>
              </label>
              <label class="inline-field">
                <span>研究主题</span>
                <input v-model="formTopicName" placeholder="可选，例如：检索增强生成" />
              </label>
            </div>

            <div class="create-paper-toolbar">
              <div>
                <strong>选择论文</strong>
              </div>
              <b>已选 {{ selectedPaperIds.length }}</b>
            </div>

            <div class="search-box create-paper-search">
              <span class="search-icon">⌕</span>
              <input v-model="paperSearch" placeholder="搜索标题、作者或关键词" />
            </div>

            <div class="inline-paper-list slim-scroll">
              <label
                v-for="paper in filteredPapers"
                :key="paper.id"
                class="inline-paper-option"
                :class="{ checked: selectedPaperIds.includes(paper.id) }"
              >
                <input type="checkbox" :checked="selectedPaperIds.includes(paper.id)" @change="togglePaper(paper.id)" />
                <div>
                  <strong>{{ paperTitle(paper) }}</strong>
                  <span>
                    {{ normalizeText(paper.authors) || '作者未知' }} · {{ paper.publication_year || paper.year || '年份未知' }} ·
                    {{ paper.parse_status === 'failed' ? '解析失败，关系解释可能较少' : parseStatusText(paper.parse_status) }}
                  </span>
                </div>
              </label>
              <div v-if="!filteredPapers.length" class="empty-small">暂无可选择论文，请先上传或解析本地文献。</div>
            </div>
          </section>

          <aside class="create-preview-card">
            <h3>生成预览</h3>
            <p>将根据所选论文生成局部文献关系网络。</p>

            <div class="preview-stat-row">
              <div><b>{{ selectedPaperIds.length }}</b><span>已选论文</span></div>
              <div><b>{{ selectedPaperIds.length >= 2 ? '可生成' : '待选择' }}</b><span>当前状态</span></div>
            </div>

            <div class="selected-paper-box">
              <strong>已选论文</strong>
              <div v-if="selectedPapers.length" class="selected-paper-list">
                <button v-for="paper in selectedPapers.slice(0, 6)" :key="paper.id" @click="togglePaper(paper.id)">
                  <span :title="paperTitle(paper)">{{ paperTitle(paper) }}</span>
                  <small>移除</small>
                </button>
                <em v-if="selectedPapers.length > 6">另有 {{ selectedPapers.length - 6 }} 篇</em>
              </div>
              <p v-else>请选择至少 2 篇论文。</p>
            </div>

            <div class="create-mode-box">
              <strong>构建方式</strong>
              <label>
                <input v-model="includeWeak" type="checkbox" />
                <span>保留弱关联，适合文献数量较少时查看线索。</span>
              </label>
            </div>

            <button class="create-submit-btn" :disabled="!canCreateInlineGraph" @click="createGraph">
              {{ creating ? '正在生成...' : '生成文献关系图谱' }}
            </button>
            <button class="create-library-btn" @click="router.push('/library')">去文献库上传 / 解析论文</button>

            <p class="create-help-text">{{ createButtonHint }}</p>
          </aside>
        </div>
      </section>

      <section v-else :class="['graph-workspace', `state-${graphDisplayState}`]">
        <div class="graph-canvas-card">
          <div class="canvas-header simplified-header">
            <div class="canvas-title-inline">
              <strong>{{ graphTitle }}</strong>
            </div>
            <div class="filter-row relation-only-filter">
              <label>关系类型</label>
              <select v-model="relationFilter">
                <option value="all">全部关系</option>
                <option value="strong">强关联</option>
                <option value="weak">弱关联</option>
                <option value="semantic">语义相似</option>
                <option value="keyword">关键词重合</option>
                <option value="method">方法相近</option>
              </select>
            </div>
          </div>

          <GraphCanvas
            :loading="loading"
            :layout-edges="layoutEdges"
            :layout-nodes="layoutNodes"
            :selected-panel="selectedPanel"
            :selected-node-for-panel="selectedNodeForPanel"
            :filtered-edges="filteredEdges"
            :graph-nodes="graph.nodes"
            :year-range="yearRange"
            :edge-stroke="edgeStroke"
            :edge-width="edgeWidth"
            :edge-opacity="edgeOpacity"
            :node-opacity="nodeOpacity"
            :node-primary-label="nodePrimaryLabel"
            :node-year-label="nodeYearLabel"
            :node-caption="nodeCaption"
            :format-authors="formatAuthors"
            :display-state="graphDisplayState"
            :display-message="graphDisplayMessage"
            :single-paper="singlePaperForState"
            @select-summary="selectSummary"
            @select-edge="selectEdge"
            @select-node="selectNode"
            @open-create="openCreateDialog"
            @open-library="router.push('/library')"
          />
        </div>

        <GraphRightPanel
          :graph="graph"
          :panel-mode="rightPanelMode"
          :selected-panel="selectedPanel"
          :graph-stats="graphStats"
          :filtered-edges="filteredEdges"
          :total-edges="totalEdges"
          :empty-reason="emptyPanelReason"
          :relation-filter="relationFilter"
          :min-score="minScore"
          :hidden-by-type-count="hiddenByTypeCount"
          :hidden-by-threshold-count="hiddenByThresholdCount"
          :has-only-weak-edges="hasOnlyWeakEdges"
          :display-state="graphDisplayState"
          :display-message="graphDisplayMessage"
          :single-paper="singlePaperForState"
          :format-authors="formatAuthors"
          :parse-status-text="parseStatusText"
          :related-edges-for-node="relatedEdgesForNode"
          :other-node-title="otherNodeTitle"
          :edge-label="edgeLabel"
          :strength-text="strengthText"
          :find-node="findNode"
          @select-core-paper="selectCorePaper"
          @select-edge="selectEdge"
          @select-node-by-id="selectNodeById"
          @open-paper="openPaperFromNode"
          @create-report="createReportFromNode"
          @compare-graph="compareFromGraph"
        />
      </section>
    </main>

    <Teleport to="body">
      <div v-if="showCreateDialog" class="modal-mask" @click.self="closeCreateDialog">
        <div class="create-dialog">
          <header class="dialog-header">
            <div>
              <p class="eyebrow">创建图谱</p>
              <h2>新建文献关系图谱</h2>
              <p>选择一组论文，系统将生成论文之间的关联关系与局部研究脉络。</p>
            </div>
            <button class="icon-btn" @click="closeCreateDialog">×</button>
          </header>

          <div class="stepper">
            <span :class="{ active: wizardStep >= 1 }">1 基本信息</span>
            <span :class="{ active: wizardStep >= 2 }">2 选择论文</span>
            <span :class="{ active: wizardStep >= 3 }">3 构建方式</span>
            <span :class="{ active: wizardStep >= 4 }">4 生成图谱</span>
          </div>

          <section v-if="wizardStep === 1" class="dialog-body">
            <label class="field-label">图谱名称</label>
            <div class="name-input-row">
              <input v-model="formName" class="text-input" placeholder="例如：检索增强生成相关文献研究脉络" />
              <button
                type="button"
                class="ghost-btn name-suggest-btn"
                :disabled="nameLoading || selectedPaperIds.length < 2"
                @click="suggestGraphName"
              >
                {{ nameLoading ? '生成中…' : 'AI 生成名称' }}
              </button>
            </div>

            <label class="field-label">研究主题</label>
            <div class="topic-select-row">
              <select :value="formTopicId ?? ''" @change="onTopicSelect">
                <option value="">未分类 / 新建主题</option>
                <option v-for="topic in topics" :key="topic.id" :value="topic.id">{{ topic.name }}</option>
              </select>
              <input v-model="formTopicName" class="text-input" placeholder="也可以输入新主题，如：知识增强生成" />
            </div>

            <label class="field-label">图谱说明</label>
            <textarea v-model="formDescription" class="text-area" placeholder="可选：记录这个图谱想分析的问题。"></textarea>
          </section>

          <section v-else-if="wizardStep === 2" class="dialog-body paper-picker">
            <div class="picker-head">
              <div>
                <h3>选择论文</h3>
                <p>至少选择 2 篇。未解析论文也可参与快速构建，但解释会较少。</p>
              </div>
              <strong>已选 {{ selectedPaperIds.length }}</strong>
            </div>
            <div class="search-box wide">
              <span class="search-icon">⌕</span>
              <input v-model="paperSearch" placeholder="搜索标题、作者或关键词" />
            </div>
            <div class="paper-list-modal slim-scroll">
              <label
                v-for="paper in filteredPapers"
                :key="paper.id"
                class="paper-option"
                :class="{ checked: selectedPaperIds.includes(paper.id) }"
              >
                <input type="checkbox" :checked="selectedPaperIds.includes(paper.id)" @change="togglePaper(paper.id)" />
                <div>
                  <strong>{{ paperTitle(paper) }}</strong>
                  <span>{{ normalizeText(paper.authors) || '作者未知' }} · {{ paper.publication_year || paper.year || '年份未知' }} · {{ parseStatusText(paper.parse_status) }}</span>
                </div>
              </label>
              <div v-if="!filteredPapers.length" class="empty-small">暂无可选择论文。</div>
            </div>
          </section>

          <section v-else-if="wizardStep === 3" class="dialog-body">
            <div class="mode-grid">
              <button class="mode-card" :class="{ active: buildMode === 'fast' }" @click="buildMode = 'fast'">
                <span class="mode-badge">推荐</span>
                <h3>快速构建</h3>
                <p>基于标题、摘要、关键词和抽取信息计算论文关系。速度快，适合演示和初步浏览。</p>
              </button>
              <button class="mode-card" :class="{ active: buildMode === 'deep' }" @click="buildMode = 'deep'">
                <span class="mode-badge soft">预留</span>
                <h3>深度构建</h3>
                <p>预留给全文语义和大模型深度解释。当前后端会兼容该模式，但第一版仍以稳定关系计算为主。</p>
              </button>
            </div>
            <label class="switch-row">
              <input v-model="includeWeak" type="checkbox" />
              <span>包含弱关联，避免文献数量少时出现空图。</span>
            </label>
          </section>

          <section v-else class="dialog-body generating-body">
            <div class="generating-orb"></div>
            <h3>正在生成文献关系图谱</h3>
            <div class="generation-list">
              <div
                v-for="(step, index) in generationSteps"
                :key="step"
                :class="{ done: index < generationStep, active: index === generationStep }"
              >
                <span>{{ index < generationStep ? '✓' : index === generationStep ? '•' : '○' }}</span>
                {{ step }}
              </div>
            </div>
          </section>

          <footer class="dialog-footer">
            <button class="ghost-btn" :disabled="creating" @click="previousStep">
              {{ wizardStep === 1 ? '取消' : '上一步' }}
            </button>
            <button
              v-if="wizardStep < 3"
              class="primary-btn"
              :disabled="wizardStep === 2 && selectedPaperIds.length < 2"
              @click="nextStep"
            >下一步</button>
            <button v-else-if="wizardStep === 3" class="primary-btn" :disabled="selectedPaperIds.length < 2 || creating" @click="createGraph">
              开始生成
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.literature-graph-page {
  --graph-blue: #2563eb;
  --graph-cyan: #14b8a6;
  --graph-navy: #0f1f3d;
  --graph-text: #182235;
  --graph-muted: #64748b;
  --graph-line: #e3ebf4;
  display: flex;
  height: 100%;
  min-height: 100vh;
  background:
    radial-gradient(circle at 24% 2%, rgba(37, 99, 235, 0.06), transparent 32%),
    linear-gradient(135deg, #f7faff 0%, #f4f8fb 42%, #f9fbfd 100%);
  color: var(--graph-text);
  overflow: hidden;
  position: relative;
}

.graph-sidebar-wrapper {
  position: relative;
  flex-shrink: 0;
  width: 292px;
  overflow: hidden;
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.graph-sidebar-wrapper.collapsed {
  width: 0;
}

.module-sidebar-toggle {
  position: absolute;
  left: 272px;
  top: 18px;
  z-index: 50;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e2e8f0;
  border-radius: 50%;
  background: #fff;
  color: #64748b;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 0.2s ease, transform 0.2s ease, color 0.15s, left 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}

.module-sidebar-toggle.visible {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.module-sidebar-toggle.collapsed {
  left: 12px;
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.module-sidebar-toggle:hover {
  color: #0f172a;
  border-color: #cbd5e1;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

.graph-sidebar {
  width: 292px;
  min-width: 292px;
  display: flex;
  flex-direction: column;
  padding: 20px 16px;
  background: rgba(255, 255, 255, 0.82);
  border-right: 1px solid rgba(207, 216, 227, 0.72);
  box-shadow: 10px 0 34px rgba(15, 23, 42, 0.035);
  backdrop-filter: blur(14px);
}

.sidebar-heading,
.graph-toolbar,
.canvas-header,
.dialog-header,
.picker-head,
.card-footer,
.toolbar-actions,
.metric-row,
.filter-row,
.legend-row,
.topic-select-row,
.title-row,
.welcome-actions {
  display: flex;
  align-items: center;
}

.sidebar-heading,
.graph-toolbar,
.canvas-header,
.dialog-header,
.picker-head {
  justify-content: space-between;
}

.eyebrow {
  margin: 0 0 5px;
  color: #6c7f95;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

h1, h2, h3, p {
  margin-top: 0;
}

.sidebar-heading h2,
.graph-toolbar h1,
.dialog-header h2 {
  margin: 0;
  color: #0f1f3d;
  font-weight: 850;
  letter-spacing: -0.04em;
}

.sidebar-heading h2 {
  font-size: 22px;
  line-height: 1.18;
}

.graph-toolbar h1 {
  font-size: 27px;
  line-height: 1.05;
}

.sidebar-desc,
.graph-toolbar p,
.dialog-header p,
.picker-head p,
.muted {
  color: var(--graph-muted);
  line-height: 1.65;
}

.sidebar-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin: 18px 0 14px;
}

.sidebar-metrics div {
  min-height: 66px;
  padding: 11px 8px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--graph-line);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.035);
}

.sidebar-metrics b,
.sidebar-metrics span {
  display: block;
  text-align: center;
}

.sidebar-metrics b {
  color: #0f5e78;
  font-size: 21px;
  line-height: 1.05;
}

.sidebar-metrics span {
  margin-top: 6px;
  color: #76869a;
  font-size: 12px;
  font-weight: 700;
}

.sidebar-create {
  margin: 0 0 16px;
}

.graph-toolbar p {
  max-width: 580px;
  margin-bottom: 0;
  font-size: 13px;
  line-height: 1.48;
}

.toolbar-copy {
  min-width: 0;
}

.title-row {
  gap: 12px;
  flex-wrap: wrap;
}

.current-graph-chip {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: #31527d;
  font-size: 12px;
  font-weight: 800;
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-box {
  position: relative;
  margin: 0 0 12px;
}

.search-box.wide {
  margin-top: 10px;
}

.search-icon {
  position: absolute;
  left: 13px;
  top: 50%;
  transform: translateY(-50%);
  color: #8ea0b5;
  font-size: 16px;
}

.search-box input,
.text-input,
.text-area,
.topic-select-row select,
.filter-row select {
  width: 100%;
  border: 1px solid #dbe6f0;
  background: rgba(255, 255, 255, 0.96);
  border-radius: 14px;
  color: #1e293b;
  outline: none;
  transition: border 0.16s, box-shadow 0.16s, background 0.16s;
}

.search-box input {
  height: 42px;
  padding: 0 12px 0 38px;
}

.text-input,
.topic-select-row select {
  height: 42px;
  padding: 0 13px;
}

.text-area {
  min-height: 92px;
  padding: 12px 13px;
  resize: vertical;
}

.search-box input:focus,
.text-input:focus,
.text-area:focus,
.topic-select-row select:focus,
.filter-row select:focus {
  border-color: rgba(20, 184, 166, 0.68);
  box-shadow: 0 0 0 4px rgba(20, 184, 166, 0.12);
}

.tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  padding: 4px;
  margin-bottom: 12px;
  background: #edf4f8;
  border-radius: 14px;
}

.tabs button,
.topic-pill,
.graph-card,
.icon-btn,
.ghost-btn,
.primary-btn,
.create-btn,
.related-paper,
.mode-card,
.paper-option,
.edge-papers button,
.relation-line-item {
  border: none;
  cursor: pointer;
  font-family: inherit;
}

.tabs button {
  height: 34px;
  border-radius: 11px;
  background: transparent;
  color: #66768a;
  font-weight: 800;
}

.tabs button.active {
  background: #fff;
  color: #0f6b83;
  box-shadow: 0 7px 18px rgba(15, 86, 111, 0.10);
}

.topic-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.topic-pill {
  padding: 7px 10px;
  border-radius: 999px;
  background: #edf5f7;
  color: #5a7188;
  font-size: 12px;
  font-weight: 800;
}

.topic-pill.active {
  background: #dff7f5;
  color: #0f766e;
}

.graph-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 3px 0 0;
}

.graph-card {
  width: 100%;
  margin-bottom: 12px;
  padding: 15px;
  text-align: left;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.95);
  color: #1e293b;
  border: 1px solid rgba(213, 223, 235, 0.92);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.045);
  transition: transform 0.16s, box-shadow 0.16s, border-color 0.16s, background 0.16s;
}

.graph-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 16px 34px rgba(15, 23, 42, 0.08);
}

.graph-card.active {
  border-color: rgba(37, 99, 235, 0.72);
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  box-shadow: 0 18px 36px rgba(37, 99, 235, 0.14);
}

.card-topline,
.card-meta,
.paper-meta-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 99px;
  background: #10b981;
  box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.12);
}

.card-status,
.card-topic,
.card-meta,
.card-footer {
  color: #728196;
  font-size: 12px;
}

.graph-card strong {
  display: block;
  margin: 9px 0 5px;
  font-size: 14px;
  line-height: 1.45;
}

.card-meta {
  margin-top: 10px;
}

.card-meta span {
  padding: 5px 9px;
  border-radius: 999px;
  background: #f0f5fa;
  color: #687b91;
  font-weight: 700;
}

.card-footer {
  justify-content: space-between;
  margin-top: 12px;
}

.card-action {
  color: #ef4444;
  opacity: 0.78;
}

.create-btn,
.primary-btn {
  background: linear-gradient(135deg, #2563eb 0%, #0ea5e9 100%);
  color: #fff;
  font-weight: 850;
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.22);
}

.create-btn {
  width: 100%;
  height: 44px;
  border-radius: 14px;
}

.primary-btn,
.ghost-btn,
.icon-btn {
  height: 38px;
  padding: 0 15px;
  border-radius: 12px;
}

.primary-btn:disabled,
.ghost-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.ghost-btn,
.icon-btn {
  background: rgba(255, 255, 255, 0.92);
  color: #344960;
  border: 1px solid #dbe6f0;
}

.icon-btn {
  width: 38px;
  padding: 0;
  font-size: 18px;
}

.graph-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.graph-toolbar {
  padding: 18px 24px 16px;
  gap: 12px;
  margin-bottom: 8px;
}

.toolbar-actions {
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
  flex-shrink: 0;
}


.create-home-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: stretch;
  justify-content: center;
  padding: 0 22px 22px;
  overflow: hidden;
}

.create-home-shell {
  width: min(980px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) 300px;
  gap: 16px;
  min-height: 0;
}

.create-paper-card,
.create-preview-card {
  min-height: 0;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(221, 230, 240, 0.92);
  border-radius: 22px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.045);
}

.create-paper-card {
  display: flex;
  flex-direction: column;
  padding: 18px;
  overflow: hidden;
}

.create-home-head {
  margin-bottom: 14px;
}

.create-home-head h2 {
  margin: 0;
  color: #0f1f3d;
  font-size: 24px;
  line-height: 1.2;
  letter-spacing: 0;
}

.create-field-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

.inline-field span {
  display: block;
  margin-bottom: 7px;
  color: #334155;
  font-size: 14px;
  font-weight: 850;
}

.inline-field input,
.create-paper-search input {
  width: 100%;
  height: 40px;
  border: 1px solid #dbe6f0;
  border-radius: 13px;
  background: #fff;
  color: #1e293b;
  outline: none;
}

.inline-field input {
  padding: 0 12px;
}

.name-input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.name-input-row input,
.name-input-row .text-input {
  flex: 1;
  min-width: 0;
}

.name-suggest-btn {
  flex-shrink: 0;
  height: 40px;
  padding: 0 12px;
  white-space: nowrap;
}

.create-paper-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.create-paper-toolbar strong,
.selected-paper-box strong,
.create-mode-box strong,
.create-preview-card h3 {
  color: #14233b;
  font-size: 14px;
  font-weight: 850;
}

.create-paper-toolbar span {
  display: block;
  margin-top: 3px;
  color: #7b8aa0;
  font-size: 12px;
}

.create-paper-toolbar b {
  color: #0f6b83;
  font-size: 13px;
}

.create-paper-search {
  margin-bottom: 12px;
}

.inline-paper-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  border-top: 1px solid #edf3f8;
}

.inline-paper-option {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: flex-start;
  padding: 12px 4px;
  border-bottom: 1px solid #edf3f8;
  cursor: pointer;
}

.inline-paper-option.checked {
  background: #f4f7fb;
}

.inline-paper-option input {
  margin-top: 4px;
  accent-color: #2563eb;
}

.inline-paper-option strong {
  display: -webkit-box;
  color: #1e293b;
  font-size: 13.5px;
  line-height: 1.42;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.inline-paper-option span {
  display: block;
  margin-top: 5px;
  color: #718096;
  font-size: 12px;
  line-height: 1.45;
}

.create-preview-card {
  display: flex;
  flex-direction: column;
  padding: 18px;
  overflow: hidden;
}

.create-preview-card h3 {
  margin: 0 0 8px;
}

.create-preview-card > p {
  margin: 0 0 14px;
  color: #617286;
  font-size: 13px;
  line-height: 1.6;
}

.preview-stat-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 14px;
}

.preview-stat-row div {
  padding: 12px;
  border: 1px solid #edf3f8;
  border-radius: 14px;
  background: #fbfdff;
}

.preview-stat-row b,
.preview-stat-row span {
  display: block;
}

.preview-stat-row b {
  color: #0f6b83;
  font-size: 18px;
}

.preview-stat-row span {
  margin-top: 4px;
  color: #7b8aa0;
  font-size: 12px;
}

.selected-paper-box {
  margin-bottom: 14px;
}

.selected-paper-box p,
.create-help-text {
  color: #718096;
  font-size: 12.5px;
  line-height: 1.55;
}

.selected-paper-list {
  display: grid;
  gap: 7px;
  margin-top: 10px;
}

.selected-paper-list button {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #edf3f8;
  border-radius: 12px;
  background: #fff;
  color: #334155;
  text-align: left;
  cursor: pointer;
}

.selected-paper-list span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected-paper-list small {
  flex: 0 0 auto;
  color: #ef4444;
}

.selected-paper-list em {
  color: #718096;
  font-size: 12px;
  font-style: normal;
  padding: 0 2px;
}

.create-mode-box {
  margin-top: auto;
  margin-bottom: 14px;
  padding-top: 12px;
  border-top: 1px solid #edf3f8;
}

.create-mode-box label {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  margin-top: 10px;
  color: #607086;
  font-size: 12.5px;
  line-height: 1.55;
}

.create-mode-box input {
  margin-top: 3px;
  accent-color: #2563eb;
}

.create-submit-btn,
.create-library-btn {
  width: 100%;
  height: 42px;
  border-radius: 13px;
  font-weight: 850;
  cursor: pointer;
}

.create-submit-btn {
  border: none;
  background: #2563eb;
  color: #fff;
}

.create-submit-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.create-library-btn {
  margin-top: 9px;
  border: 1px solid #dbe6f0;
  background: #fff;
  color: #40566c;
}

.create-help-text {
  margin: 12px 0 0;
}

@media (max-width: 1180px) {
  .create-home-shell {
    grid-template-columns: 1fr;
  }
}

.welcome-panel {
  flex: 1;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 26px 34px 34px;
}

.welcome-card {
  width: min(880px, 100%);
  padding: 26px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(214, 224, 236, 0.88);
  border-radius: 26px;
  box-shadow: 0 28px 72px rgba(15, 23, 42, 0.08);
}

.refined-empty-card {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 30px;
  align-items: center;
}

.empty-graph-preview {
  position: relative;
  height: 230px;
  border-radius: 24px;
  background:
    radial-gradient(circle at 32% 35%, rgba(20, 184, 166, 0.18), transparent 38%),
    radial-gradient(circle at 74% 58%, rgba(37, 99, 235, 0.12), transparent 42%),
    #f8fbfd;
  border: 1px solid #e3ebf4;
  overflow: hidden;
}

.preview-line {
  position: absolute;
  height: 1.5px;
  background: rgba(94, 116, 140, 0.28);
  transform-origin: left center;
}

.preview-line.l1 { width: 150px; left: 66px; top: 84px; transform: rotate(18deg); }
.preview-line.l2 { width: 128px; left: 102px; top: 145px; transform: rotate(-28deg); }
.preview-line.l3 { width: 112px; left: 72px; top: 174px; transform: rotate(-4deg); }

.preview-node {
  position: absolute;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #8bbbc2;
  color: #fff;
  border: 3px solid rgba(255, 255, 255, 0.95);
  box-shadow: 0 16px 36px rgba(27, 83, 104, 0.18);
  font-size: 11px;
  font-weight: 850;
}

.preview-node.n1 { width: 88px; height: 88px; left: 32px; top: 72px; background: #9aaab8; }
.preview-node.n2 { width: 68px; height: 68px; left: 154px; top: 104px; background: #14b8a6; }
.preview-node.n3 { width: 54px; height: 54px; left: 204px; top: 44px; background: #2563eb; }
.preview-node.n4 { width: 56px; height: 56px; left: 84px; top: 162px; background: #60a5fa; }

.welcome-copy {
  text-align: left;
}

.welcome-kicker {
  display: inline-flex;
  margin-bottom: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #eaf8f6;
  color: #0f766e;
  font-size: 12px;
  font-weight: 850;
}

.welcome-copy h2 {
  margin-bottom: 12px;
  font-size: 27px;
  line-height: 1.22;
  letter-spacing: -0.04em;
}

.welcome-copy p {
  margin-bottom: 0;
  color: #5c6f84;
  line-height: 1.75;
}

.welcome-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0 20px;
}

.welcome-pills span {
  padding: 7px 10px;
  border-radius: 999px;
  background: #f0f5fa;
  color: #50657c;
  font-size: 12px;
  font-weight: 800;
}

.welcome-actions {
  gap: 10px;
  flex-wrap: wrap;
}

.graph-workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 12px;
  padding: 0 14px 16px;
  overflow: hidden;
}

.graph-workspace.state-low {
  grid-template-columns: minmax(0, 1fr) 300px;
}

.graph-workspace.state-weak {
  grid-template-columns: minmax(0, 1fr) 300px;
}

.graph-workspace.state-empty {
  grid-template-columns: minmax(0, 1fr) 300px;
}

.graph-canvas-card,
.detail-panel {
  min-height: 0;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(221, 230, 240, 0.92);
  border-radius: 22px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.045);
}

.graph-canvas-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.canvas-header {
  padding: 14px 18px 12px;
  gap: 12px;
  border-bottom: 1px solid #eef4f9;
}

.canvas-header.simplified-header {
  align-items: center;
}

.relation-only-filter {
  align-items: center;
  gap: 10px;
}

.relation-only-filter label {
  margin-right: 2px;
}

.canvas-title-inline {
  min-width: 150px;
  flex: 1;
}

.canvas-title-inline strong,
.canvas-title-inline span {
  display: block;
}

.canvas-title-inline strong {
  color: #13203a;
  font-size: 17px;
  line-height: 1.32;
}

.canvas-title-inline span {
  margin-top: 2px;
  color: #7b8aa0;
  font-size: 11.5px;
}

.metric-row,
.filter-row {
  gap: 10px;
  flex-wrap: wrap;
}

.metric-row span {
  padding: 7px 10px;
  border-radius: 999px;
  background: #f0f7f9;
  color: #587286;
  font-size: 12px;
}

.metric-row b {
  color: #0f6b83;
}

.filter-row {
  justify-content: flex-end;
  margin-left: auto;
}

.filter-row > label:not(.score-filter) {
  color: #5c6f83;
  font-size: 14px;
  font-weight: 760;
  line-height: 1;
}

.filter-row select {
  width: 152px;
  height: 38px;
  padding: 0 36px 0 14px;
  border-radius: 14px;
}

.score-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #46586c;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
}

.score-filter input {
  width: 104px;
  accent-color: var(--graph-blue);
}


.svg-shell {
  position: relative;
  flex: 1;
  min-height: 0;
  margin: 10px 16px 0;
  border-radius: 20px;
  background:
    radial-gradient(circle at 48% 40%, rgba(20, 184, 166, 0.10), transparent 22%),
    radial-gradient(circle at 70% 60%, rgba(37, 99, 235, 0.06), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 253, 255, 0.96));
  border: 1px solid #edf3f8;
  overflow: hidden;
}

.svg-shell svg {
  width: 100%;
  height: 100%;
  min-height: 540px;
  display: block;
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
  transition: opacity 0.16s;
}

.node-halo {
  fill: rgba(255, 255, 255, 0.38);
  stroke: rgba(148, 163, 184, 0.18);
  stroke-width: 13;
}

.node-halo.selected {
  stroke: rgba(37, 99, 235, 0.30);
  stroke-width: 16;
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
  font-size: 13px;
}

.node-year-label {
  font-size: 12px;
}

.node-label {
  fill: #28394f;
  font-size: 12.5px;
  font-weight: 850;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.96);
  stroke-width: 5px;
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

.legend-row {
  justify-content: center;
  gap: 18px;
  padding: 12px 14px 16px;
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

.detail-panel {
  padding: 14px;
  overflow-y: auto;
  word-break: break-word;
}

.panel-section {
  padding: 14px;
  margin-bottom: 12px;
  border-radius: 16px;
  background: #f9fcff;
  border: 1px solid #edf3f8;
}

.hero-summary,
.paper-head,
.edge-head {
  background: linear-gradient(135deg, #f4fbff, #f7fffd);
  border-color: #dcecf4;
}

.panel-section h2,
.panel-section h3 {
  margin: 0 0 10px;
  color: #14233b;
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

.summary-grid,
.two-metrics {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}

.summary-grid div,
.two-metrics div {
  padding: 14px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid #edf3f8;
}

.summary-grid b,
.two-metrics b {
  display: block;
  color: #0f6b83;
  font-size: 22px;
}

.summary-grid span,
.two-metrics span {
  color: #7d8b9c;
  font-size: 12px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-list span {
  padding: 6px 10px;
  border-radius: 999px;
  background: #e8faf7;
  color: #0f766e;
  font-size: 12px;
  font-weight: 800;
}

.tag-list.compact span {
  padding: 5px 8px;
  font-size: 11px;
}

.related-paper,
.relation-line-item {
  width: 100%;
  padding: 11px 12px;
  margin-top: 8px;
  text-align: left;
  border-radius: 14px;
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
  flex-wrap: wrap;
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

.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: grid;
  place-items: center;
  background: rgba(15, 23, 42, 0.34);
  backdrop-filter: blur(8px);
}

.create-dialog {
  width: min(920px, calc(100vw - 44px));
  max-height: calc(100vh - 44px);
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 28px;
  box-shadow: 0 34px 90px rgba(15, 23, 42, 0.24);
  overflow: hidden;
}

.dialog-header {
  padding: 24px 28px 16px;
  border-bottom: 1px solid #edf3f8;
}

.stepper {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  padding: 14px 28px;
  background: #f8fbfd;
}

.stepper span {
  position: relative;
  padding: 8px 8px;
  color: #8493a5;
  text-align: center;
  font-size: 12px;
  font-weight: 850;
}

.stepper span::before {
  content: '';
  display: block;
  width: 9px;
  height: 9px;
  margin: 0 auto 7px;
  border-radius: 999px;
  background: #cbd5e1;
  box-shadow: 0 0 0 5px #eef3f8;
}

.stepper span:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 12px;
  left: calc(50% + 16px);
  right: calc(-50% + 16px);
  height: 1px;
  background: #dbe5ef;
}

.stepper span.active {
  color: #0f6b83;
}

.stepper span.active::before {
  background: var(--graph-cyan);
  box-shadow: 0 0 0 5px rgba(20, 184, 166, 0.13);
}

.dialog-body {
  padding: 24px 28px;
  overflow-y: auto;
}

.field-label {
  display: block;
  margin: 0 0 8px;
  color: #334155;
  font-size: 13px;
  font-weight: 850;
}

.field-label:not(:first-child) {
  margin-top: 18px;
}

.topic-select-row {
  gap: 10px;
}

.topic-select-row select {
  width: 220px;
  flex-shrink: 0;
}

.paper-picker {
  min-height: 430px;
}

.paper-list-modal {
  max-height: 360px;
  overflow-y: auto;
  margin-top: 12px;
}

.paper-option {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
  padding: 13px;
  margin-bottom: 10px;
  border-radius: 16px;
  background: #f8fbfd;
  border: 1px solid #edf3f8;
  transition: border 0.16s, background 0.16s;
}

.paper-option.checked {
  background: #edf8fb;
  border-color: #75b6c9;
}

.paper-option strong,
.paper-option span {
  display: block;
}

.paper-option span {
  margin-top: 5px;
  color: #7d8b9c;
  font-size: 12px;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.mode-card {
  position: relative;
  padding: 22px;
  text-align: left;
  border-radius: 20px;
  background: #f8fbfd;
  color: #1e293b;
  border: 1px solid #edf3f8;
}

.mode-card.active {
  border-color: #54a9b4;
  background: #edf8fb;
  box-shadow: 0 16px 34px rgba(36, 112, 139, 0.12);
}

.mode-badge {
  display: inline-block;
  margin-bottom: 18px;
  padding: 5px 9px;
  border-radius: 999px;
  background: #0f8ea5;
  color: #fff;
  font-size: 11px;
  font-weight: 850;
}

.mode-badge.soft {
  background: #cbd5e1;
  color: #475569;
}

.mode-card p {
  color: #64748b;
  line-height: 1.65;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  color: #45586b;
  font-weight: 750;
}

.generating-body {
  display: grid;
  place-items: center;
  text-align: center;
  min-height: 360px;
}

.generating-orb {
  width: 76px;
  height: 76px;
  border-radius: 28px;
  background: conic-gradient(from 0deg, #2563eb, #14b8a6, #e0f5f7, #2563eb);
  animation: spin 1.3s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.generation-list {
  width: 320px;
  margin-top: 18px;
  text-align: left;
}

.generation-list div {
  padding: 9px 0;
  color: #94a3b8;
  font-weight: 750;
}

.generation-list div.active {
  color: #2563eb;
}

.generation-list div.done {
  color: #17806d;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 28px 24px;
  border-top: 1px solid #edf3f8;
}

.empty-small {
  margin-top: 16px;
  padding: 22px 18px;
  text-align: center;
  color: #8493a5;
  border: 1px dashed #dce5ee;
  border-radius: 18px;
  background: #f8fbfd;
}

.empty-small strong,
.empty-small span {
  display: block;
}

.slim-scroll::-webkit-scrollbar,
.detail-panel::-webkit-scrollbar,
.paper-list-modal::-webkit-scrollbar {
  width: 6px;
}

.slim-scroll::-webkit-scrollbar-thumb,
.detail-panel::-webkit-scrollbar-thumb,
.paper-list-modal::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 999px;
}

@media (max-width: 1380px) {
  .graph-workspace,
  .graph-workspace.state-low,
  .graph-workspace.state-empty {
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 12px;
    padding: 0 14px 16px;
  }
  .graph-workspace.state-weak {
    grid-template-columns: minmax(0, 1fr) 344px;
    gap: 12px;
    padding: 0 14px 16px;
  }
  .graph-sidebar {
    width: 278px;
    min-width: 278px;
    padding-left: 14px;
    padding-right: 14px;
  }
  .toolbar-actions {
    gap: 8px;
  }
}

@media (max-width: 1180px) {
  .graph-workspace,
  .graph-workspace.state-low,
  .graph-workspace.state-weak,
  .graph-workspace.state-empty {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }
  .detail-panel {
    min-height: 320px;
  }
  .refined-empty-card {
    grid-template-columns: 1fr;
  }
  .empty-graph-preview {
    display: none;
  }
}
</style>
