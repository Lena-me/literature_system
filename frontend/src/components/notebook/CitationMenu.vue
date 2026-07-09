<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Source } from '@/types/domain'
import { officialLinkLabel, resolveOfficialPaperUrl } from '@/utils/paperOfficialUrl'

const props = defineProps<{
  source: Source
  anchor: { x: number; y: number }
}>()

const emit = defineEmits<{
  close: []
  openLibrary: [source: Source]
}>()

const menuRef = ref<HTMLElement | null>(null)

const officialUrl = computed(() =>
  resolveOfficialPaperUrl({
    doi: props.source.doi,
    official_url: props.source.official_url,
  }),
)

const title = computed(
  () => props.source.paper_title || `文献 #${props.source.paper_id}`,
)

const style = computed(() => ({
  left: `${props.anchor.x}px`,
  top: `${props.anchor.y}px`,
}))

function openOfficial() {
  if (officialUrl.value) {
    window.open(officialUrl.value, '_blank', 'noopener,noreferrer')
  }
  emit('close')
}

function openLibrary() {
  emit('openLibrary', props.source)
  emit('close')
}

function onDocClick(e: MouseEvent) {
  if (menuRef.value?.contains(e.target as Node)) return
  emit('close')
}

onMounted(() => {
  document.addEventListener('click', onDocClick, true)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick, true)
})
</script>

<template>
  <div ref="menuRef" class="citation-menu" :style="style" @click.stop>
    <div class="citation-menu-title">{{ title }}</div>
    <p v-if="source.doi" class="citation-menu-meta">DOI · {{ source.doi }}</p>
    <p v-else-if="source.journal_conf" class="citation-menu-meta">{{ source.journal_conf }}</p>
    <div class="citation-menu-actions">
      <button
        v-if="officialUrl"
        type="button"
        class="action official"
        @click="openOfficial"
      >
        {{ officialLinkLabel(officialUrl) }} ↗
      </button>
      <button type="button" class="action library" @click="openLibrary">
        文库定位
      </button>
    </div>
  </div>
</template>

<style scoped>
.citation-menu {
  position: fixed;
  z-index: 1200;
  min-width: 220px;
  max-width: 320px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  box-shadow: var(--shadow-float);
  transform: translate(-50%, 8px);
}

.citation-menu-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--academic-text-main);
  line-height: 1.45;
}

.citation-menu-meta {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--academic-text-muted);
  line-height: 1.4;
  word-break: break-all;
}

.citation-menu-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
}

.action {
  width: 100%;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--academic-border);
  background: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}

.action.official {
  color: #7c3aed;
  border-color: rgba(124, 58, 237, 0.25);
  background: rgba(124, 58, 237, 0.06);
}

.action.library {
  color: var(--academic-primary);
  border-color: rgba(166, 124, 82, 0.25);
  background: var(--academic-primary-light);
}

.action:hover {
  filter: brightness(0.98);
}
</style>
