<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '@/api/knowledge'
import { papersApi } from '@/api/papers'
import GraphCanvas from '@/components/reader/GraphCanvas.vue'
import type { KnowledgeGraph } from '@/types/domain'

const route = useRoute()
const router = useRouter()

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

onMounted(async () => {
  try { graphHistory.value = JSON.parse(localStorage.getItem('graph_ids') || '[]') } catch { /* */ }
  // 加载文献列表
  try {
    const res: any = await papersApi.list({ limit: 100 })
    papers.value = Array.isArray(res) ? res : (res?.data || res?.papers || [])
  } catch { /* */ }

  // URL 参数 ?id=3
  const id = Number(route.query.id)
  if (id) await loadGraph(id)
})

function paperChecked(id: number): boolean { return selectedIds.value.includes(id) }

function togglePaper(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx > -1) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

async function handleCreate() {
  if (selectedIds.value.length === 0) { ElMessage.warning('请至少选择一篇文献'); return }
  creating.value = true
  try {
    const kg = await knowledgeApi.create({ paper_ids: selectedIds.value, name: nameInput.value || undefined })
    graphId.value = kg.id
    graph.value = kg
    saveToHistory(kg.id, kg.name)
    router.replace({ query: { id: kg.id } })
    ElMessage.success('知识图谱已构建')
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
      <!-- 构建面板 -->
      <div v-if="!graphId" class="build-panel">
        <h3>构建新图谱</h3>
        <p class="build-hint">选择文献，系统将抽取命名实体(CV/NLP模型、数据集、指标等)与关系生成知识图谱。</p>

        <div class="form-row">
          <input
            v-model="nameInput"
            class="name-input"
            placeholder="图谱名称（可选）"
          />
          <button
            class="create-btn"
            :disabled="selectedIds.length === 0 || creating"
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
        <button class="back-btn" @click="graphId = null; graph = null; router.replace({ query: {} })">
          ← 返回构建
        </button>
        <GraphCanvas :graph="graph" />
      </div>

      <!-- 历史图谱 -->
      <div v-if="graphHistory.length" class="history-section">
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

.name-input:focus {
  border-color: var(--academic-primary);
}

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

.create-btn:hover:not(:disabled) {
  background: var(--academic-primary-hover);
}

.create-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

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

.paper-item:hover {
  border-color: var(--academic-primary);
}

.paper-item.checked {
  border-color: var(--academic-primary);
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}

.paper-item input {
  accent-color: var(--academic-primary);
}

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

.back-btn:hover {
  background: var(--academic-primary-light);
}

.graph-viewer :deep(.graph-canvas) {
  flex: 1;
}

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

.history-item:hover {
  border-color: var(--academic-primary);
}

.history-item.active {
  border-color: var(--academic-primary);
  background: var(--academic-primary-light);
  color: var(--academic-primary);
}
</style>
