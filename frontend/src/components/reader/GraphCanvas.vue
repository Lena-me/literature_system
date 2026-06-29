<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Graph } from '@antv/g6'
import type { KnowledgeGraph } from '@/types/domain'

const props = defineProps<{ graph?: KnowledgeGraph | null }>()
const el = ref<HTMLDivElement | null>(null)
let instance: any

async function render() {
  if (!el.value || !props.graph || !props.graph.nodes?.length) return

  await nextTick()
  await new Promise(resolve => setTimeout(resolve, 80))

  instance?.destroy?.()

  const width = el.value.clientWidth || 800
  const height = el.value.clientHeight || 520

  const data = {
    nodes: props.graph.nodes.map(n => ({
      id: String(n.id),
      data: {
        label: n.name,
        type: n.type
      }
    })),
    edges: props.graph.edges.map(e => ({
      source: String(e.source),
      target: String(e.target),
      data: {
        label: e.relation_type
      }
    }))
  }

  instance = new Graph({
    container: el.value,
    width,
    height,
    data,
    node: {
      style: {
        labelText: (d: any) => d.data.label,
        fill: '#111c33',
        stroke: '#66e7ff',
        lineWidth: 1.5,
        labelFill: '#eef6ff'
      }
    },
    edge: {
      style: {
        stroke: 'rgba(255,255,255,.28)',
        labelText: (d: any) => d.data.label,
        labelFill: '#9fb1cc'
      }
    },
    layout: {
      type: 'force',
      preventOverlap: true,
      linkDistance: 110
    },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element']
  })

  instance.render()
}

onMounted(render)
watch(() => props.graph, render, { deep: true })

onBeforeUnmount(() => {
  instance?.destroy?.()
})
</script>

<template>
  <div ref="el" class="graph-canvas">
    <div v-if="!graph" class="empty">Click knowledge graph to show entity relations.</div>
    <div v-else-if="!graph.nodes || graph.nodes.length === 0" class="empty">
      The current graph has no nodes. Check extraction results or regenerate the graph.
    </div>
  </div>
</template>

<style scoped>
.graph-canvas {
  height: 520px;
  border-radius: 22px;
  background: radial-gradient(circle at center, rgba(102,231,255,.13), rgba(255,255,255,.04));
  border: 1px solid rgba(255,255,255,.12);
  overflow: hidden;
  position: relative;
}
.empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: rgba(238,246,255,.55);
  text-align: center;
  padding: 20px;
}
</style>
