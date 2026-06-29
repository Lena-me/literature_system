<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import BrandMark from '@/components/common/BrandMark.vue'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/papers'
const router = useRouter(); const auth = useAuthStore(); const papers = usePaperStore()
onMounted(() => papers.load())
function logout(){ auth.logout(); router.push('/login') }
</script>
<template>
  <main class="research-layout page-shell">
    <aside class="nav glass">
      <BrandMark />
      <nav>
        <router-link to="/research"><House /> 工作台</router-link>
        <router-link to="/research/library"><Files /> 文献库</router-link>
        <router-link to="/research/reports"><Document /> 研读报告</router-link>
        <router-link to="/research/archive"><TrendCharts /> 学习档案</router-link>
        <router-link v-if="auth.isAdmin" to="/admin"><Setting /> 管理后台</router-link>
      </nav>
      <div class="profile">
        <div class="avatar">{{ auth.user?.username?.slice(0,1)?.toUpperCase() }}</div>
        <div><b>{{ auth.user?.name || auth.user?.username }}</b><span>{{ auth.user?.role }}</span></div>
        <el-button text @click="logout"><SwitchButton /></el-button>
      </div>
    </aside>
    <section class="content"><router-view /></section>
  </main>
</template>
<style scoped>
.research-layout { min-height:100vh; display:grid; grid-template-columns: 286px 1fr; gap: 20px; padding: 20px; }
.nav { border-radius: 30px; padding: 22px; display:flex; flex-direction:column; gap:28px; min-height: calc(100vh - 40px); position:sticky; top:20px; }
nav { display:flex; flex-direction:column; gap:10px; }
nav a { display:flex; gap:10px; align-items:center; padding:13px 14px; border-radius:16px; color:rgba(238,246,255,.72); transition:.2s; }
nav a.router-link-active, nav a:hover { background:rgba(102,231,255,.14); color:#fff; }
.profile { margin-top:auto; display:flex; align-items:center; gap:10px; padding:12px; border-radius:18px; background:rgba(255,255,255,.07); }
.avatar { width:38px; height:38px; border-radius:14px; display:grid; place-items:center; background:linear-gradient(135deg,var(--brand),var(--brand-2)); color:#06111f; font-weight:850; }
.profile b{display:block}.profile span{font-size:12px;color:var(--muted)}.profile :deep(.el-button){margin-left:auto;color:var(--muted)}
.content { min-width:0; }
@media(max-width:980px){.research-layout{grid-template-columns:1fr}.nav{position:relative;min-height:auto}.nav nav{flex-direction:row;overflow:auto}.profile{display:none}}
</style>
