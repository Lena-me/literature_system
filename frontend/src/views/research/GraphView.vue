<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { knowledgeApi, type GraphListItem } from '@/api/knowledge'
import { papersApi } from '@/api/papers'
import GraphCanvas from '@/components/reader/GraphCanvas.vue'
import type { KnowledgeGraph, KnowledgeDomain, DomainSuggestion, MergeSuggestion, RegionRecommendation } from '@/types/domain'

const route = useRoute()
const router = useRouter()

// ========== 知识域 ==========
const domains = ref<KnowledgeDomain[]>([])
const activeDomainId = ref<number | null>(null)
const showNewDomainForm = ref(false)
const newDomainName = ref('')
const newDomainDesc = ref('')
const domainCreating = ref(false)

// ========== AI 感知建议 ==========
const aiSuggestions = ref<DomainSuggestion[]>([])
const suggestionsLoading = ref(false)
let suggestionTimer: ReturnType<typeof setTimeout> | null = null

// ========== 实体融合 ==========
const mergeSuggestions = ref<MergeSuggestion[]>([])
const mergeLoading = ref(false)

// ========== 知识推荐 ==========
const recommendations = ref<RegionRecommendation[]>([])
const recLoading = ref(false)

const graphCypher = computed(() => {
  if (!graphId.value) return ''
  return `MATCH (n:Entity)-[r]->(m:Entity) WHERE r.graph_id = ${graphId.value} RETURN n, r, m`
})

const activeDomain = computed(() =>
  domains.value.find(d => d.id === activeDomainId.value) || null
)

// 切换知识域时自动回到构建模式
watch(activeDomainId, () => {
  if (graphId.value) {
    graphId.value = null
    graph.value = null
    router.replace({ query: {} })
  }
})

async function loadDomains() {
  try {
    domains.value = await knowledgeApi.listDomains()
  } catch { /* */ }
}

async function handleCreateDomain() {
  const name = newDomainName.value.trim()
  if (!name) { ElMessage.warning('请输入域名'); return }
  domainCreating.value = true
  try {
    const d = await knowledgeApi.createDomain({
      name,
      description: newDomainDesc.value || undefined,
    })
    domains.value.unshift(d)
    activeDomainId.value = d.id
    showNewDomainForm.value = false
    newDomainName.value = ''
    newDomainDesc.value = ''
    ElMessage.success('知识域已创建')
  } catch { ElMessage.error('创建失败') }
  domainCreating.value = false
}

async function handleDeleteDomain(id: number) {
  try {
    await knowledgeApi.deleteDomain(id)
    domains.value = domains.value.filter(d => d.id !== id)
    if (activeDomainId.value === id) activeDomainId.value = null
    ElMessage.success('已删除')
  } catch { ElMessage.error('删除失败') }
}

// ========== 筛选 ==========
const papers = ref<any[]>([])
const selectedIds = ref<number[]>([])
const nameInput = ref('')
const loading = ref(false)
const creating = ref(false)

// ========== 图谱 ==========
const graphId = ref<number | null>(null)
const graph = ref<KnowledgeGraph | null>(null)

interface HistoryItem {
  id: number
  name: string
  paperCount?: number
  nodeCount?: number
  edgeCount?: number
  updatedAt?: string
}

const graphHistory = ref<HistoryItem[]>([])
const showBuildModal = ref(false)
const paperSearchQuery = ref('')
const menuOpenId = ref<number | null>(null)
const editingId = ref<number | null>(null)
const editName = ref('')

const filteredPapers = computed(() => {
  const q = paperSearchQuery.value.trim().toLowerCase()
  if (!q) return papers.value
  return papers.value.filter((p: any) => {
    const title = (p.title || p.original_filename || '').toLowerCase()
    return title.includes(q)
  })
})

function openBuildModal() {
  if (!activeDomainId.value) {
    ElMessage.warning('请先在左侧选择一个知识域')
    return
  }
  paperSearchQuery.value = ''
  showBuildModal.value = true
}

function closeBuildModal() {
  showBuildModal.value = false
  paperSearchQuery.value = ''
}

async function loadGraphHistory() {
  try {
    const apiList = await knowledgeApi.list()
    let localMeta: Record<number, any> = {}
    try {
      const cached = JSON.parse(localStorage.getItem('graph_ids') || '[]')
      for (const item of cached) {
        if (item.id) localMeta[item.id] = item
      }
    } catch { /* */ }

    graphHistory.value = apiList.map(g => ({
      id: g.id,
      name: g.name,
      domainId: g.domain_id,
      paperCount: g.paper_count,
      nodeCount: localMeta[g.id]?.nodeCount ?? 0,
      edgeCount: localMeta[g.id]?.edgeCount ?? 0,
      updatedAt: localMeta[g.id]?.updatedAt || g.created_at,
    }))
  } catch {
    try { graphHistory.value = JSON.parse(localStorage.getItem('graph_ids') || '[]') } catch { /* */ }
  }
}

onMounted(async () => {
  await loadDomains()
  await loadGraphHistory()

  try {
    const res: any = await papersApi.list({ limit: 100 })
    papers.value = Array.isArray(res) ? res : (res?.data || res?.papers || [])
  } catch { /* */ }

  const id = Number(route.query.id)
  if (id) await loadGraph(id)
})

// ========== 论文选择 ==========
function paperChecked(id: number): boolean { return selectedIds.value.includes(id) }
function togglePaper(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx > -1) selectedIds.value.splice(idx, 1)
  else {
    selectedIds.value.push(id)
    triggerSuggest()
  }
}

// ========== AI 域建议 ==========
function triggerSuggest() {
  if (suggestionTimer) clearTimeout(suggestionTimer)
  if (selectedIds.value.length === 0) {
    aiSuggestions.value = []
    return
  }
  suggestionTimer = setTimeout(() => fetchSuggestions(), 600)
}

async function fetchSuggestions() {
  suggestionsLoading.value = true
  try {
    const res = await knowledgeApi.suggestDomain({ paper_ids: selectedIds.value.slice(0, 5) })
    aiSuggestions.value = res.suggestions || []
  } catch { aiSuggestions.value = [] }
  suggestionsLoading.value = false
}

async function adoptSuggestion(s: DomainSuggestion) {
  if (s.match_type === 'existing' && s.domain_id) {
    activeDomainId.value = s.domain_id
    aiSuggestions.value = []
    ElMessage.success(`已选择「${s.domain_name}」`)
  } else {
    newDomainName.value = s.domain_name
    newDomainDesc.value = s.reason
    showNewDomainForm.value = true
    aiSuggestions.value = []
  }
}

function dismissSuggestions() {
  aiSuggestions.value = []
}

// ========== 实体融合 ==========
async function loadMergeSuggestions() {
  if (!graph.value?.domain_id || !graph.value?.nodes?.length) return
  mergeLoading.value = true
  try {
    const res = await knowledgeApi.getMergeSuggestions(graph.value.domain_id)
    mergeSuggestions.value = res.suggestions || []
  } catch { mergeSuggestions.value = [] }
  mergeLoading.value = false
}

async function handleMerge(sourceId: number, targetId: number) {
  if (!graph.value?.domain_id) return
  try {
    const result = await knowledgeApi.mergeEntities(graph.value.domain_id, {
      source_node_id: sourceId, target_node_id: targetId,
    })
    ElMessage.success(`已合并（${result.merged_edges} 条边重定向${result.deleted_duplicates ? `，${result.deleted_duplicates} 条重复边已删除` : ''}）`)
    if (graphId.value) await loadGraph(graphId.value)
    mergeSuggestions.value = []
  } catch { ElMessage.error('合并失败') }
}

// ========== 知识推荐 ==========
async function loadRecommendations() {
  if (!graph.value?.domain_id) return
  recLoading.value = true
  try {
    const res = await knowledgeApi.getRecommendations(graph.value.domain_id)
    recommendations.value = res.recommendations || []
  } catch { recommendations.value = [] }
  recLoading.value = false
}

async function handleExplore(concept: string, source: string) {
  if (!graph.value?.domain_id) return
  try {
    await knowledgeApi.exploreConcept(graph.value.domain_id, { concept, source })
    ElMessage.success(`已标记探索："${concept}"`)
  } catch { /* silent */ }
}

// ========== 图谱操作 ==========
async function handleCreate() {
  if (selectedIds.value.length === 0) { ElMessage.warning('请至少选择一篇文献'); return }
  if (!activeDomainId.value) { ElMessage.warning('请先选择或创建一个知识域'); return }
  creating.value = true
  try {
    const kg = await knowledgeApi.create({
      paper_ids: selectedIds.value,
      name: nameInput.value || undefined,
      domain_id: activeDomainId.value,
    })
    graphId.value = kg.id
    graph.value = kg
    console.log('[GraphView:create] kg.id =', kg.id, '| kg.nodes =', kg.nodes?.length, '| kg.edges =', kg.edges?.length)
    saveToHistory(kg.id, kg.name, kg)
    await loadGraphHistory()
    router.replace({ query: { id: kg.id } })
    showBuildModal.value = false
    paperSearchQuery.value = ''
    selectedIds.value = []
    ElMessage.success('知识图谱已构建')
    await loadDomains()
  } catch (err: any) {
    console.error('[GraphView:create] 构建失败详情:', err?.message || err)
    ElMessage.error('构建失败')
  }
  creating.value = false
}

async function loadGraph(id: number, updateUrl = true) {
  loading.value = true
  try {
    const kg = await knowledgeApi.get(id)
    console.log('[GraphView:loadGraph] kg.id =', kg.id, '| kg.nodes =', kg.nodes?.length, '| kg.edges =', kg.edges?.length)
    graph.value = kg
    graphId.value = id
    saveToHistory(id, kg.name, kg)
    if (updateUrl) router.replace({ query: { id } })
    if (kg.domain_id) {
      // 自动同步知识域选择
      if (activeDomainId.value !== kg.domain_id) {
        activeDomainId.value = kg.domain_id
      }
      await loadMergeSuggestions()
      await loadRecommendations()
    }
  } catch { ElMessage.error('图谱加载失败') }
  loading.value = false
}

function saveToHistory(id: number, name: string, kg?: KnowledgeGraph) {
  const safeName = name || `图谱 #${id}`
  const exists = graphHistory.value.find(h => h.id === id)
  const meta = kg ? {
    paperCount: (kg as any).paper_count ?? (kg as any).paper_ids?.length,
    nodeCount: kg.nodes?.length,
    edgeCount: kg.edges?.length,
  } : {}
  if (!exists) {
    graphHistory.value.unshift({ id, name: safeName, ...meta, updatedAt: new Date().toISOString() })
    if (graphHistory.value.length > 20) graphHistory.value.pop()
  } else {
    Object.assign(exists, { name: safeName, ...meta, updatedAt: new Date().toISOString() })
  }
  try {
    localStorage.setItem('graph_ids', JSON.stringify(graphHistory.value))
  } catch {
    console.warn('[GraphView] localStorage写入失败，图谱历史未能持久化')
  }
}

// 返回构建模式
function backToBuild() {
  graphId.value = null
  graph.value = null
  router.replace({ query: {} })
  loadDomains()
}

// 点击卡片进入图谱
function enterGraph(id: number) {
  loadGraph(id)
}

// 从历史记录中删除
function removeFromHistory(id: number) {
  graphHistory.value = graphHistory.value.filter(h => h.id !== id)
  menuOpenId.value = null
  syncHistoryToStorage()
}

// 开始重命名
function startRename(h: HistoryItem) {
  editingId.value = h.id
  editName.value = h.name
  menuOpenId.value = null
}

// 确认重命名
function confirmRename() {
  const item = graphHistory.value.find(h => h.id === editingId.value)
  if (item && editName.value.trim()) {
    item.name = editName.value.trim()
    syncHistoryToStorage()
  }
  editingId.value = null
  editName.value = ''
}

// 取消重命名
function cancelRename() {
  editingId.value = null
  editName.value = ''
}

function syncHistoryToStorage() {
  try {
    localStorage.setItem('graph_ids', JSON.stringify(graphHistory.value))
  } catch { /* */ }
}

function toggleMenu(id: number) {
  menuOpenId.value = menuOpenId.value === id ? null : id
}

function closeMenu() {
  menuOpenId.value = null
}
</script>

<template>
  <div class="workspace">
    <!-- ========== 左侧边栏：知识域导航 ========== -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h3 class="sidebar-title">知识域</h3>
        <span class="sidebar-count" v-if="domains.length">{{ domains.length }}</span>
      </div>

      <!-- AI 感知建议 -->
      <div v-if="aiSuggestions.length && selectedIds.length" class="sidebar-ai-panel">
        <div class="sidebar-ai-header">
          <span class="sidebar-ai-title">✨ AI 建议</span>
          <span v-if="suggestionsLoading" class="sidebar-ai-loading">分析中...</span>
          <button class="sidebar-ai-close" @click="dismissSuggestions">&times;</button>
        </div>
        <div
          v-for="(s, i) in aiSuggestions"
          :key="i"
          class="sidebar-ai-item"
          :class="{ 'ai-existing': s.match_type === 'existing', 'ai-new': s.match_type === 'new' }"
          @click="adoptSuggestion(s)"
        >
          <span class="sidebar-ai-badge">{{ s.match_type === 'existing' ? '已有' : '新建' }}</span>
          <span class="sidebar-ai-name">{{ s.domain_name }}</span>
          <span class="sidebar-ai-reason">{{ s.reason }}</span>
        </div>
      </div>

      <!-- 知识域列表 -->
      <nav class="domain-nav">
        <div
          v-for="d in domains"
          :key="d.id"
          class="domain-nav-item"
          :class="{ active: d.id === activeDomainId }"
          @click="activeDomainId = d.id"
        >
          <span class="domain-nav-icon">📁</span>
          <div class="domain-nav-info">
            <span class="domain-nav-name">{{ d.name }}</span>
            <span class="domain-nav-meta">{{ d.graph_count }} 图谱 · {{ d.paper_count }} 论文</span>
          </div>
          <button
            class="domain-nav-delete"
            title="删除知识域"
            @click.stop="handleDeleteDomain(d.id)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
            </svg>
          </button>
        </div>

        <div v-if="!domains.length && !showNewDomainForm" class="domain-nav-empty">
          暂无知识域，请新建一个
        </div>
      </nav>

      <!-- 新建知识域表单 -->
      <div v-if="showNewDomainForm" class="sidebar-new-form">
        <input
          v-model="newDomainName"
          class="sidebar-input"
          placeholder="域名，如：深度学习"
          @keyup.enter="handleCreateDomain"
        />
        <input
          v-model="newDomainDesc"
          class="sidebar-input"
          placeholder="简要描述（可选）"
        />
        <div class="sidebar-new-actions">
          <button class="sidebar-btn-confirm" :disabled="domainCreating" @click="handleCreateDomain">
            {{ domainCreating ? '创建中...' : '确认' }}
          </button>
          <button class="sidebar-btn-cancel" @click="showNewDomainForm = false; newDomainName = ''; newDomainDesc = ''">取消</button>
        </div>
      </div>

      <!-- 新建知识域按钮 -->
      <button v-if="!showNewDomainForm" class="sidebar-new-btn" @click="showNewDomainForm = true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新建知识域
      </button>
    </aside>

    <!-- ========== 右侧主内容区 ========== -->
    <main class="main-content">
      <!-- Header -->
      <header class="workspace-header">
        <div class="header-left">
          <h1 class="header-title">{{ activeDomain ? activeDomain.name : '知识图谱工作台' }}</h1>
          <span v-if="activeDomain" class="header-subtitle">
            {{ activeDomain.graph_count }} 图谱 · {{ activeDomain.paper_count }} 论文
          </span>
        </div>
        <div class="header-right">
          <button
            v-if="graphId"
            class="btn-secondary"
            @click="backToBuild"
          >
            &larr; 返回
          </button>
          <button
            v-if="!graphId"
            class="btn-primary"
            @click="openBuildModal"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            构建新图谱
          </button>
        </div>
      </header>

      <!-- Body -->
      <div class="workspace-body" @click="closeMenu">
        <!-- ===== 主页：历史图谱卡片网格 ===== -->
        <template v-if="!graphId">
          <!-- 历史图谱卡片网格 -->
          <div v-if="graphHistory.length" class="history-section">
            <div class="history-section-header">
              <h2 class="history-section-title">历史图谱</h2>
              <span class="history-section-count">{{ graphHistory.length }} 个图谱</span>
            </div>

            <div class="history-grid">
              <div
                v-for="h in graphHistory"
                :key="h.id"
                class="history-card"
                @click="enterGraph(h.id)"
              >
                <!-- 卡片头部 -->
                <div class="card-header">
                  <div class="card-title-row">
                    <template v-if="editingId === h.id">
                      <input
                        v-model="editName"
                        class="card-rename-input"
                        @keyup.enter="confirmRename"
                        @keyup.escape="cancelRename"
                        @click.stop
                        @blur="confirmRename"
                        autofocus
                      />
                    </template>
                    <template v-else>
                      <h4 class="card-title">{{ h.name }}</h4>
                    </template>
                  </div>
                  <div class="card-menu" @click.stop>
                    <button class="card-menu-btn" @click="toggleMenu(h.id)" title="更多操作">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>
                      </svg>
                    </button>
                    <div v-if="menuOpenId === h.id" class="card-dropdown">
                      <button class="card-dropdown-item" @click="startRename(h)">重命名</button>
                      <button class="card-dropdown-item card-dropdown-danger" @click="removeFromHistory(h.id)">删除</button>
                    </div>
                  </div>
                </div>

                <!-- 数据区：label / value 竖线分隔 -->
                <div class="card-stats">
                  <span class="stat-group">
                    <span class="stat-label">实体</span>
                    <span class="stat-value">{{ h.nodeCount ?? 0 }}</span>
                  </span>
                  <span class="stat-sep">|</span>
                  <span class="stat-group">
                    <span class="stat-label">关系</span>
                    <span class="stat-value">{{ h.edgeCount ?? 0 }}</span>
                  </span>
                  <span class="stat-sep">|</span>
                  <span class="stat-group">
                    <span class="stat-label">文献</span>
                    <span class="stat-value">{{ h.paperCount ?? '-' }}</span>
                  </span>
                </div>

                <!-- 底部 -->
                <div class="card-footer">
                  <span class="card-time">更新于 {{ new Date(h.updatedAt || Date.now()).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-if="!graphHistory.length" class="history-empty">
            <div class="empty-illustration">
              <h3>还没有知识图谱</h3>
              <p>点击上方「构建新图谱」按钮，从文献中抽取知识</p>
            </div>
          </div>
        </template>

        <!-- ===== 图谱查看模式 ===== -->
        <div v-else class="graph-view">
          <GraphCanvas
            :cypher-query="graphCypher"
            :graph-id="graphId"
            :graph-data="graph"
          />

          <!-- 实体融合建议 -->
          <div v-if="mergeSuggestions.length" class="merge-panel">
            <div class="merge-panel-header">
              <span class="merge-panel-title">🔗 发现疑似同义实体</span>
              <span class="merge-panel-hint">相似度越高越可能是同一概念的不同表述</span>
            </div>
            <div
              v-for="(s, i) in mergeSuggestions"
              :key="i"
              class="merge-row"
            >
              <div class="merge-entities">
                <span class="merge-node merge-source">{{ s.node_a.name }}</span>
                <span class="merge-arrow">&rarr;</span>
                <span class="merge-node merge-target">{{ s.node_b.name }}</span>
                <span class="merge-sim">{{ (s.similarity * 100).toFixed(0) }}%</span>
              </div>
              <button class="merge-btn" @click="handleMerge(s.node_a.id, s.node_b.id)">合并</button>
            </div>
          </div>

          <!-- 知识推荐 -->
          <div v-if="recommendations.length" class="rec-panel">
            <div class="rec-panel-header">
              <span class="rec-panel-title">💡 知识拓展建议</span>
              <span class="rec-panel-hint">基于图谱关系 + AI 推理</span>
            </div>
            <div v-for="(r, i) in recommendations" :key="i" class="rec-row">
              <div class="rec-left">
                <span class="rec-badge" :class="r.source === 'relation' ? 'rec-relation' : 'rec-llm'">
                  {{ r.source === 'relation' ? '关联推理' : 'AI推荐' }}
                </span>
                <span class="rec-concept">{{ r.concept }}</span>
                <span class="rec-type">{{ r.entity_type }}</span>
              </div>
              <div class="rec-right">
                <span class="rec-reason">{{ r.reason }}</span>
                <button class="rec-explore-btn" @click="handleExplore(r.concept, r.source)">标记探索</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- ========== 构建新图谱 Modal ========== -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showBuildModal" class="modal-overlay" @click.self="closeBuildModal">
          <div class="modal-dialog" @click.stop>
            <!-- Modal Header -->
            <div class="modal-header">
              <h3 class="modal-title">构建新图谱</h3>
              <span class="modal-domain-badge" v-if="activeDomain">{{ activeDomain.name }}</span>
              <button class="modal-close" @click="closeBuildModal">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>

            <!-- Modal Body -->
            <div class="modal-body">
              <!-- 图谱名称 -->
              <div class="modal-field">
                <label class="modal-label">图谱名称（可选）</label>
                <input
                  v-model="nameInput"
                  class="modal-input"
                  placeholder="如：CV综述知识图谱"
                />
              </div>

              <!-- 搜索文献 -->
              <div class="modal-field">
                <div class="modal-search-row">
                  <label class="modal-label">选择文献</label>
                  <span class="modal-search-count">共 {{ papers.length }} 篇 · 已选 {{ selectedIds.length }}</span>
                </div>
                <div class="modal-search-box">
                  <svg class="modal-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                  </svg>
                  <input
                    v-model="paperSearchQuery"
                    class="modal-search-input"
                    placeholder="搜索文献标题..."
                  />
                  <button
                    v-if="paperSearchQuery"
                    class="modal-search-clear"
                    @click="paperSearchQuery = ''"
                  >
                    &times;
                  </button>
                </div>
              </div>

              <!-- 文献列表 -->
              <div class="modal-paper-list" v-if="filteredPapers.length">
                <label
                  v-for="p in filteredPapers"
                  :key="p.id"
                  class="modal-paper-item"
                  :class="{ checked: paperChecked(p.id) }"
                >
                  <div class="modal-paper-check">
                    <input
                      type="checkbox"
                      :checked="paperChecked(p.id)"
                      @change="togglePaper(p.id)"
                    />
                  </div>
                  <div class="modal-paper-body">
                    <span class="modal-paper-title">{{ p.title || p.original_filename }}</span>
                    <span class="modal-paper-meta" v-if="p.authors">{{ p.authors }}</span>
                  </div>
                </label>
              </div>

              <div v-else class="modal-paper-empty">
                <span v-if="paperSearchQuery">未找到匹配「{{ paperSearchQuery }}」的文献</span>
                <span v-else>暂无文献，请先上传文献</span>
              </div>
            </div>

            <!-- Modal Footer -->
            <div class="modal-footer">
              <button class="modal-btn-cancel" @click="closeBuildModal">取消</button>
              <button
                class="modal-btn-confirm"
                :disabled="selectedIds.length === 0 || creating"
                @click="handleCreate"
              >
                <template v-if="creating">
                  <span class="modal-spinner"></span>
                  构建中...
                </template>
                <template v-else>
                  确认构建 (已选 {{ selectedIds.length }} 篇)
                </template>
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* ========================================
   Workspace Layout
   ======================================== */
.workspace {
  display: flex;
  height: 100%;
  background: #F8FAFC;
  overflow: hidden;
}

/* ========================================
   Sidebar (260px)
   ======================================== */
.sidebar {
  width: 260px;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: none;
  box-shadow: 1px 0 0 0 rgba(0, 0, 0, 0.04), 2px 0 8px rgba(0, 0, 0, 0.03);
  z-index: 10;
  padding: 24px 0 16px;
  overflow-y: auto;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  margin-bottom: 4px;
}

.sidebar-title {
  font-size: 12px;
  font-weight: 600;
  color: #94A3B8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0;
}

.sidebar-count {
  font-size: 11px;
  font-weight: 600;
  color: #64748B;
  background: #F1F5F9;
  padding: 2px 8px;
  border-radius: 10px;
}

/* ---- AI 建议面板 ---- */
.sidebar-ai-panel {
  margin: 8px 12px;
  padding: 10px 12px;
  background: linear-gradient(135deg, rgba(250, 173, 20, 0.06), rgba(250, 173, 20, 0.02));
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(250, 173, 20, 0.15);
  animation: aiFadeIn 0.25s ease-out;
}

@keyframes aiFadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.sidebar-ai-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.sidebar-ai-title {
  font-size: 12px;
  font-weight: 700;
  color: #D48806;
}

.sidebar-ai-loading {
  font-size: 11px;
  color: #94A3B8;
}

.sidebar-ai-close {
  margin-left: auto;
  padding: 0 4px;
  border: none;
  background: transparent;
  font-size: 16px;
  color: #94A3B8;
  cursor: pointer;
  line-height: 1;
}

.sidebar-ai-close:hover {
  color: #475569;
}

.sidebar-ai-item {
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.15s;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar-ai-item:last-child { margin-bottom: 0; }

.sidebar-ai-item.ai-existing {
  background: rgba(59, 130, 246, 0.06);
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.15);
}

.sidebar-ai-item.ai-new {
  background: rgba(250, 173, 20, 0.06);
  box-shadow: inset 0 0 0 1px rgba(250, 173, 20, 0.15);
}

.sidebar-ai-item:hover { filter: brightness(0.97); }

.sidebar-ai-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 6px;
  color: #fff;
  width: fit-content;
}

.ai-existing .sidebar-ai-badge { background: #3B82F6; }
.ai-new .sidebar-ai-badge { background: #D48806; }

.sidebar-ai-name {
  font-size: 13px;
  font-weight: 600;
  color: #1E293B;
}

.sidebar-ai-reason {
  font-size: 11px;
  color: #94A3B8;
  line-height: 1.3;
}

/* ---- 知识域导航 ---- */
.domain-nav {
  flex: 1;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.domain-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}

.domain-nav-item:hover {
  background: #F1F5F9;
}

.domain-nav-item.active {
  background: #EFF6FF;
  box-shadow: inset 3px 0 0 0 #3B82F6;
}

.domain-nav-item.active .domain-nav-name {
  color: #2563EB;
  font-weight: 600;
}

.domain-nav-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.domain-nav-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.domain-nav-name {
  font-size: 13px;
  font-weight: 500;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.domain-nav-meta {
  font-size: 11px;
  color: #94A3B8;
}

.domain-nav-delete {
  opacity: 0;
  padding: 4px;
  border: none;
  background: transparent;
  color: #94A3B8;
  cursor: pointer;
  border-radius: 4px;
  flex-shrink: 0;
  transition: all 0.15s;
}

.domain-nav-item:hover .domain-nav-delete {
  opacity: 1;
}

.domain-nav-delete:hover {
  color: #EF4444;
  background: #FEE2E2;
}

.domain-nav-empty {
  padding: 20px 12px;
  font-size: 13px;
  color: #94A3B8;
  text-align: center;
}

/* ---- 新建知识域表单 ---- */
.sidebar-new-form {
  margin: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: #F8FAFC;
  border-radius: 10px;
  box-shadow: 0 0 0 1px #3B82F6;
  animation: aiFadeIn 0.2s ease-out;
}

.sidebar-input {
  padding: 8px 12px;
  border: none;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
  color: #334155;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: box-shadow 0.15s;
}

.sidebar-input:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.sidebar-input::placeholder {
  color: #94A3B8;
}

.sidebar-new-actions {
  display: flex;
  gap: 8px;
}

.sidebar-btn-confirm {
  flex: 1;
  padding: 7px 0;
  background: #3B82F6;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.sidebar-btn-confirm:hover:not(:disabled) { background: #2563EB; }
.sidebar-btn-confirm:disabled { opacity: 0.5; cursor: not-allowed; }

.sidebar-btn-cancel {
  flex: 1;
  padding: 7px 0;
  background: #fff;
  color: #64748B;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: all 0.15s;
}

.sidebar-btn-cancel:hover { background: #F1F5F9; }

/* ---- 新建知识域按钮 ---- */
.sidebar-new-btn {
  margin: 8px 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 0;
  background: #fff;
  color: #3B82F6;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: all 0.15s;
}

.sidebar-new-btn:hover {
  background: #EFF6FF;
  box-shadow: 0 0 0 1px #3B82F6;
}

/* ---- 新建知识域按钮 ---- END ---- */

/* ========================================
   History Section — Card Grid
   ======================================== */
.history-section {
  margin-bottom: 24px;
}

.history-section-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 20px;
}

.history-section-title {
  font-size: 18px;
  font-weight: 700;
  color: #0F172A;
  margin: 0;
}

.history-section-count {
  font-size: 13px;
  color: #94A3B8;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

/* ---- 卡片 ---- */
.history-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 0 0 1px #E2E8F0;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
}

.history-card:hover {
  box-shadow: 0 0 0 1px #CBD5E1, 0 12px 24px rgba(0, 0, 0, 0.06);
  transform: translateY(-4px);
}

/* ---- 卡片头部 ---- */
.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
  gap: 8px;
}

.card-title-row {
  flex: 1;
  min-width: 0;
}

.card-title {
  font-size: 15px;
  font-weight: 700;
  color: #0F172A;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-rename-input {
  width: 100%;
  padding: 6px 10px;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 700;
  color: #0F172A;
  background: #F8FAFC;
  outline: none;
  box-shadow: 0 0 0 2px #3B82F6;
}

/* ---- 操作菜单 ---- */
.card-menu {
  position: relative;
  flex-shrink: 0;
}

.card-menu-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #94A3B8;
  cursor: pointer;
  transition: all 0.15s;
}

.card-menu-btn:hover {
  background: #F1F5F9;
  color: #475569;
}

.card-dropdown {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1), 0 0 0 1px #E2E8F0;
  padding: 4px;
  z-index: 20;
  min-width: 120px;
  animation: dropdownIn 0.12s ease-out;
}

@keyframes dropdownIn {
  from { opacity: 0; transform: translateY(-4px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.card-dropdown-item {
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #334155;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  transition: background 0.1s;
}

.card-dropdown-item:hover {
  background: #F1F5F9;
}

.card-dropdown-danger {
  color: #EF4444;
}

.card-dropdown-danger:hover {
  background: #FEF2F2;
}

/* ---- 数据统计区 ---- */
.card-stats {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.stat-group {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: #94A3B8;
  font-weight: 500;
  letter-spacing: 0.2px;
}

.stat-value {
  font-size: 14px;
  font-weight: 700;
  color: #1E293B;
}

.stat-sep {
  font-size: 12px;
  color: #E2E8F0;
  user-select: none;
}

/* ---- 卡片底部 ---- */
.card-footer {
  padding-top: 14px;
  border-top: 1px solid #F1F5F9;
}

.card-time {
  font-size: 12px;
  color: #94A3B8;
  font-weight: 400;
}

/* ---- 空状态 ---- */
.history-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

.empty-illustration {
  text-align: center;
}

.empty-illustration h3 {
  font-size: 16px;
  font-weight: 600;
  color: #64748B;
  margin: 0 0 8px;
}

.empty-illustration p {
  font-size: 14px;
  color: #94A3B8;
  margin: 0;
}


/* ========================================
   Main Content
   ======================================== */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

/* ---- Header ---- */
.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 32px;
  background: #fff;
  box-shadow: 0 1px 0 0 rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.02);
  flex-shrink: 0;
  z-index: 5;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.header-title {
  font-size: 22px;
  font-weight: 700;
  color: #0F172A;
  margin: 0;
  letter-spacing: -0.3px;
}

.header-subtitle {
  font-size: 13px;
  color: #94A3B8;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-primary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  background: #3B82F6;
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.3), 0 1px 2px rgba(59, 130, 246, 0.2);
  white-space: nowrap;
}

.btn-primary:hover {
  background: #2563EB;
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3), 0 2px 4px rgba(59, 130, 246, 0.2);
  transform: translateY(-0.5px);
}

.btn-primary:active {
  transform: translateY(0);
}

.btn-secondary {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 16px;
  background: #fff;
  color: #64748B;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn-secondary:hover {
  background: #F8FAFC;
  color: #334155;
  box-shadow: 0 0 0 1px #CBD5E1;
}

/* ---- Body ---- */
.workspace-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}

/* ========================================
   Modal — 构建新图谱
   ======================================== */

/* ---- Overlay ---- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-active .modal-dialog,
.modal-fade-leave-active .modal-dialog {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
.modal-fade-enter-from .modal-dialog {
  transform: scale(0.96) translateY(8px);
  opacity: 0;
}
.modal-fade-leave-to .modal-dialog {
  transform: scale(0.96) translateY(8px);
  opacity: 0;
}

/* ---- Dialog ---- */
.modal-dialog {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  width: 100%;
  max-width: 640px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ---- Modal Header ---- */
.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid #F1F5F9;
  flex-shrink: 0;
}

.modal-title {
  font-size: 17px;
  font-weight: 700;
  color: #0F172A;
  margin: 0;
}

.modal-domain-badge {
  padding: 3px 10px;
  background: #EFF6FF;
  color: #3B82F6;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
}

.modal-close {
  margin-left: auto;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #94A3B8;
  cursor: pointer;
  transition: all 0.15s;
}

.modal-close:hover {
  background: #F1F5F9;
  color: #475569;
}

/* ---- Modal Body ---- */
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.modal-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.modal-label {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.modal-input {
  padding: 10px 14px;
  border: none;
  border-radius: 10px;
  background: #F8FAFC;
  font-size: 14px;
  color: #334155;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: box-shadow 0.15s;
}

.modal-input:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.modal-input::placeholder {
  color: #94A3B8;
}

/* ---- 搜索 ---- */
.modal-search-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-search-count {
  font-size: 12px;
  color: #94A3B8;
}

.modal-search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.modal-search-icon {
  position: absolute;
  left: 12px;
  pointer-events: none;
}

.modal-search-input {
  width: 100%;
  padding: 9px 36px 9px 36px;
  border: none;
  border-radius: 10px;
  background: #F8FAFC;
  font-size: 13px;
  color: #334155;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: box-shadow 0.15s;
}

.modal-search-input:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.modal-search-input::placeholder {
  color: #94A3B8;
}

.modal-search-clear {
  position: absolute;
  right: 8px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: #E2E8F0;
  color: #64748B;
  font-size: 14px;
  cursor: pointer;
  line-height: 1;
}

.modal-search-clear:hover {
  background: #CBD5E1;
}

/* ---- 文献列表 ---- */
.modal-paper-list {
  max-height: 320px;
  overflow-y: auto;
  border-radius: 10px;
  box-shadow: 0 0 0 1px #E2E8F0;
}

.modal-paper-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.1s;
  border-bottom: 1px solid #F1F5F9;
}

.modal-paper-item:last-child {
  border-bottom: none;
}

.modal-paper-item:nth-child(even) {
  background: #F8FAFC;
}

.modal-paper-item:nth-child(odd) {
  background: #fff;
}

.modal-paper-item:hover {
  background: #EFF6FF !important;
}

.modal-paper-item.checked {
  background: #EFF6FF !important;
}

.modal-paper-check {
  flex-shrink: 0;
}

.modal-paper-check input {
  accent-color: #3B82F6;
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.modal-paper-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.modal-paper-title {
  font-size: 13px;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.modal-paper-item.checked .modal-paper-title {
  color: #1D4ED8;
  font-weight: 600;
}

.modal-paper-meta {
  font-size: 11px;
  color: #94A3B8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.modal-paper-empty {
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: #94A3B8;
}

/* ---- Modal Footer ---- */
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 24px;
  border-top: 1px solid #F1F5F9;
  flex-shrink: 0;
}

.modal-btn-cancel {
  padding: 9px 20px;
  background: #fff;
  color: #64748B;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: all 0.15s;
}

.modal-btn-cancel:hover {
  background: #F8FAFC;
}

.modal-btn-confirm {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 24px;
  background: #3B82F6;
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.3);
}

.modal-btn-confirm:hover:not(:disabled) {
  background: #2563EB;
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3);
}

.modal-btn-confirm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ========================================
   Graph View
   ======================================== */
.graph-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.graph-view :deep(.graph-canvas) {
  flex: 1;
  min-height: 480px;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.03);
}

/* ========================================
   Merge Panel
   ======================================== */
.merge-panel {
  background: #FFFBEB;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 0 0 1px rgba(250, 173, 20, 0.15);
  flex-shrink: 0;
}

.merge-panel-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.merge-panel-title {
  font-weight: 600;
  font-size: 14px;
  color: #D48806;
}

.merge-panel-hint {
  font-size: 12px;
  color: #94A3B8;
}

.merge-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 8px;
  box-shadow: 0 0 0 1px #F1F5F9;
}

.merge-row:last-child { margin-bottom: 0; }

.merge-entities {
  display: flex;
  align-items: center;
  gap: 8px;
}

.merge-node {
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.merge-source { background: #EFF6FF; color: #2563EB; }
.merge-target { background: #ECFDF5; color: #059669; }
.merge-arrow { color: #94A3B8; font-size: 12px; }

.merge-sim {
  background: #F8FAFC;
  color: #D97706;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  margin-left: 4px;
}

.merge-btn {
  padding: 5px 16px;
  border: none;
  border-radius: 8px;
  background: #fff;
  color: #64748B;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: all 0.15s;
}

.merge-btn:hover {
  color: #EA580C;
  box-shadow: 0 0 0 1px #EA580C;
  background: #FFF7ED;
}

/* ========================================
   Recommendation Panel
   ======================================== */
.rec-panel {
  background: #F0FDF4;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 0 0 1px rgba(16, 185, 129, 0.15);
  flex-shrink: 0;
}

.rec-panel-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.rec-panel-title {
  font-weight: 600;
  font-size: 14px;
  color: #059669;
}

.rec-panel-hint {
  font-size: 12px;
  color: #94A3B8;
}

.rec-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 8px;
  box-shadow: 0 0 0 1px #F1F5F9;
  gap: 12px;
}

.rec-row:last-child { margin-bottom: 0; }

.rec-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.rec-badge {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.rec-relation { background: #EFF6FF; color: #2563EB; }
.rec-llm { background: #FFF7ED; color: #D97706; }

.rec-concept {
  font-weight: 600;
  font-size: 14px;
  color: #1E293B;
  white-space: nowrap;
}

.rec-type {
  padding: 1px 6px;
  background: #F8FAFC;
  border-radius: 4px;
  font-size: 11px;
  color: #94A3B8;
}

.rec-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.rec-reason {
  font-size: 12px;
  color: #64748B;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rec-explore-btn {
  padding: 4px 14px;
  border: none;
  border-radius: 8px;
  background: #ECFDF5;
  color: #059669;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  box-shadow: 0 0 0 1px rgba(16, 185, 129, 0.2);
  transition: all 0.15s;
}

.rec-explore-btn:hover {
  background: #059669;
  color: #fff;
}
</style>
