<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/papers'
import { featuresApi } from '@/api/features'
import type { Paper } from '@/types/domain'

const router = useRouter()
const auth = useAuthStore()
const store = usePaperStore()
const user = auth.user!

const paperCount = ref(0)
const completedCount = ref(0)
const learningOverview = ref<any>(null)
const hotTopics = ref<string[]>([])

onMounted(async () => {
  await store.load()
  paperCount.value = store.list.length
  completedCount.value = store.list.filter(p => p.parse_status === 'completed').length

  try {
    learningOverview.value = await featuresApi.overview()
  } catch { /* ignore */ }

  try {
    const hotspots = await featuresApi.hotspots()
    hotTopics.value = (hotspots as any)?.keywords || []
  } catch { /* ignore */ }
})

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="profile-page slim-scroll">
    <!-- 头部卡片 -->
    <div class="profile-card">
      <div class="avatar-circle">{{ user.username?.slice(0, 1)?.toUpperCase() }}</div>
      <div class="profile-info">
        <h2>{{ user.name || user.username }}</h2>
        <span class="role-badge">{{ user.role === 'admin' ? '管理员' : '研究者' }}</span>
        <div class="meta-row">
          <span v-if="user.email">{{ user.email }}</span>
          <span v-if="user.phone">{{ user.phone }}</span>
          <span>注册时间 {{ user.created_at ? new Date(user.created_at).toLocaleDateString('zh-CN') : '-' }}</span>
        </div>
      </div>
      <button class="logout-btn" @click="logout">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        退出登录
      </button>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ paperCount }}</div>
        <div class="stat-label">上传文献</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ completedCount }}</div>
        <div class="stat-label">已解析</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ user.paper_upload_count || paperCount }}</div>
        <div class="stat-label">总上传量</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ user.report_generate_count || '-' }}</div>
        <div class="stat-label">生成报告</div>
      </div>
    </div>

    <!-- 学习概览 -->
    <div v-if="learningOverview" class="section">
      <h3>学习概览</h3>
      <div class="overview-grid">
        <div class="kv"><span>总学习记录</span><b>{{ learningOverview.total_records || 0 }}</b></div>
        <div class="kv"><span>今日记录</span><b>{{ learningOverview.today_records || 0 }}</b></div>
        <div class="kv"><span>连续学习</span><b>{{ learningOverview.streak_days || 0 }} 天</b></div>
        <div class="kv"><span>累计时长</span><b>{{ learningOverview.total_minutes || 0 }} 分钟</b></div>
      </div>
    </div>

    <!-- 热门主题 -->
    <div v-if="hotTopics.length" class="section">
      <h3>热门研究主题</h3>
      <div class="topic-tags">
        <span v-for="t in hotTopics" :key="t" class="topic-tag">{{ t }}</span>
      </div>
    </div>

    <!-- 帐号信息 -->
    <div class="section">
      <h3>帐号信息</h3>
      <div class="info-list">
        <div class="info-row"><span>用户名</span><b>{{ user.username }}</b></div>
        <div class="info-row"><span>邮箱</span><b>{{ user.email || '未设置' }}</b></div>
        <div class="info-row"><span>手机</span><b>{{ user.phone || '未设置' }}</b></div>
        <div class="info-row"><span>角色</span><b>{{ user.role === 'admin' ? '管理员' : '普通用户' }}</b></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-page {
  height: 100%;
  overflow-y: auto;
  padding: 28px 32px;
  max-width: 720px;
  margin: 0 auto;
  background: var(--academic-canvas);
}

/* ====== 头部 ====== */
.profile-card {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 28px;
  border-radius: 22px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  margin-bottom: 20px;
  box-shadow: var(--shadow-soft);
}

.avatar-circle {
  width: 64px;
  height: 64px;
  border-radius: 20px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--academic-primary), var(--academic-primary-hover));
  color: #fff;
  font-size: 26px;
  font-weight: 800;
  flex-shrink: 0;
}

.profile-info {
  flex: 1;
}

.profile-info h2 {
  margin: 0;
  font-size: 20px;
  color: var(--academic-text-main);
}

.role-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--academic-primary);
  background: var(--academic-primary-light);
  margin-top: 4px;
}

.meta-row {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--academic-text-muted);
}

.logout-btn {
  padding: 10px 18px;
  border-radius: 12px;
  border: 1px solid var(--academic-border);
  background: var(--academic-panel);
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s;
  flex-shrink: 0;
}

.logout-btn:hover {
  background: rgba(239, 68, 68, 0.06);
  color: var(--danger);
  border-color: var(--danger);
}

/* ====== 统计 ====== */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  padding: 20px;
  border-radius: 18px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  text-align: center;
  box-shadow: var(--shadow-soft);
}

.stat-value {
  font-size: 28px;
  font-weight: 800;
  color: var(--academic-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--academic-text-muted);
  margin-top: 4px;
}

/* ====== 段落 ====== */
.section {
  margin-bottom: 20px;
}

.section h3 {
  font-size: 15px;
  color: var(--academic-text-main);
  margin: 0 0 12px;
  font-weight: 600;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.kv {
  padding: 14px 18px;
  border-radius: 14px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
}

.kv span {
  font-size: 12px;
  color: var(--academic-text-muted);
  display: block;
}

.kv b {
  font-size: 18px;
  color: var(--academic-text-main);
  margin-top: 2px;
  display: block;
}

.topic-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.topic-tag {
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  background: var(--academic-primary-light);
  color: var(--academic-primary);
  border: 1px solid rgba(37, 99, 235, 0.15);
  font-weight: 500;
}

.info-list {
  border-radius: 16px;
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  overflow: hidden;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--academic-border);
}

.info-row:last-child {
  border-bottom: none;
}

.info-row span {
  font-size: 13px;
  color: var(--academic-text-muted);
}

.info-row b {
  font-size: 13px;
  color: var(--academic-text-body);
  font-weight: 500;
}
</style>
