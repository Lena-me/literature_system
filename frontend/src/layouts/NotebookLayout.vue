<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import UnifiedSidebar from '@/components/notebook/UnifiedSidebar.vue'
import { usePaperStore } from '@/stores/papers'

const paperStore = usePaperStore()

onMounted(() => {
  paperStore.ensureParseSync()
})

onUnmounted(() => {
  paperStore.disconnectParseEvents()
})
</script>

<template>
  <main class="notebook-layout">
    <UnifiedSidebar />
    <section class="canvas">
      <div class="main-content-container">
        <router-view />
      </div>
    </section>
  </main>
</template>

<style scoped>
.notebook-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: var(--bg-canvas);
}

.canvas {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-canvas);
}
</style>
