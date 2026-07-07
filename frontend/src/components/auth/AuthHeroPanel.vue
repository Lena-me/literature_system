<script setup lang="ts">
import BrandMark from '@/components/common/BrandMark.vue'

const features = [
  {
    key: 'qa',
    title: '智能问答',
    desc: '基于文献的深度对话',
    icon: '<path d="M21 15a2 2 0 01-2 2H9l-4 3V7a2 2 0 012-2h12a2 2 0 012 2z"/>',
  },
  {
    key: 'graph',
    title: '知识图谱',
    desc: '发现论文关联脉络',
    icon: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="17" r="2.5"/><path d="M8.2 7.5L10.5 14.5M15.5 14.5L13.8 7.5M8.5 6h7"/>',
  },
  {
    key: 'report',
    title: '研读报告',
    desc: '一键生成阅读笔记',
    icon: '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6M9 13h6M9 17h4"/>',
  },
]
</script>

<template>
  <section class="hero fade-slide">
    <BrandMark />
    <h1 class="gradient-title">从文献浩海，到精准睿识</h1>
    <div class="hero-cards">
      <div
        v-for="item in features"
        :key="item.key"
        class="feature-card"
        :class="`card-${item.key}`"
      >
        <div class="card-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="item.icon" />
        </div>
        <b>{{ item.title }}</b>
        <span>{{ item.desc }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  display: flex;
  flex-direction: column;
}

.hero h1 {
  font-size: 58px;
  line-height: 1.18;
  max-width: 820px;
  margin: 52px 0 0;
  letter-spacing: -1.5px;
}

.hero-cards {
  display: flex;
  gap: 16px;
  margin-top: 48px;
}

.feature-card {
  flex: 1;
  padding: 20px 22px;
  border-radius: 18px;
  border: 1px solid transparent;
  box-shadow: var(--shadow-soft);
}

.card-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  margin-bottom: 14px;
}

.card-icon svg {
  width: 20px;
  height: 20px;
}

.feature-card b {
  font-size: 18px;
  font-weight: 600;
  display: block;
  margin-bottom: 6px;
  color: var(--academic-text-main);
}

.feature-card span {
  color: var(--academic-text-muted);
  font-size: 13px;
  line-height: 1.55;
}

.card-qa {
  background: linear-gradient(160deg, #EFF6FF 0%, #FFFFFF 70%);
  border-color: #BFDBFE;
}
.card-qa .card-icon {
  color: #2563EB;
  background: rgba(37, 99, 235, 0.12);
}

.card-graph {
  background: linear-gradient(160deg, #F5F3FF 0%, #FFFFFF 70%);
  border-color: #DDD6FE;
}
.card-graph .card-icon {
  color: #7C3AED;
  background: rgba(124, 58, 237, 0.1);
}

.card-report {
  background: linear-gradient(160deg, #ECFDF5 0%, #FFFFFF 70%);
  border-color: #A7F3D0;
}
.card-report .card-icon {
  color: #059669;
  background: rgba(5, 150, 105, 0.1);
}

@media (max-width: 960px) {
  .hero h1 {
    font-size: 40px;
    margin-top: 36px;
    line-height: 1.22;
  }

  .hero-cards {
    flex-direction: column;
    margin-top: 36px;
    gap: 12px;
  }
}
</style>
