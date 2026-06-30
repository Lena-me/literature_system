<script setup lang="ts">
defineProps<{ label: string; value: string | number; hint?: string; icon?: any }>()
</script>
<template>
  <div class="stat-card">
    <div class="icon"><component :is="icon || 'DataAnalysis'" /></div>
    <div>
      <div class="value">{{ value }}</div>
      <div class="label">{{ label }}</div>
      <div class="hint" v-if="hint">{{ hint }}</div>
    </div>
  </div>
</template>
<style scoped>
.stat-card {
  border-radius: 16px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 96px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
}

.icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  color: var(--academic-primary);
  background: var(--academic-primary-light);
  font-size: 20px;
}

.value {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.5px;
  color: var(--academic-text-main);
  line-height: 1.2;
}

.label {
  color: var(--academic-text-muted);
  font-size: 13px;
  margin-top: 3px;
}

.hint {
  color: var(--academic-text-muted);
  font-size: 12px;
  margin-top: 5px;
  opacity: 0.6;
}
</style>
