<script setup lang="ts">
import type { StreamStage } from '@/types/domain'
import {
  STREAM_STAGES,
  isStreamStageActive,
  isStreamStageDone,
  streamStageLabel,
} from '@/utils/streamStages'

defineProps<{
  stage: StreamStage | undefined
}>()
</script>

<template>
  <div v-if="stage" class="stream-progress">
    <p class="stream-progress-title">{{ streamStageLabel(stage) }}</p>
    <div class="stream-progress-track">
      <div
        v-for="(step, idx) in STREAM_STAGES"
        :key="step.id"
        class="stream-step"
        :class="{
          done: isStreamStageDone(step.id, stage),
          active: isStreamStageActive(step.id, stage),
        }"
      >
        <div class="step-dot">
          <span v-if="isStreamStageDone(step.id, stage)">✓</span>
          <span v-else-if="isStreamStageActive(step.id, stage)" class="step-pulse" />
          <span v-else>{{ idx + 1 }}</span>
        </div>
        <span class="step-label">{{ step.label }}</span>
      </div>
    </div>
    <div class="stream-progress-bar">
      <div
        class="stream-progress-fill"
        :style="{ width: `${((STREAM_STAGES.findIndex(s => s.id === stage) + 1) / STREAM_STAGES.length) * 100}%` }"
      />
    </div>
  </div>
</template>

<style scoped>
.stream-progress {
  min-width: 280px;
  padding: 4px 0;
}

.stream-progress-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 500;
  color: var(--academic-text-body);
}

.stream-progress-track {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  margin-bottom: 10px;
}

.stream-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  opacity: 0.45;
  transition: opacity 0.2s;
}

.stream-step.done,
.stream-step.active {
  opacity: 1;
}

.step-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid var(--academic-border);
  background: var(--academic-panel);
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--academic-text-muted);
}

.stream-step.done .step-dot {
  border-color: var(--academic-primary);
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  font-size: 12px;
}

.stream-step.active .step-dot {
  border-color: var(--academic-primary);
  background: var(--academic-primary);
}

.step-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
  animation: pulse 1s ease-in-out infinite;
}

.step-label {
  font-size: 11px;
  color: var(--academic-text-muted);
  text-align: center;
  line-height: 1.2;
}

.stream-step.active .step-label {
  color: var(--academic-primary);
  font-weight: 600;
}

.stream-progress-bar {
  height: 4px;
  border-radius: 999px;
  background: var(--academic-border);
  overflow: hidden;
}

.stream-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--academic-primary), #6366f1);
  transition: width 0.35s ease;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.85); opacity: 0.7; }
}
</style>
