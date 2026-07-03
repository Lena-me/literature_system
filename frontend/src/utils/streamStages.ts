import type { StreamStage } from '@/types/domain'

export const STREAM_STAGES: { id: StreamStage; label: string }[] = [
  { id: 'embedding', label: '理解问题' },
  { id: 'searching', label: '检索文献' },
  { id: 'reranking', label: '重排序' },
  { id: 'generating', label: '生成回答' },
]

const STAGE_ORDER: StreamStage[] = ['embedding', 'searching', 'reranking', 'generating']

export function streamStageLabel(stage: StreamStage | undefined): string {
  if (!stage) return ''
  const map: Record<StreamStage, string> = {
    embedding: '正在理解问题…',
    searching: '正在检索文献…',
    reranking: '正在重排序…',
    generating: '正在生成回答…',
  }
  return map[stage] || ''
}

export function streamStageIndex(stage: StreamStage | undefined): number {
  if (!stage) return -1
  return STAGE_ORDER.indexOf(stage)
}

export function isStreamStageDone(step: StreamStage, current: StreamStage | undefined): boolean {
  if (!current) return true
  return streamStageIndex(step) < streamStageIndex(current)
}

export function isStreamStageActive(step: StreamStage, current: StreamStage | undefined): boolean {
  return step === current
}

/** 检索阶段可能跳过 embedding / reranking，仅展示到当前步骤 */
export function visibleStreamStages(current: StreamStage | undefined): typeof STREAM_STAGES {
  if (!current || current === 'generating') return STREAM_STAGES
  const idx = streamStageIndex(current)
  return STREAM_STAGES.filter((_, i) => i <= idx || STREAM_STAGES[i].id === 'generating')
}
