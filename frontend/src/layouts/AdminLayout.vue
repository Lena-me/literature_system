<script setup lang="ts">
import { useRouter } from 'vue-router'
import BrandMark from '@/components/common/BrandMark.vue'
import { useAuthStore } from '@/stores/auth'
const router = useRouter(); const auth = useAuthStore(); function logout(){ auth.logout(); router.push('/admin/login') }
</script>
<template>
  <main class="admin-layout page-shell">
    <aside class="side glass">
      <BrandMark />
      <div class="admin-badge">Administrator Console</div>
      <router-link to="/admin"><DataBoard /> 运维总览</router-link>
      <router-link to="/admin/users"><User /> 用户与配额</router-link>
      <router-link to="/admin/models"><Cpu /> 模型配置</router-link>
      <router-link to="/admin/tasks"><Operation /> 解析任务</router-link>
      <router-link to="/admin/ops"><Monitor /> 向量库与日志</router-link>
      <router-link to="/research"><Back /> 返回用户端</router-link>
      <el-button class="logout" @click="logout">退出登录</el-button>
    </aside>
    <section class="admin-content"><router-view /></section>
  </main>
</template>
<style scoped>
.admin-layout{min-height:100vh;display:grid;grid-template-columns:280px 1fr;gap:20px;padding:20px}.side{border-radius:30px;padding:22px;display:flex;flex-direction:column;gap:10px;min-height:calc(100vh - 40px)}.admin-badge{margin:14px 0 18px;color:var(--brand);font-size:12px;letter-spacing:1px;text-transform:uppercase}.side a{display:flex;gap:10px;align-items:center;padding:13px 14px;border-radius:16px;color:rgba(238,246,255,.72)}.side a.router-link-active,.side a:hover{background:rgba(138,124,255,.18);color:#fff}.logout{margin-top:auto}.admin-content{min-width:0}
</style>
