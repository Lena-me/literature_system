<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import PaperCard from '@/components/paper/PaperCard.vue'
import DocumentOutline from '@/components/reader/DocumentOutline.vue'
import ChatPanel from '@/components/reader/ChatPanel.vue'
import GraphCanvas from '@/components/reader/GraphCanvas.vue'
import PdfReader from '@/components/reader/PdfReader.vue'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import { usePaperStore } from '@/stores/papers'
import { papersApi } from '@/api/papers'
import { reportsApi } from '@/api/reports'
import { knowledgeApi } from '@/api/knowledge'
import { featuresApi } from '@/api/features'
import type { KnowledgeGraph, Source } from '@/types/domain'

const papers = usePaperStore()
const progress = ref(0)
const uploadMode = ref<'auto' | 'chunk'>('auto')
const uploadText = ref('Single, batch, chunked, and resumable PDF upload')
const keyword = ref('')
const activeTab = ref('outline')
const reportMd = ref('')
const guideMd = ref('')
const graph = ref<KnowledgeGraph | null>(null)
const comparison = ref<any>(null)
const evidence = ref<any>(null)
const evidenceQuestion = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const pdfUrl = ref('')
const pdfError = ref('')
const pdfPage = ref(1)
const pdfHighlight = ref('')
const pdfReader = ref<InstanceType<typeof PdfReader> | null>(null)
const selectedSingle = computed(() => (papers.selectedIds.length === 1 ? papers.selectedIds[0] : null))
const graphCypher = computed(() => {
  const id = graph.value?.id
  if (!id) return ''
  return `MATCH (n:Entity)-[r]->(m:Entity) WHERE r.graph_id = ${id} RETURN n, r, m`
})

function safeRevokeBlobUrl(url: string) {
  if (!url?.startsWith('blob:')) return
  try {
    URL.revokeObjectURL(url)
  } catch {
    // 如果已被回收则忽略
  }
}

function onOldUrlCleanup(url: string) {
  safeRevokeBlobUrl(url)
}

onMounted(async () => {
  await papers.load()
})

async function loadPdfForPaper(id?: number | null) {
  // 不再立即释放 blob URL——PdfReader 内部会先销毁旧的 LoadingTask，
  // 确保 PDF.js 不再引用旧 URL 后，通过 @old-url-cleanup 事件通知释放。
  pdfUrl.value = ''
  pdfError.value = ''
  pdfHighlight.value = ''

  if (!id) return

  try {
    pdfUrl.value = await papersApi.fileBlobUrl(id)
  } catch (error: any) {
    pdfUrl.value = ''
    const status = error?.response?.status
    const detail = error?.response?.data?.detail || error?.message
    pdfError.value = status
      ? `PDF loading failed: ${status}${detail ? ` - ${detail}` : ''}`
      : `PDF loading failed${detail ? `: ${detail}` : ''}`
    console.error('PDF loading failed:', error)
    ElMessage.error(pdfError.value)
  }
}

watch(
  () => papers.current?.id,
  async id => {
    await loadPdfForPaper(id)
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  safeRevokeBlobUrl(pdfUrl.value)
})

async function openPaper(paper: any) {
  await papers.open(paper)
  await loadPdfForPaper(paper.id)
  activeTab.value = 'pdf'
}

async function refreshCurrent() {
  if (!papers.current) return
  await papers.open(papers.current)
  await loadPdfForPaper(papers.current.id)
}

async function handleNativeFiles(evt: Event) {
  const input = evt.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return

  progress.value = 0
  uploadText.value =
    files.length > 1
      ? `Uploading ${files.length} PDFs`
      : uploadMode.value === 'chunk' || files[0].size >= 8 * 1024 * 1024
        ? 'Chunked upload in progress'
        : 'Uploading PDF'
  try {
    if (uploadMode.value === 'chunk' && files.length === 1) {
      await papers.chunkUpload(files[0], n => (progress.value = n))
    } else {
      await papers.smartUpload(files, n => (progress.value = n))
    }
    ElMessage.success('Upload completed. Parsing task has been queued.')
  } finally {
    uploadText.value = 'Single, batch, chunked, and resumable PDF upload'
  }
}

async function search() {
  await papers.load({ keyword: keyword.value })
}

async function createReport() {
  if (!selectedSingle.value) return
  const r = await reportsApi.create({ paper_id: selectedSingle.value })
  reportMd.value = r.content?.markdown || JSON.stringify(r.content, null, 2)
  activeTab.value = 'report'
}

async function createGraph() {
  if (!papers.selectedIds.length) return
  activeTab.value = 'graph'
  graph.value = null
  await nextTick()
  graph.value = await knowledgeApi.create({ paper_ids: papers.selectedIds })
  await nextTick()
}

async function createCompare() {
  if (papers.selectedIds.length < 2) return
  comparison.value = await featuresApi.compare({ paper_ids: papers.selectedIds })
  activeTab.value = 'compare'
}

async function createGuide() {
  if (!selectedSingle.value) return
  const r: any = await featuresApi.guide(selectedSingle.value)
  guideMd.value = r.guide_content?.markdown || JSON.stringify(r.guide_content, null, 2)
  activeTab.value = 'guide'
}

async function createEvidence() {
  if (!papers.selectedIds.length) return
  activeTab.value = 'evidence'
  evidence.value = await featuresApi.evidenceMatrix({
    paper_ids: papers.selectedIds,
    question: evidenceQuestion.value || undefined,
  })
}

async function onSourceClick(source: Source) {
  const target = papers.list.find(p => p.id === source.paper_id)
  if (target) {
    await openPaper(target)
  }
  activeTab.value = 'pdf'
  pdfPage.value = source.page_number || 1
  pdfHighlight.value = source.snippet || source.text || ''
  await nextTick()
  await pdfReader.value?.jumpTo(pdfPage.value, pdfHighlight.value)
}
</script>

<template>
  <div class="workbench fade-slide">
    <section class="left glass">
      <div class="panel-title">
        <b>Paper Library</b>
        <el-button text @click="papers.load()"><Refresh /></el-button>
      </div>

      <el-input v-model="keyword" placeholder="Search title, author, keyword" @keyup.enter="search">
        <template #suffix><Search @click="search" /></template>
      </el-input>

      <div class="upload-card" @click="fileInput?.click()">
        <input ref="fileInput" type="file" accept="application/pdf,.pdf" multiple hidden @change="handleNativeFiles" />
        <el-icon><UploadFilled /></el-icon>
        <div>
          <b>Upload Research PDFs</b>
          <small>{{ uploadText }}</small>
        </div>
        <el-segmented
          v-model="uploadMode"
          :options="[
            { label: 'Auto', value: 'auto' },
            { label: 'Chunked', value: 'chunk' },
          ]"
          @click.stop
        />
      </div>

      <el-progress v-if="progress" :percentage="progress" />
      <div class="paper-list slim-scroll">
        <PaperCard
          v-for="p in papers.list"
          :key="p.id"
          :paper="p"
          :selected="papers.selectedIds.includes(p.id)"
          @toggle="papers.toggleSelect"
          @open="openPaper"
        />
      </div>
    </section>

    <section class="center glass">
      <div class="read-head">
        <div>
          <b>{{ papers.current?.title || 'Structured Paper Preview' }}</b>
          <span>{{ papers.current?.original_filename || 'Select a paper from the left to view parsed content.' }}</span>
        </div>
        <div class="actions">
          <el-button @click="createEvidence" :disabled="!papers.selectedIds.length">Evidence Matrix</el-button>
          <el-button @click="refreshCurrent" :disabled="!papers.current">Refresh Content</el-button>
        </div>
      </div>

      <el-tabs v-model="activeTab" class="tabs">
        <el-tab-pane label="PDF" name="pdf">
          <el-alert v-if="pdfError" :title="pdfError" type="error" show-icon :closable="false" class="pdf-error" />
          <PdfReader ref="pdfReader" :url="pdfUrl" :initial-page="pdfPage" :highlight-text="pdfHighlight" @old-url-cleanup="onOldUrlCleanup" />
        </el-tab-pane>

        <el-tab-pane label="Outline" name="outline">
          <DocumentOutline :items="papers.content" />
        </el-tab-pane>

        <el-tab-pane label="Report" name="report">
          <MarkdownRenderer :content="reportMd || 'Generate a reading report from the right panel.'" />
        </el-tab-pane>

        <el-tab-pane label="Knowledge Graph" name="graph">
          <GraphCanvas
            :cypher-query="graphCypher"
            :graph-id="graph?.id ?? null"
          />
        </el-tab-pane>

        <el-tab-pane label="Compare" name="compare">
          <pre>{{ comparison || 'Select 2-5 papers to generate a comparison.' }}</pre>
        </el-tab-pane>

        <el-tab-pane label="Reproduce" name="guide">
          <MarkdownRenderer :content="guideMd || 'Select one paper to generate a reproducibility guide.'" />
        </el-tab-pane>

        <el-tab-pane label="Evidence Matrix" name="evidence">
          <div class="evidence-box">
            <div class="evidence-toolbar">
              <el-input
                v-model="evidenceQuestion"
                placeholder="Research question, e.g. how does this paper validate the method?"
                clearable
                @keyup.enter="createEvidence"
              />
              <el-button type="primary" @click="createEvidence" :disabled="!papers.selectedIds.length">
                Generate
              </el-button>
            </div>

            <div v-if="!evidence" class="empty-evidence">
              Select one or more papers, enter a research question, then generate the evidence matrix.
            </div>

            <div v-else class="evidence-table">
              <div class="evidence-question">
                <b>Question:</b> {{ evidence.question || 'No question specified. Showing representative paper snippets.' }}
              </div>

              <div v-for="row in evidence.rows" :key="row.paper_id" class="evidence-row">
                <h4>{{ row.title }}</h4>

                <div v-if="!row.evidences || row.evidences.length === 0" class="evidence-empty">
                  No evidence snippets available.
                </div>

                <div
                  v-for="ev in row.evidences"
                  :key="`${ev.paper_id}-${ev.page_number}-${ev.snippet.slice(0, 20)}`"
                  class="evidence-card"
                  @click="onSourceClick(ev.source)"
                >
                  <div class="evidence-meta">
                    <span>Page: {{ ev.page_number || 'unknown' }}</span>
                    <span>Section: {{ ev.section_title || 'unknown' }}</span>
                    <span>Support: {{ ev.support }}</span>
                    <span v-if="ev.score !== null && ev.score !== undefined">Similarity: {{ ev.score }}</span>
                  </div>
                  <p>{{ ev.snippet }}</p>
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </section>

    <ChatPanel
      class="right"
      :selected-ids="papers.selectedIds"
      @report="createReport"
      @graph="createGraph"
      @compare="createCompare"
      @guide="createGuide"
      @source-click="onSourceClick"
    />
  </div>
</template>

<style scoped>
.workbench{display:grid;grid-template-columns:330px minmax(360px,1fr) 440px;gap:18px;height:calc(100vh - 40px)}
.left,.center{border-radius:28px;padding:18px;min-height:0;display:flex;flex-direction:column}
.panel-title,.read-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:12px}
.read-head b,.panel-title b{font-size:18px}
.read-head span{display:block;color:var(--muted);font-size:12px;margin-top:4px}
.actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.upload-card{margin:14px 0;padding:18px;border:1px dashed rgba(102,231,255,.38);border-radius:22px;background:linear-gradient(135deg,rgba(102,231,255,.1),rgba(138,124,255,.08));display:grid;grid-template-columns:42px 1fr;gap:12px;align-items:center;cursor:pointer}
.upload-card .el-icon{font-size:34px;color:var(--brand);filter:drop-shadow(0 0 14px rgba(102,231,255,.55))}
.upload-card b{display:block}
.upload-card small{display:block;color:var(--muted);margin-top:4px}
.upload-card .el-segmented{grid-column:1/3}
.paper-list{display:flex;flex-direction:column;gap:10px;overflow:auto;padding-right:4px}
.tabs{min-height:0;flex:1;display:flex;flex-direction:column}
.tabs :deep(.el-tabs__content){flex:1;min-height:0;overflow:auto}
.tabs :deep(.el-tab-pane){height:100%;overflow:auto}
.right{min-height:0}
pre{white-space:pre-wrap;color:#ddecff;background:rgba(0,0,0,.25);border-radius:14px;padding:14px;min-height:320px}
.pdf-error{margin-bottom:12px}
.evidence-box{padding:12px}
.evidence-toolbar{display:grid;grid-template-columns:1fr auto;gap:10px;margin-bottom:14px}
.empty-evidence,.evidence-empty{color:var(--muted);padding:18px;border-radius:14px;background:rgba(255,255,255,.05)}
.evidence-question{margin-bottom:12px;color:#ddecff}
.evidence-row{margin-bottom:16px}
.evidence-row h4{margin:8px 0;color:#eef6ff}
.evidence-card{padding:12px;margin:8px 0;border-radius:14px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);cursor:pointer}
.evidence-card:hover{border-color:rgba(102,231,255,.45);background:rgba(102,231,255,.08)}
.evidence-meta{display:flex;gap:12px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-bottom:8px}
.evidence-card p{margin:0;color:#ddecff;line-height:1.65}
@media(max-width:1300px){.workbench{grid-template-columns:300px 1fr}.right{grid-column:1/3;height:560px}}
@media(max-width:900px){.workbench{grid-template-columns:1fr;height:auto}.right{grid-column:auto;height:560px}.evidence-toolbar{grid-template-columns:1fr}}
</style>
