<script setup lang="ts">
import { computed } from 'vue'
import type { GraphListItem } from '@/api/knowledge'
import type { KnowledgeDomain } from '@/types/domain'

type LeftTab = 'all' | 'recent' | 'topic'

const props = defineProps<{
  libraryStats: { graphCount: number; topicCount: number; paperCount: number }
  graphSearch: string
  leftTab: LeftTab
  activeTopicId: number | null
  topics: KnowledgeDomain[]
  filteredGraphs: GraphListItem[]
  currentGraphId: number | null
  formatDate: (value?: string | null) => string
}>()

const emit = defineEmits<{
  (e: 'update:graphSearch', value: string): void
  (e: 'update:leftTab', value: LeftTab): void
  (e: 'update:activeTopicId', value: number | null): void
  (e: 'refresh'): void
  (e: 'openCreate'): void
  (e: 'openGraph', id: number): void
  (e: 'deleteGraph', item: GraphListItem): void
}>()

const graphSearchModel = computed({
  get: () => props.graphSearch,
  set: value => emit('update:graphSearch', value),
})

function setLeftTab(tab: LeftTab) {
  emit('update:leftTab', tab)
}

function setActiveTopic(id: number | null) {
  emit('update:activeTopicId', id)
}
</script>

<template>
  <aside class="graph-sidebar">
    <div class="sidebar-heading">
      <h2>我的图谱</h2>
      <button class="icon-btn" title="刷新列表" @click="emit('refresh')">
        <span>↻</span>
      </button>
    </div>

    <button class="create-btn sidebar-create" @click="emit('openCreate')">
      <span>＋</span> 新建图谱
    </button>

    <div class="search-box">
      <span class="search-icon">⌕</span>
      <input v-model="graphSearchModel" placeholder="搜索图谱名称或主题…" />
    </div>

    <div class="tabs">
      <button :class="{ active: leftTab === 'all' }" @click="setLeftTab('all')">全部</button>
      <button :class="{ active: leftTab === 'recent' }" @click="setLeftTab('recent')">最近</button>
      <button :class="{ active: leftTab === 'topic' }" @click="setLeftTab('topic')">主题</button>
    </div>

    <div v-if="leftTab === 'topic'" class="topic-list">
      <button
        class="topic-pill"
        :class="{ active: activeTopicId === null }"
        @click="setActiveTopic(null)"
      >全部主题</button>
      <button
        v-for="topic in topics"
        :key="topic.id"
        class="topic-pill"
        :class="{ active: activeTopicId === topic.id }"
        @click="setActiveTopic(topic.id)"
      >{{ topic.name }}</button>
    </div>

    <div class="graph-list slim-scroll">
      <button
        v-for="item in filteredGraphs"
        :key="item.id"
        class="graph-card"
        :class="{ active: currentGraphId === item.id }"
        @click="emit('openGraph', item.id)"
      >
        <div class="row-title-line">
          <strong>{{ item.name }}</strong>
          <span class="row-date">{{ formatDate(item.created_at) }}</span>
        </div>
        <div class="row-subline">
          <span class="status-dot"></span>
          <span>{{ item.status === 'failed' ? '未完成' : '已生成' }}</span>
          <span class="dot-separator">·</span>
          <span>{{ item.domain_name || '未分类' }}</span>
        </div>
        <div class="row-meta-line">
          <span>{{ item.paper_count || 0 }} 篇 · {{ item.relation_count ?? item.edge_count ?? 0 }} 组关联</span>
          <span class="card-action" @click.stop="emit('deleteGraph', item)">删除</span>
        </div>
      </button>

      <div v-if="!filteredGraphs.length" class="empty-small">
        <strong>还没有图谱</strong>
        <span>选择多篇文献后，可生成研究关联图谱。</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.graph-sidebar {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px 12px;
  background: #fff;
  box-shadow: 1px 0 0 0 #e2e8f0;
  overflow-y: auto;
  overflow-x: hidden;
  gap: 12px;
}

.sidebar-heading,
.card-topline,
.card-meta,
.card-footer,
.row-title-line,
.row-subline,
.row-meta-line {
  display: flex;
  align-items: center;
}

.sidebar-heading,
.card-footer,
.row-title-line,
.row-meta-line {
  justify-content: space-between;
}

.sidebar-heading h2 {
  margin: 0;
  color: #0f1f3d;
  font-size: 21px;
  line-height: 1.16;
  font-weight: 850;
  letter-spacing: -0.04em;
}

.sidebar-create {
  margin: 18px 0 14px;
}

.icon-btn,
.create-btn,
.tabs button,
.topic-pill,
.graph-card {
  border: none;
  cursor: pointer;
  font-family: inherit;
}

.icon-btn {
  width: 38px;
  height: 38px;
  padding: 0;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  color: #344960;
  border: 1px solid #dbe6f0;
  font-size: 18px;
}

.create-btn {
  width: 100%;
  height: 42px;
  border-radius: 13px;
  background: #2563eb;
  color: #fff;
  font-weight: 850;
  box-shadow: none;
}

.create-btn:hover {
  background: #1d4ed8;
}

.search-box {
  position: relative;
  margin: 0 0 14px;
}

.search-icon {
  position: absolute;
  left: 13px;
  top: 50%;
  transform: translateY(-50%);
  color: #8ea0b5;
  font-size: 16px;
}

.search-box input {
  width: 100%;
  height: 40px;
  padding: 0 12px 0 38px;
  border: 1px solid #dbe6f0;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 13px;
  color: #1e293b;
  outline: none;
  transition: border 0.16s, box-shadow 0.16s, background 0.16s;
}

.search-box input:focus {
  border-color: rgba(20, 184, 166, 0.68);
  box-shadow: 0 0 0 4px rgba(20, 184, 166, 0.12);
}

.tabs {
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 0 4px 8px;
  margin-bottom: 10px;
  background: transparent;
  border-radius: 0;
  border-bottom: 1px solid #eaf1f6;
}

.tabs button {
  height: auto;
  padding: 0 1px 8px;
  border-radius: 0;
  background: transparent;
  color: #7d8ea3;
  font-weight: 800;
  border-bottom: 2px solid transparent;
}

.tabs button.active {
  color: #2563eb;
  box-shadow: none;
  border-bottom-color: #2563eb;
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
  padding: 2px 0 0;
}

.graph-card {
  position: relative;
  width: 100%;
  padding: 12px 10px;
  text-align: left;
  border-radius: 0;
  background: transparent;
  color: #1e293b;
  border: none;
  border-bottom: 1px solid #e8eef5;
  box-shadow: none;
  transition: background 0.16s, color 0.16s;
}

.graph-card:hover {
  background: rgba(241, 245, 249, 0.72);
}

.graph-card.active {
  background: #f3f6f8;
}

.graph-card.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 14px;
  bottom: 14px;
  width: 3px;
  border-radius: 999px;
  background: #2563eb;
}

.graph-card:focus,
.graph-card:focus-visible {
  outline: none;
}

.graph-card:focus-visible {
  box-shadow: inset 0 0 0 2px rgba(37, 99, 235, 0.18);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 99px;
  background: #10b981;
  box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.10);
  flex: 0 0 auto;
}

.row-title-line {
  gap: 8px;
}

.graph-card strong {
  min-width: 0;
  margin: 0;
  color: #17233a;
  font-size: 13.5px;
  line-height: 1.38;
  font-weight: 850;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.graph-card.active strong {
  color: #075985;
}

.row-date {
  flex: 0 0 auto;
  color: #7b8aa0;
  font-size: 12px;
}

.row-subline {
  gap: 7px;
  margin-top: 7px;
  color: #6f8094;
  font-size: 12px;
  line-height: 1.35;
}

.dot-separator {
  color: #b5c1cf;
}

.row-meta-line {
  gap: 10px;
  margin-top: 6px;
  color: #708196;
  font-size: 12px;
  line-height: 1.35;
}

.card-action {
  color: #ef4444;
  opacity: 0;
  transition: opacity 0.16s;
}

.graph-card:hover .card-action,
.graph-card.active .card-action {
  opacity: 0.72;
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

.slim-scroll::-webkit-scrollbar {
  width: 6px;
}

.slim-scroll::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 999px;
}

</style>
