<script setup lang="ts">
import { computed } from 'vue'
import type { StreamFlow, StreamStage } from '@/types/domain'
import {
  inferStreamFlow,
  isStreamStageActive,
  isStreamStageDone,
  streamProgressPercent,
  streamStageLabel,
  streamStagesForFlow,
} from '@/utils/streamStages'

const props = defineProps<{
  stage: StreamStage | undefined
  flow?: StreamFlow
}>()

const resolvedFlow = computed(() => {
  if (props.flow) return props.flow
  if (props.stage) return inferStreamFlow(props.stage)
  return undefined
})

const steps = computed(() => streamStagesForFlow(resolvedFlow.value))

const progressWidth = computed(() =>
  streamProgressPercent(props.stage, resolvedFlow.value),
)

const isCompareFlow = computed(() => resolvedFlow.value === 'compare')
</script>

<template>
  <div v-if="stage" class="stream-progress" :class="{ 'stream-progress--compare': isCompareFlow }">
    <p class="stream-progress-title">{{ streamStageLabel(stage) }}</p>
    <div
      class="stream-progress-track"
      :style="{ gridTemplateColumns: `repeat(${steps.length}, 1fr)` }"
    >
      <div
        v-for="(step, idx) in steps"
        :key="step.id"
        class="stream-step"
        :class="{
          done: isStreamStageDone(step.id, stage, resolvedFlow),
          active: isStreamStageActive(step.id, stage),
          compare: step.id === 'comparing',
        }"
      >
        <div class="step-dot">
          <span v-if="isStreamStageDone(step.id, stage, resolvedFlow)">✓</span>
          <span v-else-if="isStreamStageActive(step.id, stage)" class="step-pulse" />
          <span v-else>{{ idx + 1 }}</span>
        </div>
        <span class="step-label">{{ step.label }}</span>
      </div>
    </div>
    <div class="stream-progress-bar">
      <div
        class="stream-progress-fill"
        :class="{ 'stream-progress-fill--compare': isCompareFlow }"
        :style="{ width: `${progressWidth}%` }"
      />
    </div>
  </div>
</template>

<style scoped>
.stream-progress {
  min-width: 280px;
  padding: 4px 0;
}

.stream-progress--compare .stream-progress-title {
  color: #7c3aed;
}

.stream-progress-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 500;
  color: var(--academic-text-body);
}

.stream-progress-track {
  display: grid;
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

.stream-step.compare.active .step-dot,
.stream-step.compare.done .step-dot {
  border-color: #7c3aed;
  background: #7c3aed;
  color: #fff;
}

.stream-step.compare.done .step-dot {
  background: #ede9fe;
  color: #7c3aed;
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

.stream-step.compare.active .step-label {
  color: #7c3aed;
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

.stream-progress-fill--compare {
  background: linear-gradient(90deg, #7c3aed, #a78bfa);
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.85); opacity: 0.7; }
}
</style>
