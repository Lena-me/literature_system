<script setup lang="ts">
defineProps<{ label: string; value: string | number; hint?: string; icon?: any }>()
</script>
<template>
  <div class="stat-card glass">
    <div class="icon"><component :is="icon || 'DataAnalysis'" /></div>
    <div>
      <div class="value">{{ value }}</div>
      <div class="label">{{ label }}</div>
      <div class="hint" v-if="hint">{{ hint }}</div>
    </div>
  </div>
</template>
<style scoped>
.stat-card { border-radius: 22px; padding: 18px; display: flex; align-items: center; gap: 14px; min-height: 96px; }
.icon { width: 44px; height: 44px; border-radius: 16px; display: grid; place-items: center; color: #06111f; background: linear-gradient(135deg, var(--brand), var(--brand-3)); }
.value { font-size: 28px; font-weight: 850; letter-spacing: -.5px; }
.label { color: var(--muted); font-size: 13px; margin-top: 3px; }
.hint { color: rgba(238,246,255,.48); font-size: 12px; margin-top: 5px; }
</style>
