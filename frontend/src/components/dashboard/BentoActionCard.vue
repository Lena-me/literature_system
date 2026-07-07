<script setup lang="ts">
defineProps<{
  title: string
  subtitle: string
  size?: 'hero' | 'featured' | 'medium' | 'compact'
  tone?: 'blue' | 'violet' | 'indigo' | 'emerald' | 'amber' | 'slate'
}>()

defineEmits<{ click: [] }>()
</script>

<template>
  <button
    type="button"
    class="bento-card"
    :class="[`is-${size || 'compact'}`, `tone-${tone || 'slate'}`]"
    @click="$emit('click')"
  >
    <div v-if="size === 'hero' || size === 'featured'" class="bento-mesh" aria-hidden="true" />
    <div class="bento-content">
      <template v-if="size === 'hero' || size === 'featured'">
        <div class="bento-icon" aria-hidden="true">
          <slot name="icon" />
        </div>
        <div class="bento-text">
          <strong class="bento-title">{{ title }}</strong>
          <span class="bento-subtitle">{{ subtitle }}</span>
        </div>
      </template>

      <template v-else>
        <div class="bento-compact-group">
          <div class="bento-icon" aria-hidden="true">
            <slot name="icon" />
          </div>
          <div class="bento-text">
            <strong class="bento-title">{{ title }}</strong>
            <span class="bento-subtitle">{{ subtitle }}</span>
          </div>
        </div>
      </template>
    </div>
    <div v-if="$slots.decor" class="bento-decor" aria-hidden="true">
      <slot name="decor" />
    </div>
  </button>
</template>

<style scoped>
.bento-card {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: stretch;
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
  border: none;
  border-radius: 20px;
  background: #ffffff;
  color: var(--academic-text-body);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.05),
    0 2px 4px -1px rgba(0, 0, 0, 0.03);
  transition:
    transform 0.22s cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.bento-card:hover {
  transform: translateY(-2px);
  box-shadow:
    0 12px 28px -6px rgba(0, 0, 0, 0.1),
    0 4px 10px -2px rgba(0, 0, 0, 0.04);
}

.bento-card:active {
  transform: translateY(0);
}

.bento-mesh {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

.tone-blue .bento-mesh {
  background:
    radial-gradient(ellipse 90% 70% at 88% 12%, rgba(56, 189, 248, 0.42), transparent 68%),
    radial-gradient(ellipse 75% 55% at 12% 88%, rgba(37, 99, 235, 0.28), transparent 65%),
    radial-gradient(ellipse 55% 45% at 55% 45%, rgba(99, 102, 241, 0.14), transparent 70%),
    linear-gradient(155deg, #ffffff 0%, #f8fbff 45%, #eef4ff 100%);
}

.tone-violet .bento-mesh {
  background:
    radial-gradient(ellipse 85% 65% at 90% 18%, rgba(167, 139, 250, 0.45), transparent 68%),
    radial-gradient(ellipse 70% 55% at 8% 82%, rgba(99, 102, 241, 0.3), transparent 65%),
    radial-gradient(ellipse 50% 40% at 48% 38%, rgba(192, 132, 252, 0.16), transparent 70%),
    linear-gradient(155deg, #ffffff 0%, #faf8ff 45%, #f3f0ff 100%);
}

.tone-emerald .bento-mesh {
  background:
    radial-gradient(ellipse 88% 68% at 92% 20%, rgba(52, 211, 153, 0.42), transparent 68%),
    radial-gradient(ellipse 72% 58% at 10% 78%, rgba(16, 185, 129, 0.3), transparent 65%),
    radial-gradient(ellipse 52% 42% at 50% 42%, rgba(45, 212, 191, 0.14), transparent 70%),
    linear-gradient(155deg, #ffffff 0%, #f0fdf9 45%, #ecfdf5 100%);
}

.bento-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 12px;
  padding: 20px 22px;
  width: 100%;
  height: 100%;
  flex: 1;
}

.is-hero .bento-content,
.is-featured .bento-content {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 12px;
  padding: 22px 28px 20px;
  max-width: 62%;
  height: 100%;
  overflow: visible;
}

.is-compact .bento-content,
.is-medium .bento-content {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: flex-start;
  padding: 18px 20px;
  max-width: 100%;
}

.bento-compact-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  max-width: 68%;
}

.is-compact .bento-text,
.is-medium .bento-text {
  gap: 3px;
}

.is-hero .bento-text,
.is-featured .bento-text {
  gap: 8px;
  flex-shrink: 0;
}

.is-hero .bento-subtitle,
.is-featured .bento-subtitle {
  display: block;
  white-space: normal;
  overflow: visible;
  line-height: 1.6;
  word-break: break-word;
}

.bento-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(15, 23, 42, 0.05);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.95),
    inset 0 -1px 2px rgba(15, 23, 42, 0.04),
    0 1px 4px rgba(15, 23, 42, 0.05);
}

.is-hero .bento-icon,
.is-featured .bento-icon {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.7);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    0 4px 12px rgba(15, 23, 42, 0.06);
}

.is-compact .bento-icon,
.is-medium .bento-icon {
  width: 42px;
  height: 42px;
}

.bento-text {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.bento-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.3;
  letter-spacing: -0.01em;
}

.is-hero .bento-title {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.35;
}

.is-featured .bento-title {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.025em;
}

.is-compact .bento-title,
.is-medium .bento-title {
  font-size: 16px;
}

.bento-subtitle {
  font-size: 13px;
  line-height: 1.55;
  color: #64748b;
  font-weight: 400;
}

.is-compact .bento-subtitle {
  font-size: 12px;
}

.tone-blue .bento-icon { color: #2563eb; }

.tone-violet .bento-icon { color: #6366f1; }

.tone-emerald .bento-icon { color: #059669; }

.bento-decor {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

.tone-indigo .bento-icon {
  background: rgba(99, 102, 241, 0.08);
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.1);
}

.tone-indigo.is-compact {
  background: linear-gradient(160deg, #ffffff 50%, #f5f3ff 100%);
}

.tone-indigo.is-compact:hover .bento-title {
  color: #4f46e5;
}

.tone-amber .bento-icon {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
  border-color: rgba(245, 158, 11, 0.12);
}

.tone-amber.is-compact {
  background: linear-gradient(160deg, #ffffff 50%, #fffbeb 100%);
}

.tone-amber.is-compact:hover .bento-title {
  color: #b45309;
}

.tone-slate .bento-icon {
  background: rgba(100, 116, 139, 0.08);
  color: #475569;
  border-color: rgba(100, 116, 139, 0.1);
}

.tone-slate:hover .bento-title {
  color: var(--academic-primary);
}

@media (max-width: 860px) {
  .is-hero .bento-content,
  .is-featured .bento-content,
  .is-compact .bento-content,
  .is-medium .bento-content {
    max-width: 100%;
  }
}
</style>
