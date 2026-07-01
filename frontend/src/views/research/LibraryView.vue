<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { papersApi } from '@/api/papers'
import { usePaperStore } from '@/stores/papers'
import PaperReader from '@/components/reader/PaperReader.vue'

// ── 分类接口 ──
interface Category {
  id: number
  name: string
}

// ── 基础状态 ──
const store = usePaperStore()
const editVisible = ref(false)
const form = ref<any>({})
const readerRef = ref<InstanceType<typeof PaperReader> | null>(null)
const currentReaderPaper = ref<{ id: number; title: string } | null>(null)

function openReader(paper: any) {
  currentReaderPaper.value = { id: paper.id, title: paper.title || paper.original_filename }
  nextTick(() => {
    readerRef.value?.open()
  })
}
const loading = ref(false)
const searchQuery = ref('')
const activeCategory = ref<string | number>('all')
const sortBy = ref<'date-desc' | 'date-asc' | 'title-asc' | 'title-desc'>('date-desc')
const dateRange = ref<[string, string] | null>(null)
const activeLetter = ref('')
const sidebarCollapsed = ref(false)
const sidebarHovered = ref(false)

// ── 清所有筛选（带旋转动画） ──
const isClearing = ref(false)
function clearAllFilters() {
  if (isClearing.value) return
  isClearing.value = true
  activeLetter.value = ''
  dateRange.value = null
  searchQuery.value = ''
  setTimeout(() => { isClearing.value = false }, 600)
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

// ── 上传状态 ──
interface UploadItem {
  id: number
  file: File
  progress: number
  status: 'pending' | 'uploading' | 'done' | 'error'
  message: string
}
const uploadVisible = ref(false)
const uploadItems = ref<UploadItem[]>([])
let _uploadId = 0

// ── 批量选择 ──
const selectedPaperIds = ref<Set<number>>(new Set())
const batchCategoryId = ref<number | string>('')
const showBatchBar = computed(() => selectedPaperIds.value.size > 0)

// ── 自定义分类 ──
const categories = ref<Category[]>([])
const newCategoryName = ref('')
const showNewCategory = ref(false)
const hoverCategoryId = ref<number | null>(null)
const editCategoryId = ref<number | null>(null)
const editCategoryName = ref('')

// ── 获取分类名称 ──
function getCategoryName(paper: any): string | null {
  if (!paper.category_id) return null
  return categories.value.find(c => c.id === paper.category_id)?.name || null
}

// ── 实时轮询：检测解析中的文献，自动刷新列表 ──
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    const hasProcessing = store.list.some(
      (p: any) => p.parse_status && p.parse_status !== 'completed' && p.parse_status !== 'failed'
    )
    if (hasProcessing) {
      await store.load()
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  store.load().then(startPolling)
  loadCategories()
})

onUnmounted(() => {
  stopPolling()
})

// ── 分类 API ──
async function loadCategories() {
  try {
    const res = await papersApi.categories()
    categories.value = (res || []).map((c: any) => ({ id: c.id, name: c.name }))
  } catch { /* ignore */ }
}

async function addCategory() {
  const name = newCategoryName.value.trim()
  if (!name) return
  try {
    const res = await papersApi.createCategory(name)
    categories.value.unshift({ id: res.id, name: res.name })
    newCategoryName.value = ''
    showNewCategory.value = false
    activeCategory.value = res.id
  } catch { /* ignore */ }
}

function startEditCategory(cat: Category) {
  editCategoryId.value = cat.id
  editCategoryName.value = cat.name
}

async function confirmEditCategory() {
  const name = editCategoryName.value.trim()
  const catId = editCategoryId.value
  if (!name || !catId) return
  try {
    await papersApi.updateCategory(catId, { name })
    const cat = categories.value.find(c => c.id === catId)
    if (cat) cat.name = name
    editCategoryId.value = null
    editCategoryName.value = ''
  } catch { /* ignore */ }
}

function cancelEditCategory() {
  editCategoryId.value = null
  editCategoryName.value = ''
}

async function deleteCategory(id: number) {
  try {
    await papersApi.deleteCategory(id)
    categories.value = categories.value.filter(c => c.id !== id)
    if (activeCategory.value === id) activeCategory.value = 'all'
  } catch { /* ignore */ }
}

// ── 分类描述映射 ──
const categoryLabel = computed(() => {
  if (activeCategory.value === 'all') return '全部文献'
  if (activeCategory.value === 'recent') return '最近添加'
  if (activeCategory.value === 'uncategorized') return '未分类'
  const cat = categories.value.find(c => c.id === activeCategory.value)
  return cat?.name || '全部文献'
})

// ── 文献过滤 ──
function formatDate(ts: string | null | undefined) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
}

function statusLabel(s: string | null | undefined): string {
  switch (s) {
    case 'completed': return '已解析'
    case 'failed': return '解析失败'
    case 'processing':
    case 'parsing': return '解析中'
    case 'pending': return '等待中'
    default: return '未解析'
  }
}

function parsedAuthors(row: any): string[] {
  const val = row.authors
  if (!val) return []
  if (Array.isArray(val)) return val.filter(Boolean)
  if (typeof val === 'string') {
    try {
      const arr = JSON.parse(val)
      if (Array.isArray(arr)) return arr.filter(Boolean)
    } catch {}
    return val.split(/[,;，；]/).map((s: string) => s.trim().replace(/^\[|\]$/g, '')).filter(Boolean)
  }
  return []
}

const ALPHABET = '#ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

const filteredPapers = computed(() => {
  let list = [...store.list]

  // 0. 自定义分类筛选（文件夹）
  if (typeof activeCategory.value === 'number') {
    list = list.filter(p => p.category_id === activeCategory.value)
  }

  // 1. 基础类别筛选
  if (activeCategory.value === 'recent') {
    const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
    list = list.filter(p => {
      const t = p.upload_time ? new Date(p.upload_time).getTime() : 0
      return t > sevenDaysAgo
    })
  }

  if (activeCategory.value === 'uncategorized') {
    list = list.filter(p => !p.category_id)
  }

  // 2. 搜索
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(p =>
      (p.title || p.original_filename || '').toLowerCase().includes(q) ||
      (p.journal_conf || '').toLowerCase().includes(q) ||
      (p.doi || '').toLowerCase().includes(q) ||
      (p.notes || '').toLowerCase().includes(q)
    )
  }

  // 3. 日期筛选
  if (dateRange.value && dateRange.value[0]) {
    const from = new Date(dateRange.value[0]).getTime()
    list = list.filter(p => {
      const t = p.upload_time ? new Date(p.upload_time).getTime() : 0
      return t >= from
    })
  }
  if (dateRange.value && dateRange.value[1]) {
    const to = new Date(dateRange.value[1] + 'T23:59:59').getTime()
    list = list.filter(p => {
      const t = p.upload_time ? new Date(p.upload_time).getTime() : 0
      return t <= to
    })
  }

  // 4. 首字母筛选
  if (activeLetter.value) {
    if (activeLetter.value === '#') {
      list = list.filter(p => /^[^a-zA-Z]/.test(p.title || p.original_filename || ''))
    } else {
      const letter = activeLetter.value.toLowerCase()
      list = list.filter(p => (p.title || p.original_filename || '')[0]?.toLowerCase() === letter)
    }
  }

  // 5. 排序
  list.sort((a, b) => {
    switch (sortBy.value) {
      case 'date-asc':
        return (a.upload_time || '').localeCompare(b.upload_time || '')
      case 'title-asc':
        return (a.title || a.original_filename || '').localeCompare(b.title || b.original_filename || '')
      case 'title-desc':
        return (b.title || b.original_filename || '').localeCompare(a.title || a.original_filename || '')
      case 'date-desc':
      default:
        return (b.upload_time || '').localeCompare(a.upload_time || '')
    }
  })

  return list
})

// ── CRUD ──
function edit(row: any) {
  form.value = { ...row }
  editVisible.value = true
}

async function save() {
  loading.value = true
  try {
    await papersApi.update(form.value.id, form.value)
    editVisible.value = false
    await store.load()
  } finally {
    loading.value = false
  }
}

async function remove(id: number) {
  await papersApi.remove(id)
  await store.load()
}

async function reparse(id: number) {
  await papersApi.reparse(id)
  await store.load()
}

// ── 上传 ──
function openUpload() {
  uploadItems.value = []
  uploadVisible.value = true
}

function handleFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files?.length) return

  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    const item: UploadItem = { id: ++_uploadId, file, progress: 0, status: 'pending', message: '等待上传' }
    uploadItems.value.push(item)
  }
  input.value = ''

  // 开始逐个上传
  uploadItems.value.forEach(item => uploadFile(item))
}

async function uploadFile(item: UploadItem) {
  item.status = 'uploading'
  item.message = '上传中...'
  try {
    await papersApi.upload(item.file, (e: any) => {
      if (e.total) item.progress = Math.round((e.loaded / e.total) * 100)
    })
    item.status = 'done'
    item.progress = 100
    item.message = '已上传，解析中...'
  } catch (err: any) {
    item.status = 'error'
    item.message = err?.message || '上传失败'
  }
}

function closeUpload() {
  uploadVisible.value = false
  uploadItems.value = []
  store.load()
}

// ── 批量选择 ──
function toggleSelectPaper(id: number) {
  const next = new Set(selectedPaperIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedPaperIds.value = next
}

function toggleSelectAll() {
  if (allSelected.value) {
    selectedPaperIds.value = new Set()
  } else {
    selectedPaperIds.value = new Set(filteredPapers.value.map(p => p.id))
  }
}

const allSelected = computed(() =>
  filteredPapers.value.length > 0 && filteredPapers.value.every(p => selectedPaperIds.value.has(p.id))
)

function clearSelection() {
  selectedPaperIds.value = new Set()
}

async function batchAssignCategory() {
  const catId = batchCategoryId.value
  if (catId === '' || catId === null) return
  const ids = [...selectedPaperIds.value]
  for (const pid of ids) {
    await papersApi.update(pid, { category_id: Number(catId) })
  }
  clearSelection()
  batchCategoryId.value = ''
  store.load()
}

async function batchDelete() {
  const ids = [...selectedPaperIds.value]
  for (const pid of ids) {
    await papersApi.remove(pid)
  }
  clearSelection()
  store.load()
}
</script>

<template>
  <div class="library-workspace">
    <!-- ================================= 左侧边栏 ================================= -->
    <div
      class="lib-sidebar-wrapper"
      :class="{ collapsed: sidebarCollapsed }"
      @mouseenter="sidebarHovered = true"
      @mouseleave="sidebarHovered = false"
    >
      <aside class="lib-sidebar">
        <!-- 基础菜单 -->
      <nav class="lib-nav">
        <button
          class="lib-nav-item"
          :class="{ active: activeCategory === 'all' }"
          @click="activeCategory = 'all'"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          全部文献
          <span class="lib-nav-count">{{ store.list.length }}</span>
        </button>
        <button
          class="lib-nav-item"
          :class="{ active: activeCategory === 'recent' }"
          @click="activeCategory = 'recent'"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
          最近添加
        </button>
        <button
          class="lib-nav-item"
          :class="{ active: activeCategory === 'uncategorized' }"
          @click="activeCategory = 'uncategorized'"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
          未分类
        </button>
      </nav>

      <!-- 分隔线 -->
      <div class="lib-divider"></div>

      <!-- 我的文件夹 -->
      <div class="lib-collections">
        <div class="lib-collections-head">
          <span class="lib-collections-title">我的文件夹</span>
          <button
            v-if="!showNewCategory"
            class="lib-collections-add"
            @click="showNewCategory = true"
            title="新建分类"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </button>
        </div>

        <!-- 新建分类输入框 -->
        <div v-if="showNewCategory" class="lib-new-cat">
          <input
            v-model="newCategoryName"
            class="lib-new-cat-input"
            placeholder="分类名称..."
            @keyup.enter="addCategory"
            @keyup.escape="showNewCategory = false; newCategoryName = ''"
            autofocus
          />
          <button class="lib-new-cat-ok" @click="addCategory">确定</button>
          <button class="lib-new-cat-cancel" @click="showNewCategory = false; newCategoryName = ''">取消</button>
        </div>

        <!-- 分类列表 -->
        <div
          v-for="cat in categories"
          :key="cat.id"
          class="lib-collection-item"
          :class="{ active: activeCategory === cat.id }"
          @click="activeCategory = cat.id"
          @mouseenter="hoverCategoryId = cat.id"
          @mouseleave="hoverCategoryId = null"
        >
          <template v-if="editCategoryId === cat.id">
            <input
              v-model="editCategoryName"
              class="lib-cat-edit-input"
              @keyup.enter="confirmEditCategory"
              @keyup.escape="cancelEditCategory"
              @click.stop
              @blur="confirmEditCategory"
              autofocus
            />
          </template>
          <template v-else>
            <svg class="lib-col-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="lib-col-name">{{ cat.name }}</span>
            <div v-if="hoverCategoryId === cat.id" class="lib-col-actions">
              <button class="lib-col-action-btn" @click.stop="startEditCategory(cat)" title="编辑">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="lib-col-action-btn danger" @click.stop="deleteCategory(cat.id)" title="删除">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </button>
            </div>
          </template>
        </div>
      </div>
    </aside>
    </div>

    <!-- 收起/展开按钮 -->
    <button
      class="lib-sidebar-toggle"
      :class="{
        visible: sidebarHovered || sidebarCollapsed,
        collapsed: sidebarCollapsed,
      }"
      @click="toggleSidebar"
      @mouseenter="sidebarHovered = true"
      @mouseleave="sidebarHovered = false"
      :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline v-if="!sidebarCollapsed" points="15 18 9 12 15 6"/>
        <polyline v-else points="9 18 15 12 9 6"/>
      </svg>
    </button>

    <!-- ================================= 右侧主内容 ================================= -->
    <main class="lib-main">
      <!-- Header -->
      <div class="lib-header">
        <h2 class="lib-header-title">{{ categoryLabel }}</h2>
        <span class="lib-header-count">{{ filteredPapers.length }} 篇</span>

        <div class="lib-header-spacer"></div>

        <select v-model="sortBy" class="lib-sort-select">
          <option value="date-desc">最新上传</option>
          <option value="date-asc">最早上传</option>
          <option value="title-asc">标题 A-Z</option>
          <option value="title-desc">标题 Z-A</option>
        </select>

        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="—"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          size="default"
          class="lib-date-picker"
        />
        <button
          v-if="dateRange"
          class="lib-filter-clear"
          @click="dateRange = null"
        >清除</button>

        <div class="lib-search-box">
          <svg class="lib-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            v-model="searchQuery"
            class="lib-search-input"
            placeholder="搜索标题、期刊、DOI..."
          />
          <button
            v-if="searchQuery"
            class="lib-search-clear"
            @click="searchQuery = ''"
          >&times;</button>
        </div>

        <button class="lib-upload-btn" @click="openUpload">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          上传
        </button>
      </div>

      <!-- 文献列表 -->
      <!-- A-Z 首字母筛选 -->
      <div class="lib-alpha-bar">
        <button
          class="lib-alpha-reset"
          :class="{ 'is-spinning': isClearing }"
          @click="clearAllFilters"
          title="刷新"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </button>
        <button
          class="lib-alpha-btn"
          :class="{ active: activeLetter === '' }"
          @click="activeLetter = ''"
        >全部</button>
        <button
          v-for="ch in ALPHABET"
          :key="ch"
          class="lib-alpha-btn"
          :class="{ active: activeLetter === ch }"
          @click="activeLetter = activeLetter === ch ? '' : ch"
        >{{ ch }}</button>
      </div>

      <div class="lib-list-wrap" v-if="filteredPapers.length">

        <!-- 全选栏 -->
        <div class="lib-select-all-bar">
          <label class="lib-select-all" @click.stop>
            <input type="checkbox" :checked="allSelected" @change="toggleSelectAll" />
            <span v-if="!showBatchBar">全选</span>
            <span v-else>已选 {{ selectedPaperIds.size }} 篇</span>
          </label>
        </div>

        <div
          v-for="row in filteredPapers"
          :key="row.id"
          class="lib-list-item"
          :class="{ selected: selectedPaperIds.has(row.id) }"
        >
          <!-- 复选框 -->
          <label class="lib-item-check" @click.stop>
            <input
              type="checkbox"
              :checked="selectedPaperIds.has(row.id)"
              @change="toggleSelectPaper(row.id)"
            />
          </label>

          <!-- 主信息区 -->
          <div class="lib-item-main" @click="openReader(row)">
            <div class="lib-item-title">{{ row.title || row.original_filename }}</div>
            <div class="lib-item-meta">
              <span v-if="row.publication_year" class="lib-meta-year">{{ row.publication_year }}</span>
              <span v-if="row.journal_conf" class="lib-meta-journal">{{ row.journal_conf }}</span>
              <span v-if="parsedAuthors(row).length" class="lib-item-authors">
                <span v-for="(a, ai) in parsedAuthors(row).slice(0, 3)" :key="ai" class="lib-author-chip">{{ a }}</span>
                <span v-if="parsedAuthors(row).length > 3" class="lib-author-more">+{{ parsedAuthors(row).length - 3 }}</span>
              </span>
              <span v-if="row.upload_time" class="lib-item-date">{{ formatDate(row.upload_time) }}</span>
            </div>
          </div>

          <!-- 分类标签 -->
          <span
            v-if="getCategoryName(row)"
            class="lib-item-cat-tag"
            @click.stop
          >{{ getCategoryName(row) }}</span>

          <!-- 状态徽章 -->
          <span class="lib-item-status" :class="row.parse_status">
            <span v-if="row.parse_status === 'completed'" class="status-dot completed"></span>
            <span v-else-if="row.parse_status === 'failed'" class="status-dot failed"></span>
            <span v-else class="status-dot processing pulsing"></span>
            {{ statusLabel(row.parse_status) }}
          </span>

          <!-- 操作按钮 -->
          <div class="lib-item-actions" @click.stop>
            <button class="lib-item-btn" @click="edit(row)" title="编辑">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </button>
            <button class="lib-item-btn" @click="reparse(row.id)" title="重新解析">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
            </button>
            <button class="lib-item-btn danger" @click="remove(row.id)" title="删除">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 批量操作栏 -->
      <transition name="batch-fade">
        <div v-if="showBatchBar" class="lib-batch-bar">
          <span class="lib-batch-info">已选 {{ selectedPaperIds.size }} 篇文献</span>
          <select v-model="batchCategoryId" class="lib-batch-select">
            <option value="">移动到文件夹...</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <button class="lib-batch-btn" @click="batchCategoryId && batchAssignCategory()">移动</button>
          <button class="lib-batch-btn-danger" @click="batchDelete">删除</button>
          <button class="lib-batch-btn-cancel" @click="clearSelection">取消</button>
        </div>
      </transition>

      <!-- 空状态 -->
      <div v-if="!filteredPapers.length && store.list.length" class="lib-empty">
        <h3>没有匹配的文献</h3>
        <p v-if="activeLetter">"{{ activeLetter }}" 开头的文献不存在</p>
        <button class="lib-empty-clear" @click="clearAllFilters">清除所有筛选</button>
      </div>
      <div v-if="!store.list.length" class="lib-empty">
        <h3>暂无文献</h3>
        <p>点击上方「上传文献」添加你的第一篇论文</p>
      </div>
    </main>

    <!-- ========== 编辑弹窗 ========== -->
    <Teleport to="body">
      <transition name="modal-fade">
        <div v-if="editVisible" class="modal-overlay" @click.self="editVisible = false">
          <div class="modal-dialog" @click.stop>
            <div class="modal-header">
              <h3 class="modal-title">编辑文献元数据</h3>
              <button class="modal-close" @click="editVisible = false">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div class="modal-body">
              <label class="modal-field">
                <span class="modal-field-label">标题</span>
                <input v-model="form.title" class="modal-input" />
              </label>
              <label class="modal-field">
                <span class="modal-field-label">DOI</span>
                <input v-model="form.doi" class="modal-input" />
              </label>
              <label class="modal-field">
                <span class="modal-field-label">期刊/会议</span>
                <input v-model="form.journal_conf" class="modal-input" />
              </label>
              <label class="modal-field">
                <span class="modal-field-label">年份</span>
                <input v-model.number="form.publication_year" type="number" class="modal-input" />
              </label>
              <label class="modal-field">
                <span class="modal-field-label">备注</span>
                <textarea v-model="form.notes" class="modal-input" rows="3" />
              </label>
              <label class="modal-field">
                <span class="modal-field-label">分类</span>
                <select v-model="form.category_id" class="modal-input">
                  <option :value="null">无</option>
                  <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
              </label>
            </div>
            <div class="modal-footer">
              <button class="modal-btn-cancel" @click="editVisible = false">取消</button>
              <button class="modal-btn-confirm" :disabled="loading" @click="save">{{ loading ? '保存中...' : '保存' }}</button>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>

    <!-- ========== 上传文献 Modal ========== -->
    <Teleport to="body">
      <transition name="modal-fade">
        <div v-if="uploadVisible" class="modal-overlay" @click.self="closeUpload">
          <div class="modal-dialog upload-dialog" @click.stop>
            <div class="modal-header">
              <h3 class="modal-title">上传文献</h3>
              <button class="modal-close" @click="closeUpload">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>

            <div class="modal-body">
              <!-- 文件选择区 -->
              <label class="upload-dropzone">
                <input
                  type="file"
                  accept=".pdf"
                  multiple
                  hidden
                  @change="handleFilesSelected"
                />
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <span class="upload-dropzone-text">点击选择 PDF 文件</span>
                <span class="upload-dropzone-hint">支持批量上传，解析将在后台自动进行</span>
              </label>

              <!-- 上传列表 -->
              <div v-if="uploadItems.length" class="upload-list">
                <div
                  v-for="item in uploadItems"
                  :key="item.id"
                  class="upload-list-item"
                >
                  <div class="upload-list-name">{{ item.file.name }}</div>
                  <div class="upload-list-bar">
                    <div
                      class="upload-list-fill"
                      :class="item.status"
                      :style="{ width: item.progress + '%' }"
                    ></div>
                  </div>
                  <div class="upload-list-status" :class="item.status">{{ item.message }}</div>
                </div>
              </div>
            </div>

            <div class="modal-footer">
              <button class="modal-btn-confirm" @click="closeUpload">
                完成
              </button>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>

    <!-- ========== 文献阅读器 ========== -->
    <PaperReader
      v-if="currentReaderPaper"
      ref="readerRef"
      :paper-id="currentReaderPaper.id"
      :paper-title="currentReaderPaper.title"
      @close="currentReaderPaper = null"
    />
  </div>
</template>

<style scoped>
/* ========================================
   Workspace Layout
   ======================================== */
.library-workspace {
  position: relative;
  display: flex;
  height: 100%;
  background: #F8FAFC;
}

/* ========================================
   Sidebar Wrapper
   ======================================== */
.lib-sidebar-wrapper {
  position: relative;
  flex-shrink: 0;
  width: 240px;
  overflow: hidden;
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.lib-sidebar-wrapper.collapsed {
  width: 0;
}

/* ========================================
   Sidebar
   ======================================== */
.lib-sidebar {
  width: 240px;
  height: 100%;
  background: #fff;
  box-shadow: 1px 0 0 0 #E2E8F0;
  display: flex;
  flex-direction: column;
  padding: 20px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  gap: 16px;
}

/* ---- 侧边栏收起/展开按钮 ---- */
.lib-sidebar-toggle {
  position: absolute;
  left: 220px;
  top: 18px;
  z-index: 50;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #E2E8F0;
  border-radius: 50%;
  background: #fff;
  color: #64748B;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 0.2s ease, transform 0.2s ease, color 0.15s, left 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}

.lib-sidebar-toggle.visible {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.lib-sidebar-toggle.collapsed {
  left: 12px;
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.lib-sidebar-toggle:hover {
  color: #0F172A;
  border-color: #CBD5E1;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

/* ---- 基础导航 ---- */
.lib-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.lib-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #475569;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  transition: all 0.12s;
  width: 100%;
}

.lib-nav-item:hover {
  background: #F1F5F9;
  color: #334155;
}

.lib-nav-item.active {
  background: #EFF6FF;
  color: #1D4ED8;
  font-weight: 600;
}

.lib-nav-count {
  margin-left: auto;
  font-size: 11px;
  color: #94A3B8;
  font-weight: 500;
  background: #F1F5F9;
  padding: 1px 7px;
  border-radius: 10px;
}

.lib-nav-item.active .lib-nav-count {
  background: #DBEAFE;
  color: #1D4ED8;
}

/* ---- 分隔线 ---- */
.lib-divider {
  height: 1px;
  background: #F1F5F9;
}

/* ---- 我的文件夹 ---- */
.lib-collections-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  margin-bottom: 8px;
}

.lib-collections-title {
  font-size: 11px;
  font-weight: 600;
  color: #94A3B8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.lib-collections-add {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #94A3B8;
  cursor: pointer;
  transition: all 0.12s;
}

.lib-collections-add:hover {
  background: #F1F5F9;
  color: #475569;
}

/* ---- 新建分类输入框 ---- */
.lib-new-cat {
  display: flex;
  gap: 4px;
  padding: 0 12px;
  margin-bottom: 4px;
}

.lib-new-cat-input {
  flex: 1;
  padding: 6px 10px;
  border: none;
  border-radius: 6px;
  background: #F8FAFC;
  font-size: 13px;
  color: #334155;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
  min-width: 0;
}

.lib-new-cat-input:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.lib-new-cat-ok,
.lib-new-cat-cancel {
  padding: 6px 10px;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.lib-new-cat-ok {
  background: #3B82F6;
  color: #fff;
}

.lib-new-cat-cancel {
  background: transparent;
  color: #94A3B8;
}

.lib-new-cat-cancel:hover {
  background: #F1F5F9;
}

/* ---- 分类列表项 ---- */
.lib-collection-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
  position: relative;
}

.lib-collection-item:hover {
  background: #F1F5F9;
}

.lib-collection-item.active {
  background: #EFF6FF;
}

.lib-col-icon {
  flex-shrink: 0;
  color: #94A3B8;
}

.lib-collection-item.active .lib-col-icon {
  color: #3B82F6;
}

.lib-col-name {
  font-size: 13px;
  color: #475569;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lib-collection-item.active .lib-col-name {
  color: #1D4ED8;
  font-weight: 600;
}

.lib-col-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.lib-col-action-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: #94A3B8;
  cursor: pointer;
  transition: all 0.1s;
}

.lib-col-action-btn:hover {
  background: #E2E8F0;
  color: #475569;
}

.lib-col-action-btn.danger:hover {
  background: #FEE2E2;
  color: #EF4444;
}

.lib-cat-edit-input {
  flex: 1;
  padding: 4px 8px;
  border: none;
  border-radius: 6px;
  background: #F8FAFC;
  font-size: 13px;
  color: #334155;
  outline: none;
  box-shadow: 0 0 0 2px #3B82F6;
}

/* ========================================
   Main Content
   ======================================== */
.lib-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  position: relative;
}

/* ---- Header (single-row toolbar) ---- */
.lib-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 24px 14px 24px;
  flex-shrink: 0;
  flex-wrap: nowrap;
}

.lib-header-title {
  font-size: 18px;
  font-weight: 700;
  color: #0F172A;
  margin: 0 0 0 16px;
  white-space: nowrap;
}

.lib-header-count {
  font-size: 13px;
  color: #94A3B8;
  white-space: nowrap;
}

.lib-header-spacer {
  flex: 1;
  min-width: 8px;
}

.lib-sort-select {
  padding: 6px 10px;
  border: none;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
  color: #475569;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
  cursor: pointer;
  white-space: nowrap;
}

.lib-date-picker {
  width: 230px;
}
.lib-date-picker .el-input__wrapper {
  border-radius: 8px !important;
  box-shadow: 0 0 0 1px #E2E8F0 !important;
}
.lib-date-picker .el-input__wrapper:hover {
  box-shadow: 0 0 0 1px #6366F1 !important;
}

.lib-filter-clear {
  padding: 4px 10px;
  border: none;
  border-radius: 6px;
  background: #FEF2F2;
  color: #DC2626;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.lib-filter-clear:hover {
  background: #FEE2E2;
}

/* ---- 搜索框 ---- */
.lib-search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.lib-search-icon {
  position: absolute;
  left: 12px;
  pointer-events: none;
}

.lib-search-input {
  width: 180px;
  padding: 6px 30px 6px 32px;
  border: none;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
  color: #334155;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: box-shadow 0.15s, width 0.2s;
}

.lib-search-input:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
  width: 220px;
}

.lib-search-input::placeholder {
  color: #94A3B8;
}

.lib-search-clear {
  position: absolute;
  right: 6px;
  width: 20px;
  height: 20px;
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

.lib-search-clear:hover {
  background: #CBD5E1;
}

/* ---- 上传按钮 ---- */
.lib-upload-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  background: #3B82F6;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, box-shadow 0.15s;
}

.lib-upload-btn:hover {
  background: #2563EB;
}

/* ---- 文献列表 ---- */
.lib-list-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 0 0px 28px;
  padding-bottom: 80px; /* 为批量操作栏留空 */
}

/* ── A-Z 首字母筛选 ── */
.lib-alpha-bar {
  display: flex;
  align-items: center;
  padding: 0 24px 8px 0;
  background: #fff;
  border-radius: 10px;
  overflow-x: auto;
  margin-bottom: 2px;
}

/* 刷新图标按钮 */
.lib-alpha-reset {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #64748B;
  cursor: pointer;
  margin-left: 10px;
  margin-right: 10px;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}

.lib-alpha-reset:hover {
  background: #F1F5F9;
  color: #0F172A;
}

/* 旋转动效 */
.lib-alpha-reset.is-spinning svg {
  animation: spin 1s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.lib-alpha-btn {
  min-width: 28px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: #64748B;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  padding: 0 4px;
  transition: all 0.12s;
  flex-shrink: 0;
}

.lib-alpha-btn:first-child {
  color: #94A3B8;
  font-weight: 600;
  margin-right: 4px;
}

.lib-alpha-btn:hover {
  background: #F1F5F9;
  color: #334155;
}

.lib-alpha-btn.active {
  background: #3B82F6;
  color: #fff;
  font-weight: 700;
}

/* ---- 全选栏 ---- */
.lib-select-all-bar {
  padding: 10px 16px;
  background: #fff;
  border-radius: 10px 10px 0 0;
  box-shadow: 0 1px 0 0 #F1F5F9;
}

.lib-select-all {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #64748B;
  cursor: pointer;
  user-select: none;
}

.lib-select-all input {
  accent-color: #3B82F6;
  width: 15px;
  height: 15px;
  cursor: pointer;
}

.lib-list-item {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  background: #fff;
  border-radius: 0;
  margin-bottom: 0;
  box-shadow: 0 1px 0 0 #F1F5F9;
  transition: background 0.15s;
  gap: 14px;
  cursor: default;
}

.lib-list-item.selected {
  background: #EFF6FF;
}

.lib-list-item:last-child {
  border-radius: 0 0 10px 10px;
  box-shadow: none;
}

.lib-list-item:hover {
  background: #F1F5F9;
}

.lib-list-item.selected:hover {
  background: #DBEAFE;
}

/* ---- 复选框 ---- */
.lib-item-check {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.lib-item-check input {
  accent-color: #3B82F6;
  width: 15px;
  height: 15px;
  cursor: pointer;
}

/* ---- 主信息区 ---- */
.lib-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.lib-item-title {
  font-size: 14px;
  font-weight: 600;
  color: #0F172A;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lib-item-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #94A3B8;
  flex-wrap: wrap;
}

.lib-meta-year {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 500;
  color: #7C3AED;
  background: #F5F3FF;
  border-radius: 4px;
}

.lib-meta-journal {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  font-size: 11px;
  font-style: italic;
  color: #059669;
  background: #ECFDF5;
  border-radius: 4px;
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lib-item-authors {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
}

.lib-author-chip {
  display: inline-block;
  padding: 1px 8px;
  font-size: 11px;
  color: #3B82F6;
  background: #EFF6FF;
  border-radius: 4px;
  white-space: nowrap;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lib-author-more {
  font-size: 11px;
  color: #94A3B8;
  white-space: nowrap;
}

.lib-item-date {
  font-size: 12px;
  color: #94A3B8;
  white-space: nowrap;
  flex-shrink: 0;
}

/* ---- 分类标签 ---- */
.lib-item-cat-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  background: #FFF7ED;
  color: #C2410C;
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}

/* ---- 状态徽章 ---- */
.lib-item-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.lib-item-status.completed {
  background: rgba(16, 185, 129, 0.08);
  color: #059669;
}

.lib-item-status.failed {
  background: rgba(239, 68, 68, 0.08);
  color: #DC2626;
}

.lib-item-status.queued,
.lib-item-status.parsing,
.lib-item-status.extracting,
.lib-item-status.vectorizing {
  background: rgba(245, 158, 11, 0.08);
  color: #D97706;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.completed {
  background: #10B981;
}

.status-dot.failed {
  background: #EF4444;
}

.status-dot.processing {
  background: #F59E0B;
  animation: pulse-dot 1.6s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.7); }
}

/* ---- 操作按钮 ---- */
.lib-item-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.lib-list-item:hover .lib-item-actions {
  opacity: 1;
}

.lib-item-btn {
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
  transition: all 0.12s;
}

.lib-item-btn:hover {
  background: #E2E8F0;
  color: #475569;
}

.lib-item-btn.danger:hover {
  background: #FEE2E2;
  color: #EF4444;
}

/* ---- 批量操作栏 ---- */
.lib-batch-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: #fff;
  padding: 14px 28px;
  box-shadow: 0 -1px 0 0 #E2E8F0, 0 -4px 12px rgba(0, 0, 0, 0.04);
  display: flex;
  align-items: center;
  gap: 12px;
  z-index: 50;
}

.batch-fade-enter-active,
.batch-fade-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.batch-fade-enter-from,
.batch-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.lib-batch-info {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.lib-batch-select {
  padding: 7px 12px;
  border: none;
  border-radius: 8px;
  background: #F8FAFC;
  font-size: 13px;
  color: #334155;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
  cursor: pointer;
}

.lib-batch-btn {
  padding: 7px 16px;
  background: #3B82F6;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.lib-batch-btn:hover {
  background: #2563EB;
}

.lib-batch-btn-danger {
  padding: 7px 16px;
  background: #fff;
  color: #DC2626;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 0 0 1px #FECACA;
  transition: all 0.15s;
}

.lib-batch-btn-danger:hover {
  background: #FEF2F2;
  box-shadow: 0 0 0 1px #FCA5A5;
}

.lib-batch-btn-cancel {
  padding: 7px 14px;
  background: transparent;
  color: #64748B;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}

.lib-batch-btn-cancel:hover {
  background: #F1F5F9;
}

/* ---- 上传拖拽区 ---- */
.upload-dialog {
  max-width: 520px;
}

.upload-dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 36px 24px;
  border: 2px dashed #E2E8F0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.upload-dropzone:hover {
  border-color: #3B82F6;
  background: #F8FAFC;
}

.upload-dropzone-text {
  font-size: 14px;
  font-weight: 600;
  color: #475569;
}

.upload-dropzone-hint {
  font-size: 12px;
  color: #94A3B8;
}

.upload-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.upload-list-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.upload-list-name {
  font-size: 13px;
  font-weight: 500;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.upload-list-bar {
  height: 4px;
  background: #F1F5F9;
  border-radius: 2px;
  overflow: hidden;
}

.upload-list-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
  background: #3B82F6;
}

.upload-list-fill.done {
  background: #10B981;
}

.upload-list-fill.error {
  background: #EF4444;
}

.upload-list-status {
  font-size: 11px;
  color: #94A3B8;
}

.upload-list-status.done {
  color: #059669;
}

.upload-list-status.error {
  color: #DC2626;
}

/* ---- 空状态 ---- */
.lib-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #94A3B8;
}

.lib-empty h3 {
  font-size: 16px;
  font-weight: 600;
  color: #64748B;
  margin: 0 0 8px;
}

.lib-empty p {
  font-size: 13px;
  margin: 0;
}

.lib-empty-clear {
  margin-top: 12px;
  padding: 6px 16px;
  border: none;
  border-radius: 8px;
  background: #3B82F6;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.3);
  transition: background 0.15s;
}

.lib-empty-clear:hover {
  background: #2563EB;
}

/* ========================================
   Edit Modal (matched to GraphView style)
   ======================================== */
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
.modal-fade-enter-from .modal-dialog,
.modal-fade-leave-to .modal-dialog {
  transform: scale(0.96) translateY(8px);
  opacity: 0;
}

.modal-dialog {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  width: 100%;
  max-width: 520px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.modal-close {
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

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.modal-field-label {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.modal-input {
  width: 100%;
  padding: 10px 14px;
  border: none;
  border-radius: 10px;
  background: #F8FAFC;
  font-size: 14px;
  color: #334155;
  outline: none;
  box-shadow: 0 0 0 1px #E2E8F0;
  transition: box-shadow 0.15s;
  box-sizing: border-box;
  font-family: inherit;
}

.modal-input:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

textarea.modal-input {
  resize: vertical;
}

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
</style>
