<script setup lang="ts">
import { useRouter } from 'vue-router'
import MultiPaperComparePanel from '@/components/notebook/MultiPaperComparePanel.vue'
import { useNotebookStore } from '@/stores/notebook'
import type { Source } from '@/types/domain'
import { extractHighlightText } from '@/utils/sourceNavigation'

const router = useRouter()
const notebook = useNotebookStore()

async function onSourceClick(source: Source) {
  if (!notebook.activeSessionId) {
    await notebook.createSession()
  }
  const sessionId = notebook.activeSessionId
  if (sessionId && !router.currentRoute.value.path.startsWith('/notebook')) {
    await router.push(`/notebook/session/${sessionId}`)
  }
  notebook.openReadingDrawer(
    source.paper_id,
    source.page_number ?? undefined,
    extractHighlightText(source),
  )
}
</script>

<template>
  <MultiPaperComparePanel @source-click="onSourceClick" />
</template>
