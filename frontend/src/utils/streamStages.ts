import type { StreamFlow, StreamStage } from '@/types/domain'

export const FLOW_STAGES: Record<StreamFlow, { id: StreamStage; label: string }[]> = {
  rag: [
    { id: 'classifying', label: '识别意图' },
    { id: 'embedding', label: '理解问题' },
    { id: 'searching', label: '检索文献' },
    { id: 'reranking', label: '重排序' },
    { id: 'generating', label: '生成回答' },
  ],
  compare: [
    { id: 'classifying', label: '识别意图' },
    { id: 'comparing', label: '对比文献' },
    { id: 'generating', label: '生成回答' },
  ],
  report: [
    { id: 'classifying', label: '识别意图' },
    { id: 'reporting', label: '生成报告' },
    { id: 'generating', label: '生成回答' },
  ],
  graph: [
    { id: 'classifying', label: '识别意图' },
    { id: 'graphing', label: '构建图谱' },
    { id: 'generating', label: '生成回答' },
  ],
  general: [
    { id: 'classifying', label: '识别意图' },
    { id: 'generating', label: '生成回答' },
  ],
}

/** @deprecated 保留兼容；新代码请用 FLOW_STAGES */
export const STREAM_STAGES = FLOW_STAGES.rag

const STAGE_LABELS: Record<StreamStage, string> = {
  classifying: '正在识别意图…',
  embedding: '正在理解问题…',
  searching: '正在检索文献…',
  reranking: '正在重排序…',
  comparing: '正在对比文献…',
  reporting: '正在生成研读报告…',
  graphing: '正在构建知识图谱…',
  generating: '正在生成回答…',
}

export function inferStreamFlow(stage: StreamStage, currentFlow?: StreamFlow): StreamFlow | undefined {
  if (stage === 'comparing') return 'compare'
  if (stage === 'reporting') return 'report'
  if (stage === 'graphing') return 'graph'
  if (stage === 'embedding' || stage === 'searching' || stage === 'reranking') return 'rag'
  if (stage === 'generating') return currentFlow ?? 'general'
  return currentFlow
}

export function streamStageLabel(stage: StreamStage | undefined): string {
  if (!stage) return ''
  return STAGE_LABELS[stage] || ''
}

export function streamStagesForFlow(flow: StreamFlow | undefined): { id: StreamStage; label: string }[] {
  if (!flow) {
    return [{ id: 'classifying', label: '识别意图' }]
  }
  return FLOW_STAGES[flow]
}

export function streamStageIndexInFlow(flow: StreamFlow, stage: StreamStage): number {
  return FLOW_STAGES[flow].findIndex((s) => s.id === stage)
}

export function isStreamStageDone(
  step: StreamStage,
  current: StreamStage | undefined,
  flow: StreamFlow | undefined,
): boolean {
  if (!current || !flow) return false
  const stepIdx = streamStageIndexInFlow(flow, step)
  const curIdx = streamStageIndexInFlow(flow, current)
  if (stepIdx < 0 || curIdx < 0) return false
  return stepIdx < curIdx
}

export function isStreamStageActive(step: StreamStage, current: StreamStage | undefined): boolean {
  return step === current
}

export function streamProgressPercent(
  stage: StreamStage | undefined,
  flow: StreamFlow | undefined,
): number {
  if (!stage || !flow) return stage === 'classifying' ? 50 : 0
  const stages = FLOW_STAGES[flow]
  const idx = stages.findIndex((s) => s.id === stage)
  if (idx < 0) return 0
  return ((idx + 1) / stages.length) * 100
}
