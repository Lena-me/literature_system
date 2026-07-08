<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import MultiPaperComparePanel from '@/components/notebook/MultiPaperComparePanel.vue'
import PaperReader from '@/components/reader/PaperReader.vue'
import { usePaperStore } from '@/stores/papers'
import type { Source } from '@/types/domain'
import { extractHighlightText } from '@/utils/sourceNavigation'

const paperStore = usePaperStore()
const readerRef = ref<InstanceType<typeof PaperReader> | null>(null)
const readerPaper = ref<{ id: number; title: string } | null>(null)

onMounted(async () => {
  if (!paperStore.list.length) {
    try {
      await paperStore.load()
    } catch {
      // ignore
    }
  }
})

async function onSourceClick(source: Source) {
  const paper = paperStore.list.find(p => p.id === source.paper_id)
  readerPaper.value = {
    id: source.paper_id,
    title: paper?.title || paper?.original_filename || source.paper_title || `文献 #${source.paper_id}`,
  }
  await nextTick()
  await readerRef.value?.open({
    page: source.page_number || 1,
    highlight: extractHighlightText(source),
    source,
  })
}
</script>

<template>
  <MultiPaperComparePanel @source-click="onSourceClick" />
  <PaperReader
    v-if="readerPaper"
    ref="readerRef"
    :paper-id="readerPaper.id"
    :paper-title="readerPaper.title"
    @close="readerPaper = null"
  />
</template>
