<script setup lang="ts">
import UnifiedSidebar from '@/components/notebook/UnifiedSidebar.vue'
</script>

<template>
  <main class="notebook-layout">
    <UnifiedSidebar />
    <section class="canvas">
      <router-view />
    </section>
  </main>
</template>

<style scoped>
.notebook-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: var(--academic-canvas);
}

.canvas {
  flex: 1;
  min-width: 0;
  position: relative;
  overflow: hidden;
  background: var(--academic-canvas);
}
</style>
