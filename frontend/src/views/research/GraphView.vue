<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '@/api/knowledge'
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

// ========== 画布模式 ==========
const canvasMode = ref<'detail' | 'overview'>('overview')

const activeDomain = computed(() =>
  domains.value.find(d => d.id === activeDomainId.value) || null
)

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

const graphHistory = ref<{ id: number; name: string }[]>([])
const filteredHistory = computed(() =>
  graphHistory.value.filter(h => {
    if (!activeDomainId.value) return false
    // simplified: show all, actual filter needs domain_id from API
    return true
  })
)

onMounted(async () => {
  try { graphHistory.value = JSON.parse(localStorage.getItem('graph_ids') || '[]') } catch { /* */ }
  await loadDomains()

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
    // 用户每次勾选论文，防抖触发 AI 域建议
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
    // 情况 A：直接选中有域
    activeDomainId.value = s.domain_id
    aiSuggestions.value = []
    ElMessage.success(`已选择「${s.domain_name}」`)
  } else {
    // 情况 B：AI 建议新建域 — 弹出创建表单，预填名称
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
    // 重新加载图谱以获取合并后的状态
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
    saveToHistory(kg.id, kg.name)
    router.replace({ query: { id: kg.id } })
    ElMessage.success('知识图谱已构建')
    // refresh domain stats
    await loadDomains()
  } catch { ElMessage.error('构建失败') }
  creating.value = false
}

async function loadGraph(id: number) {
  loading.value = true
  try {
    const kg = await knowledgeApi.get(id)
    graph.value = kg
    graphId.value = id
    saveToHistory(id, kg.name)
    // ★ 加载图谱后自动拉取融合建议 + 推荐
    if (kg.domain_id) {
      await loadMergeSuggestions()
      await loadRecommendations()
    }
  } catch { ElMessage.error('图谱加载失败') }
  loading.value = false
}

function saveToHistory(id: number, name: string) {
  const exists = graphHistory.value.find(h => h.id === id)
  if (!exists) {
    graphHistory.value.unshift({ id, name })
    if (graphHistory.value.length > 20) graphHistory.value.pop()
  }
  localStorage.setItem('graph_ids', JSON.stringify(graphHistory.value))
}
</script>

<template>
  <div class="graph-page">
    <div class="graph-header">
      <h2 class="graph-title">知识图谱</h2>
      <div v-if="graphId" class="graph-id-badge">图谱 #{{ graphId }} · {{ graph?.name }}</div>
    </div>

    <div class="graph-body">
      <!-- ===== 知识域选择 ===== -->
      <div v-if="!graphId" class="domain-section">
        <h3>知识域</h3>
        <p class="section-hint">知识域用于组织你的知识图谱，同一域下的知识将自动关联。建议按"深度学习""自然语言处理"等学科领域划分。</p>

        <!-- AI 感知建议面板 -->
        <div v-if="aiSuggestions.length && selectedIds.length" class="ai-suggest-panel">
          <div class="ai-suggest-header">
            <span class="ai-sparkle">✨ AI 感知建议</span>
            <span v-if="suggestionsLoading" class="ai-thinking">分析中...</span>
            <button class="ai-dismiss" @click="dismissSuggestions">×</button>
          </div>
          <div class="ai-suggest-list">
            <div
              v-for="(s, i) in aiSuggestions"
              :key="i"
              class="ai-suggest-card"
              :class="{ 'ai-new': s.match_type === 'new', 'ai-existing': s.match_type === 'existing' }"
              @click="adoptSuggestion(s)"
            >
              <div class="ai-suggest-top">
                <span class="ai-badge">{{ s.match_type === 'existing' ? '匹配已有域' : '建议新建' }}</span>
                <span class="ai-action">{{ s.match_type === 'existing' ? '点击采用' : '点击创建' }}</span>
              </div>
              <strong class="ai-suggest-name">{{ s.domain_name }}</strong>
              <p class="ai-suggest-reason">{{ s.reason }}</p>
            </div>
          </div>
        </div>

        <!-- 已有域列表 -->
        <div class="domain-list" v-if="domains.length">
          <button
            v-for="d in domains"
            :key="d.id"
            class="domain-chip"
            :class="{ active: d.id === activeDomainId, 'ai-highlighted': aiSuggestions.some(s => s.domain_id === d.id && s.match_type === 'existing') }"
            @click="activeDomainId = d.id"
          >
            <span class="domain-chip-icon" v-if="aiSuggestions.some(s => s.domain_id === d.id && s.match_type === 'existing')">✨</span>
            <span class="domain-chip-icon" v-else>{{ d.icon === 'folder' ? '📁' : d.icon }}</span>
            <span class="domain-chip-name">{{ d.name }}</span>
            <span class="domain-chip-stat">{{ d.graph_count }}图谱 · {{ d.paper_count }}论文</span>
            <span class="domain-chip-del" @click.stop="handleDeleteDomain(d.id)" title="删除">×</span>
          </button>
        </div>

        <div v-if="!showNewDomainForm" class="add-domain-row">
          <button class="add-domain-btn" @click="showNewDomainForm = true">+ 创建新知识域</button>
        </div>
        <div v-else class="new-domain-form">
          <input
            v-model="newDomainName"
            class="domain-input"
            placeholder="域名，如：深度学习、NLP..."
            @keyup.enter="handleCreateDomain"
          />
          <input
            v-model="newDomainDesc"
            class="domain-input domain-desc"
            placeholder="简要描述（可选）"
          />
          <div class="new-domain-actions">
            <button class="domain-confirm-btn" :disabled="domainCreating" @click="handleCreateDomain">
              {{ domainCreating ? '创建中...' : '确认创建' }}
            </button>
            <button class="domain-cancel-btn" @click="showNewDomainForm = false; newDomainName = ''; newDomainDesc = ''">取消</button>
          </div>
        </div>

        <!-- 知识推荐 -->
        <div v-if="recommendations.length" class="rec-panel">
          <div class="rec-header">
            <span class="rec-title">💡 知识拓展建议</span>
            <span class="rec-hint">基于图谱关系 + AI 推理，帮你发现可能感兴趣的概念</span>
          </div>
          <div v-for="(r, i) in recommendations" :key="i" class="rec-card">
            <div class="rec-card-left">
              <span class="rec-source-badge" :class="r.source === 'relation' ? 'rec-relation' : 'rec-llm'">
                {{ r.source === 'relation' ? '🔗 关联推理' : '🤖 AI推荐' }}
              </span>
              <span class="rec-concept">{{ r.concept }}</span>
              <span class="rec-type-tag">{{ r.entity_type }}</span>
            </div>
            <div class="rec-card-right">
              <span class="rec-reason" :title="r.reason">{{ r.reason }}</span>
              <button class="rec-explore-btn" @click="handleExplore(r.concept, r.source)">标记探索</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 构建面板 -->
      <div v-if="!graphId" class="build-panel">
        <h3>构建新图谱</h3>
        <p class="build-hint">
          选择文献，系统将抽取命名实体（CV/NLP模型、数据集、指标等）与关系生成知识图谱。
          <template v-if="activeDomain">
            当前域：<strong>{{ activeDomain.name }}</strong>
          </template>
          <template v-else>
            <span class="no-domain-warn">请先在上方选择或创建一个知识域</span>
          </template>
        </p>

        <div class="form-row">
          <input
            v-model="nameInput"
            class="name-input"
            placeholder="图谱名称（可选）"
          />
          <button
            class="create-btn"
            :disabled="selectedIds.length === 0 || creating || !activeDomainId"
            @click="handleCreate"
          >
            {{ creating ? '构建中...' : `构建图谱 (${selectedIds.length} 篇)` }}
          </button>
        </div>

        <div class="paper-grid" v-if="papers.length">
          <label
            v-for="p in papers"
            :key="p.id"
            class="paper-item"
            :class="{ checked: paperChecked(p.id) }"
          >
            <input type="checkbox" :checked="paperChecked(p.id)" @change="togglePaper(p.id)" />
            <span class="paper-name">{{ p.title || p.original_filename }}</span>
          </label>
        </div>
        <div v-else class="empty-hint">暂无文献，请先上传文献</div>
      </div>

      <!-- 图谱展示 -->
      <div v-else class="graph-viewer">
        <button class="back-btn" @click="graphId = null; graph = null; router.replace({ query: {} }); loadDomains()">
          ← 返回构建
        </button>
        <div v-if="graph?.domain_id && activeDomain" class="domain-context">
          域：{{ activeDomain.name }} | 图谱：{{ graph.name }}
        </div>
        <GraphCanvas
          :graph="graph"
          :mode="canvasMode"
          @change-mode="canvasMode = $event"
          @node-dblclick="() => {}"
        />

        <!-- 实体融合建议 -->
        <div v-if="mergeSuggestions.length" class="merge-panel">
          <div class="merge-header">
            <span class="merge-title">🔗 发现疑似同义实体，确认是否合并？</span>
            <span class="merge-hint">相似度越高越可能是同一概念的不同表述</span>
          </div>
          <div
            v-for="(s, i) in mergeSuggestions"
            :key="i"
            class="merge-row"
          >
            <div class="merge-entities">
              <span class="merge-node merge-source" :title="`类型: ${s.node_a.type}`">{{ s.node_a.name }}</span>
              <span class="merge-arrow">→</span>
              <span class="merge-node merge-target" :title="`类型: ${s.node_b.type}`">{{ s.node_b.name }}</span>
              <span class="merge-sim">{{ (s.similarity * 100).toFixed(0) }}%</span>
            </div>
            <button class="merge-btn" @click="handleMerge(s.node_a.id, s.node_b.id)">合并</button>
          </div>
        </div>
      </div>

      <!-- 历史图谱 -->
      <div v-if="graphHistory.length && !graphId" class="history-section">
        <h4>历史图谱</h4>
        <div class="history-list">
          <button
            v-for="h in graphHistory"
            :key="h.id"
            class="history-item"
            :class="{ active: h.id === graphId }"
            @click="loadGraph(h.id)"
          >
            #{{ h.id }} · {{ h.name }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.graph-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 24px 32px;
}

.graph-header {
  display: flex;
  align-items: baseline;
  gap: 16px;
  margin-bottom: 24px;
}

.graph-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--academic-text-main);
}

.graph-id-badge {
  font-size: 14px;
  color: var(--academic-text-muted);
}

.graph-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ===== 知识域 ===== */
.domain-section {
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 16px;
  padding: 20px 24px;
}

.domain-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin-bottom: 6px;
}

.section-hint {
  color: var(--academic-text-muted);
  font-size: 13px;
  margin-bottom: 16px;
  line-height: 1.5;
}

.domain-list {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.domain-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: 1px solid var(--academic-border);
  border-radius: 12px;
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.domain-chip:hover {
  border-color: var(--academic-primary);
}

.domain-chip.active {
  border-color: var(--academic-primary);
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.domain-chip-icon { font-size: 16px; }

.domain-chip-name { font-weight: 600; }

.domain-chip-stat {
  font-size: 12px;
  opacity: 0.7;
}

.domain-chip-del {
  margin-left: 2px;
  padding: 0 4px;
  font-size: 16px;
  opacity: 0.4;
  transition: opacity 0.15s;
}

.domain-chip-del:hover { opacity: 1; }

.add-domain-row { margin-bottom: 0; }

.add-domain-btn {
  padding: 8px 20px;
  border: 1px dashed var(--academic-border);
  border-radius: 10px;
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.add-domain-btn:hover {
  border-color: var(--academic-primary);
  color: var(--academic-primary);
}

.new-domain-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--academic-primary);
  border-radius: 12px;
  background: var(--academic-primary-light);
}

.domain-input {
  padding: 10px 14px;
  border: 1px solid var(--academic-border);
  border-radius: 10px;
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 14px;
  outline: none;
}

.domain-input:focus { border-color: var(--academic-primary); }

.new-domain-actions { display: flex; gap: 8px; }

.domain-confirm-btn {
  padding: 8px 20px;
  background: var(--academic-primary);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.domain-confirm-btn:hover:not(:disabled) { background: var(--academic-primary-hover); }
.domain-confirm-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.domain-cancel-btn {
  padding: 8px 20px;
  border: 1px solid var(--academic-border);
  border-radius: 10px;
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 14px;
  cursor: pointer;
}

/* ===== AI 感知建议面板 ===== */
.ai-suggest-panel {
  margin-bottom: 16px;
  border: 1px solid rgba(250, 173, 20, 0.35);
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(250, 173, 20, 0.06), rgba(250, 173, 20, 0.02));
  overflow: hidden;
  animation: aiSlideIn 0.3s ease-out;
}

@keyframes aiSlideIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.ai-suggest-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(250, 173, 20, 0.15);
}

.ai-sparkle {
  font-size: 14px;
  font-weight: 700;
  color: #d48806;
}

.ai-thinking {
  font-size: 12px;
  color: var(--academic-text-muted);
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.ai-dismiss {
  margin-left: auto;
  padding: 2px 8px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  font-size: 16px;
  cursor: pointer;
  border-radius: 4px;
}

.ai-dismiss:hover {
  background: rgba(0,0,0,0.05);
  color: var(--academic-text-body);
}

.ai-suggest-list {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  flex-wrap: wrap;
}

.ai-suggest-card {
  flex: 1;
  min-width: 200px;
  padding: 12px 16px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.ai-suggest-card.ai-existing {
  background: var(--academic-primary-light);
  border-color: var(--academic-primary);
}

.ai-suggest-card.ai-existing:hover {
  box-shadow: 0 0 0 2px var(--academic-primary);
}

.ai-suggest-card.ai-new {
  background: rgba(250, 173, 20, 0.08);
  border-color: rgba(250, 173, 20, 0.4);
}

.ai-suggest-card.ai-new:hover {
  box-shadow: 0 0 0 2px rgba(250, 173, 20, 0.5);
}

.ai-suggest-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.ai-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  color: #fff;
}

.ai-existing .ai-badge {
  background: var(--academic-primary);
}

.ai-new .ai-badge {
  background: #d48806;
}

.ai-action {
  font-size: 11px;
  opacity: 0.6;
}

.ai-suggest-name {
  display: block;
  font-size: 16px;
  color: var(--academic-text-main);
  margin-bottom: 4px;
}

.ai-suggest-reason {
  font-size: 12px;
  color: var(--academic-text-muted);
  margin: 0;
  line-height: 1.4;
}

/* AI 高亮的域 Chip */
.domain-chip.ai-highlighted {
  border-color: rgba(250, 173, 20, 0.6);
  background: rgba(250, 173, 20, 0.06);
  animation: glowPulse 2s ease-in-out infinite;
}

@keyframes glowPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(250, 173, 20, 0.2); }
  50% { box-shadow: 0 0 0 4px rgba(250, 173, 20, 0.1); }
}

/* ===== 构建面板 ===== */
.build-panel {
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 16px;
  padding: 24px;
}

.build-panel h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin-bottom: 8px;
}

.build-hint {
  color: var(--academic-text-muted);
  font-size: 14px;
  margin-bottom: 20px;
}

.no-domain-warn {
  color: var(--academic-warning, #e6a23c);
  font-weight: 600;
}

.form-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.name-input {
  flex: 1;
  padding: 10px 16px;
  border: 1px solid var(--academic-border);
  border-radius: 12px;
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.name-input:focus { border-color: var(--academic-primary); }

.create-btn {
  padding: 10px 24px;
  background: var(--academic-primary);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s;
}

.create-btn:hover:not(:disabled) { background: var(--academic-primary-hover); }
.create-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.paper-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.paper-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--academic-border);
  background: var(--academic-canvas);
  cursor: pointer;
  transition: all 0.15s;
  font-size: 14px;
  color: var(--academic-text-body);
}

.paper-item:hover { border-color: var(--academic-primary); }

.paper-item.checked {
  border-color: var(--academic-primary);
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.paper-item input { accent-color: var(--academic-primary); }

.paper-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-hint {
  color: var(--academic-text-muted);
  font-size: 14px;
  text-align: center;
  padding: 40px;
}

/* ===== 图谱展示 ===== */
.graph-viewer {
  flex: 1;
  min-height: 480px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 16px;
  padding: 16px;
  display: flex;
  flex-direction: column;
}

.domain-context {
  font-size: 13px;
  color: var(--academic-text-muted);
  margin-bottom: 8px;
  padding: 6px 12px;
  background: var(--academic-canvas);
  border-radius: 8px;
}

.back-btn {
  align-self: flex-start;
  padding: 8px 16px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
  margin-bottom: 12px;
  transition: background 0.15s;
}

.back-btn:hover { background: var(--academic-primary-light); }

.graph-viewer :deep(.graph-canvas) { flex: 1; }

/* ========== 实体融合面板 ========== */
.merge-panel {
  margin: 16px 20px 20px;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  padding: 16px;
}
.merge-header {
  display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px;
}
.merge-title { font-weight: 600; font-size: 14px; color: #d48806; }
.merge-hint { font-size: 12px; color: #999; }
.merge-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; background: #fff; border-radius: 6px; margin-bottom: 8px;
  border: 1px solid #f0f0f0;
}
.merge-entities { display: flex; align-items: center; gap: 8px; }
.merge-node {
  padding: 3px 10px; border-radius: 4px; font-size: 13px; font-weight: 500;
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.merge-source { background: #f0f5ff; color: #2f54eb; }
.merge-target { background: #e6fffb; color: #13c2c2; }
.merge-arrow { color: #bbb; font-size: 12px; }
.merge-sim {
  background: #fafafa; color: #fa8c16; font-weight: 600;
  padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 4px;
}
.merge-btn {
  padding: 4px 16px; border: 1px solid #d9d9d9; border-radius: 4px;
  background: #fff; cursor: pointer; font-size: 13px; transition: all .2s;
}
.merge-btn:hover { border-color: #ff7a45; color: #ff7a45; }

/* ========== 知识推荐面板 ========== */
.rec-panel {
  margin: 0 20px 20px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 8px;
  padding: 16px;
}
.rec-header {
  display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px;
}
.rec-title { font-weight: 600; font-size: 14px; color: #389e0d; }
.rec-hint { font-size: 12px; color: #999; }
.rec-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; background: #fff; border-radius: 6px; margin-bottom: 8px;
  border: 1px solid #f0f0f0; gap: 12px;
}
.rec-card-left { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.rec-source-badge {
  padding: 2px 8px; border-radius: 4px; font-size: 11px; white-space: nowrap;
}
.rec-relation { background: #e6f7ff; color: #1890ff; }
.rec-llm { background: #fff7e6; color: #fa8c16; }
.rec-concept { font-weight: 600; font-size: 14px; color: #333; white-space: nowrap; }
.rec-type-tag {
  padding: 1px 6px; background: #fafafa; border-radius: 3px; font-size: 11px; color: #999;
}
.rec-card-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.rec-reason {
  font-size: 12px; color: #666; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rec-explore-btn {
  padding: 4px 14px; border: 1px solid #b7eb8f; border-radius: 4px;
  background: #f6ffed; color: #389e0d; cursor: pointer; font-size: 12px; white-space: nowrap; transition: all .2s;
}
.rec-explore-btn:hover { background: #389e0d; color: #fff; }

/* ===== 历史 ===== */
.history-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--academic-text-muted);
  margin-bottom: 10px;
}

.history-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.history-item {
  padding: 6px 14px;
  border: 1px solid var(--academic-border);
  border-radius: 20px;
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.history-item:hover { border-color: var(--academic-primary); }

.history-item.active {
  border-color: var(--academic-primary);
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}
</style>
