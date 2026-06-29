<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { papersApi } from '@/api/papers'
import { usePaperStore } from '@/stores/papers'

const store = usePaperStore()
const editVisible = ref(false)
const form = ref<any>({})
const loading = ref(false)

onMounted(() => store.load())

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
</script>

<template>
  <div class="library-page slim-scroll">
    <div class="page-head">
      <div>
        <h2>文献库</h2>
        <p>管理已上传的所有学术文献</p>
      </div>
      <div class="head-actions">
        <span class="count">共 {{ store.list.length }} 篇</span>
        <button class="refresh-btn" @click="() => store.load()">刷新</button>
      </div>
    </div>

    <div class="table-wrap">
      <table class="lib-table">
        <thead>
          <tr>
            <th class="col-id">ID</th>
            <th class="col-title">论文标题</th>
            <th class="col-status">解析状态</th>
            <th class="col-journal">期刊/会议</th>
            <th class="col-year">年份</th>
            <th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in store.list" :key="row.id">
            <td class="col-id">{{ row.id }}</td>
            <td class="col-title">
              <div class="title-main">{{ row.title || row.original_filename }}</div>
              <div class="title-sub">{{ row.original_filename }}</div>
            </td>
            <td class="col-status">
              <span class="status-badge" :class="row.parse_status">{{ row.parse_status }}</span>
            </td>
            <td class="col-journal">{{ row.journal_conf || '-' }}</td>
            <td class="col-year">{{ row.publication_year || '-' }}</td>
            <td class="col-actions">
              <button class="act-btn" @click="edit(row)">编辑</button>
              <button class="act-btn" @click="papersApi.reparse(row.id)">重解析</button>
              <button class="act-btn danger" @click="remove(row.id)">删除</button>
            </td>
          </tr>
          <tr v-if="store.list.length === 0">
            <td colspan="6" class="empty-row">暂无文献，请先上传</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 编辑弹窗 -->
    <Teleport to="body">
      <div v-if="editVisible" class="modal-overlay" @click.self="editVisible = false">
        <div class="modal-dialog">
          <div class="modal-head">
            <b>编辑文献元数据</b>
            <button class="modal-close" @click="editVisible = false">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="modal-body">
            <label class="field">
              <span>标题</span>
              <input v-model="form.title" class="text-input" />
            </label>
            <label class="field">
              <span>DOI</span>
              <input v-model="form.doi" class="text-input" />
            </label>
            <label class="field">
              <span>期刊/会议</span>
              <input v-model="form.journal_conf" class="text-input" />
            </label>
            <label class="field">
              <span>年份</span>
              <input v-model.number="form.publication_year" type="number" class="text-input" />
            </label>
            <label class="field">
              <span>备注</span>
              <textarea v-model="form.notes" class="text-input" rows="3" />
            </label>
          </div>
          <div class="modal-foot">
            <button class="cancel-btn" @click="editVisible = false">取消</button>
            <button class="save-btn" :disabled="loading" @click="save">{{ loading ? '保存中...' : '保存' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.library-page {
  height: 100%;
  overflow-y: auto;
  padding: 12px 24px;
  background: var(--academic-canvas);
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-head h2 {
  margin: 0;
  font-size: 24px;
  color: var(--academic-text-main);
}

.page-head p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--academic-text-muted);
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.count {
  font-size: 13px;
  color: var(--academic-text-muted);
}

.refresh-btn {
  padding: 8px 18px;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.refresh-btn:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border-color: var(--academic-primary);
}

/* ====== 表格 ====== */
.table-wrap {
  border-radius: 18px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  overflow: hidden;
  box-shadow: var(--shadow-soft);
}

.lib-table {
  width: 100%;
  border-collapse: collapse;
}

.lib-table th {
  padding: 14px 16px;
  font-size: 11px;
  font-weight: 600;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  text-align: left;
  background: var(--academic-canvas);
  border-bottom: 1px solid var(--academic-border);
}

.lib-table td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--academic-border);
  font-size: 13px;
  color: var(--academic-text-body);
}

.lib-table tr:last-child td {
  border-bottom: none;
}

.lib-table tbody tr:hover {
  background: rgba(0, 0, 0, 0.015);
}

.col-id { width: 60px; }
.col-status { width: 110px; }
.col-journal { width: 180px; }
.col-year { width: 80px; }
.col-actions { width: 200px; }

.title-main {
  font-weight: 600;
  color: var(--academic-text-main);
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-sub {
  font-size: 11px;
  color: var(--academic-text-muted);
  margin-top: 2px;
}

.status-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.status-badge.completed {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.status-badge.queued,
.status-badge.parsing,
.status-badge.extracting,
.status-badge.vectorizing {
  background: rgba(245, 158, 11, 0.1);
  color: #D97706;
}

.status-badge.failed {
  background: rgba(239, 68, 68, 0.1);
  color: #DC2626;
}

.act-btn {
  padding: 5px 14px;
  border-radius: 8px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  margin-right: 6px;
}

.act-btn:hover {
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border-color: var(--academic-primary);
}

.act-btn.danger:hover {
  background: rgba(239, 68, 68, 0.08);
  color: var(--danger);
  border-color: var(--danger);
}

.empty-row {
  text-align: center;
  padding: 40px !important;
  color: var(--academic-text-muted);
}

/* ====== 编辑弹窗 ====== */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.3);
  display: grid;
  place-items: center;
  z-index: 200;
  backdrop-filter: blur(4px);
}

.modal-dialog {
  width: 520px;
  max-height: 80vh;
  overflow-y: auto;
  border-radius: 22px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  box-shadow: var(--shadow-float);
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 22px;
  border-bottom: 1px solid var(--academic-border);
}

.modal-head b {
  font-size: 16px;
  color: var(--academic-text-main);
}

.modal-close {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: all 0.15s;
}

.modal-close:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--academic-text-main);
}

.modal-body {
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field span {
  font-size: 13px;
  font-weight: 600;
  color: var(--academic-text-body);
}

.text-input {
  width: 100%;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-canvas);
  color: var(--academic-text-body);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
  font-family: inherit;
}

.text-input:focus {
  border-color: var(--academic-primary);
  background: var(--academic-panel);
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 22px 20px;
  border-top: 1px solid var(--academic-border);
}

.cancel-btn {
  padding: 10px 20px;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.cancel-btn:hover {
  background: var(--academic-canvas);
}

.save-btn {
  padding: 10px 22px;
  border-radius: 12px;
  border: none;
  background: var(--academic-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.save-btn:hover:not(:disabled) {
  background: var(--academic-primary-hover);
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
