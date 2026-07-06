<script setup lang="ts">
import type { ExternalReference } from '@/types/domain'
import { officialLinkLabel, sanitizePaperTitle } from '@/utils/paperOfficialUrl'

defineProps<{ refs: ExternalReference[] }>()

function sourceLabel(item: ExternalReference): string {
  if (item.source_type === 'reference_bibliography') return '参考文献拓展'
  if (item.source_type === 'library_recommendation') return '文献库推荐'
  if (item.source_type === 'scholar_search') return 'Scholar 检索'
  return '文中提及'
}

function openUrl(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <div v-if="refs.length" class="external-refs">
    <div class="external-refs-head">拓展阅读 / 外部溯源</div>
    <button
      v-for="(item, idx) in refs"
      :key="`${item.official_url}-${idx}`"
      type="button"
      class="external-ref-card"
      @click="openUrl(item.official_url)"
    >
      <span class="ref-badge">{{ sourceLabel(item) }}</span>
      <span class="ref-title">{{ sanitizePaperTitle(item.title) }}</span>
      <span class="ref-action">{{ officialLinkLabel(item.official_url) }} ↗</span>
    </button>
  </div>
</template>

<style scoped>
.external-refs {
  margin-top: 10px;
  width: 100%;
  max-width: 800px;
}

.external-refs-head {
  font-size: 12px;
  color: var(--academic-text-muted);
  margin-bottom: 8px;
}

.external-ref-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 6px;
  border-radius: 10px;
  border: 1px solid rgba(124, 58, 237, 0.22);
  background: linear-gradient(135deg, rgba(124, 58, 237, 0.05), rgba(99, 102, 241, 0.03));
  cursor: pointer;
  text-align: left;
}

.external-ref-card:hover {
  border-color: rgba(124, 58, 237, 0.42);
  transform: translateX(2px);
}

.ref-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: #7c3aed;
  background: rgba(124, 58, 237, 0.12);
  padding: 2px 6px;
  border-radius: 999px;
}

.ref-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--academic-text-body);
  white-space: normal;
  word-break: break-word;
}

.ref-action {
  flex-shrink: 0;
  font-size: 11px;
  color: #7c3aed;
  font-weight: 600;
}
</style>
