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

const isToolFlow = computed(() =>
  resolvedFlow.value === 'compare' ||
  resolvedFlow.value === 'report' ||
  resolvedFlow.value === 'graph',
)
</script>

<template>
  <div v-if="stage" class="stream-progress" :class="{ 'stream-progress--tool': isToolFlow }">
    <p class="stream-progress-title">{{ streamStageLabel(stage) }}</p>
    <div class="stream-progress-track">
      <div
        v-for="(step, idx) in steps"
        :key="step.id"
        class="stream-step"
        :class="{
          done: isStreamStageDone(step.id, stage, resolvedFlow),
          active: isStreamStageActive(step.id, stage),
          tool: ['comparing', 'reporting', 'graphing'].includes(step.id),
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
        :class="{ 'stream-progress-fill--tool': isToolFlow }"
        :style="{ width: `${progressWidth}%` }"
      />
    </div>
  </div>
</template>

<style scoped>
.stream-progress {
  min-width: 320px;
  padding: 10px 16px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 12px;
  margin-bottom: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
}

.stream-progress-title {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--academic-primary);
}

.stream-progress-track {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  position: relative;
}

.stream-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  min-width: 0;
  opacity: 0.45;
  transition: opacity 0.3s ease;
}

.stream-step.done,
.stream-step.active {
  opacity: 1;
}

.step-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--academic-border);
  background: var(--academic-panel);
  display: grid;
  place-items: center;
  font-size: 8px;
  font-weight: 600;
  color: var(--academic-text-muted);
}

.stream-step.done .step-dot {
  border-color: var(--academic-primary);
  background: var(--academic-primary);
  color: #fff;
}

.stream-step.active .step-dot {
  border-color: var(--academic-primary);
  background: var(--academic-primary-light);
}

.step-pulse {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--academic-primary);
  animation: pulse 1.6s ease-in-out infinite;
}

.step-label {
  font-size: 10px;
  color: var(--academic-text-muted);
  margin-top: 4px;
  text-align: center;
  line-height: 1.2;
}

.stream-step.active .step-label {
  color: var(--academic-primary);
  font-weight: 600;
}

.stream-progress-bar {
  height: 2px;
  border-radius: 999px;
  background: var(--academic-border);
  overflow: hidden;
  margin-top: 4px;
}

.stream-progress-fill {
  height: 100%;
  background: var(--academic-primary);
  transition: width 0.4s ease;
}

@keyframes pulse {
  0% { transform: scale(0.9); opacity: 0.6; }
  50% { transform: scale(1.1); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.6; }
}
</style>
