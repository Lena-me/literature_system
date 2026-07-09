<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { notesApi } from '@/api/notes'
import type { PaperNote } from '@/types/domain'
import { katexRenderedCleanly, renderKatexHtml } from '@/utils/mathRender'

const props = defineProps<{
  paperId: number
  notes: PaperNote[]
  loading?: boolean
}>()

const emit = defineEmits<{
  select: [note: PaperNote]
  refresh: []
}>()

const editingId = ref<number | null>(null)
const editingContent = ref('')
const savingId = ref<number | null>(null)
const flashNoteId = ref<number | null>(null)
let flashTimer: ReturnType<typeof setTimeout> | null = null

const groupedNotes = computed(() => {
  const map = new Map<number, PaperNote[]>()
  for (const note of props.notes) {
    const page = note.page_number || 1
    if (!map.has(page)) map.set(page, [])
    map.get(page)!.push(note)
  }
  return [...map.entries()].sort((a, b) => a[0] - b[0])
})

function previewText(note: PaperNote) {
  if (note.selected_text === '[公式]' && note.note_content?.includes('$')) {
    return '公式笔记'
  }
  return note.note_content?.trim() || note.selected_text.trim()
}

function renderNoteContentHtml(content: string, note?: PaperNote): string {
  const trimmed = content.trim()
  const katexSource = note?.selected_text === '[公式]' ? 'ocr' : 'default'
  if (trimmed.startsWith('$$') && trimmed.endsWith('$$')) {
    const inner = trimmed.replace(/^\$\$\n?|\n?\$\$$/g, '').trim()
    const html = renderKatexHtml(inner, true, { source: katexSource })
    if (katexRenderedCleanly(html)) {
      return `<div class="formula-display">${html}</div>`
    }
    return `<pre class="formula-fallback">${inner}</pre>`
  }
  if (trimmed.startsWith('$') && trimmed.endsWith('$') && !trimmed.startsWith('$$')) {
    const inner = trimmed.slice(1, -1).trim()
    const html = renderKatexHtml(inner, false, { source: katexSource })
    if (katexRenderedCleanly(html)) {
      return `<span class="math-inline">${html}</span>`
    }
    return `<pre class="formula-fallback">${inner}</pre>`
  }
  return ''
}

function hasFormulaContent(note: PaperNote) {
  return !!renderNoteContentHtml(note.note_content || '', note)
}

function startEdit(note: PaperNote) {
  editingId.value = note.id
  editingContent.value = note.note_content || ''
}

function cancelEdit() {
  editingId.value = null
  editingContent.value = ''
}

async function saveEdit(note: PaperNote) {
  savingId.value = note.id
  try {
    await notesApi.update(note.id, {
      note_content: editingContent.value.trim() || null,
    })
    cancelEdit()
    emit('refresh')
    ElMessage.success('笔记已保存')
  } catch {
    /* http interceptor handles error */
  } finally {
    savingId.value = null
  }
}

async function removeNote(note: PaperNote) {
  try {
    await notesApi.delete(note.id)
    if (editingId.value === note.id) cancelEdit()
    emit('refresh')
    ElMessage.success('笔记已删除')
  } catch {
    /* ignore */
  }
}

function flashNote(noteId: number) {
  flashNoteId.value = noteId
  if (flashTimer) clearTimeout(flashTimer)
  flashTimer = setTimeout(() => {
    flashNoteId.value = null
    flashTimer = null
  }, 1500)
}

function scrollToNote(noteId: number) {
  const el = document.getElementById(`note-card-${noteId}`)
  if (!el) return false
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  flashNote(noteId)
  return true
}

defineExpose({ scrollToNote, flashNote })
</script>

<template>
  <div class="notes-panel">
    <div v-if="loading" class="notes-empty">加载笔记中...</div>
    <div v-else-if="!notes.length" class="notes-empty">
      <p>暂无笔记</p>
      <span>在左侧 PDF 中划选文字，即可添加高亮与批注。</span>
    </div>

    <div v-else class="notes-list slim-scroll">
      <section v-for="[page, items] in groupedNotes" :key="page" class="notes-page-group">
        <header class="notes-page-head">第 {{ page }} 页 · {{ items.length }} 条</header>
        <article
          v-for="note in items"
          :id="`note-card-${note.id}`"
          :key="note.id"
          class="note-card"
          :class="{ 'note-card--flash': flashNoteId === note.id }"
          @click="emit('select', note)"
        >
          <div class="note-color" :style="{ backgroundColor: note.highlight_color }" />
          <div class="note-body">
            <p class="note-quote">{{ note.selected_text }}</p>

            <div v-if="editingId === note.id" class="note-editor" @click.stop>
              <el-input
                v-model="editingContent"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
                placeholder="添加批注..."
              />
              <div class="note-editor-actions">
                <el-button size="small" @click="cancelEdit">取消</el-button>
                <el-button
                  size="small"
                  type="primary"
                  :loading="savingId === note.id"
                  @click="saveEdit(note)"
                >
                  保存
                </el-button>
              </div>
            </div>
            <div
              v-else-if="note.note_content && hasFormulaContent(note)"
              class="note-content note-content--formula"
              v-html="renderNoteContentHtml(note.note_content, note)"
            />
            <p v-else-if="note.note_content" class="note-content">{{ note.note_content }}</p>

            <div class="note-actions" @click.stop>
              <button type="button" @click="startEdit(note)">编辑</button>
              <button type="button" class="danger" @click="removeNote(note)">删除</button>
            </div>
          </div>
        </article>
      </section>
    </div>
  </div>
</template>

<style scoped>
.notes-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.notes-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 24px;
  text-align: center;
  color: #94A3B8;
}

.notes-empty p {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #64748B;
}

.notes-empty span {
  font-size: 13px;
  line-height: 1.6;
  max-width: 280px;
}

.notes-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px 24px;
}

.notes-page-group + .notes-page-group {
  margin-top: 18px;
}

.notes-page-head {
  font-size: 12px;
  font-weight: 700;
  color: #64748B;
  margin-bottom: 10px;
  letter-spacing: 0.02em;
}

.note-card {
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.note-card + .note-card {
  margin-top: 10px;
}

.note-card:hover {
  border-color: #93C5FD;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.08);
}

.note-card--flash {
  border-color: #3B82F6;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.22);
  animation: noteFlash 1.2s ease-in-out 1;
}

@keyframes noteFlash {
  0%, 100% { background: #fff; }
  35% { background: rgba(219, 234, 254, 0.85); }
}

.note-color {
  width: 4px;
  border-radius: 999px;
  flex-shrink: 0;
  opacity: 0.85;
}

.note-body {
  flex: 1;
  min-width: 0;
}

.note-quote {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.note-content {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
}

.note-content--formula {
  white-space: normal;
  overflow-x: auto;
}

.note-content--formula :deep(.formula-display) {
  margin: 0;
  text-align: left;
}

.note-content--formula :deep(.katex-display) {
  margin: 0;
}

.note-content--formula :deep(.formula-fallback) {
  margin: 0;
  padding: 8px 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  background: var(--bg-canvas);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
}

.note-editor {
  margin-top: 8px;
}

.note-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.note-actions {
  display: flex;
  gap: 12px;
}

.note-actions button {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 12px;
  color: #64748B;
  cursor: pointer;
}

.note-actions button:hover {
  color: #2563EB;
}

.note-actions button.danger:hover {
  color: #DC2626;
}
</style>
