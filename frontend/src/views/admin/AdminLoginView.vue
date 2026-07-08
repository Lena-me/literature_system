<script setup lang="ts">

import { useAuthStore } from '@/stores/auth'
import AuthHeroPanel from '@/components/auth/AuthHeroPanel.vue'
import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

const router = useRouter()

const auth = useAuthStore()
const loading = reactive({
    submit: false
})
const form = reactive({
    phone: '',
    password: ''
})

// 登录
async function submit() {
    loading.submit = true
    try {
        const res = await auth.login(form.phone, form.password)
        // 检查是否为管理员角色
        if (res.role !== 'admin') {
            auth.logout()
            return ElMessage.error('该账号不是管理员账号，请联系超级管理员！')
        }
        router.push('/admin')
    }
    catch (error: any) {
        ElMessage.error(error.response?.data?.detail || error.message || '登录失败')
        // 清空认证状态
        auth.logout()
    }
    finally {
        loading.submit = false
    }
}
</script>

<template>
  <main class="login-page page-shell">
    <!-- 背景 -->
    <div class="aurora a1" />
    <div class="aurora a2" />
    <div class="grid" />

    <!-- 左侧区域 -->
    <AuthHeroPanel />

    <!-- 右侧表单 -->
    <section class="login-card glass fade-slide">
      <h2>管理员登录</h2>
      <p class="subtitle">请输入管理员账号</p>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="管理员账号">
          <el-input v-model="form.phone" size="large" />
        </el-form-item>

        <el-form-item label="密码">
          <el-input v-model="form.password" size="large" show-password/>
        </el-form-item>

        <el-button class="submit is-glow" size="large" :loading="loading.submit" @click="submit">
          登录
        </el-button>
      </el-form>

    </section>
  </main>
</template>

<style scoped>
.login-page { position:relative; overflow:hidden; display:grid; grid-template-columns: 1.1fr 460px; gap: 48px; align-items:center; padding: 70px 8vw; }
.grid { position:absolute; inset:0; background-image: linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px); background-size: 48px 48px; mask-image: radial-gradient(circle at center, #000, transparent 72%); }
.aurora { position:absolute; width:360px; height:360px; border-radius:50%; filter: blur(50px); opacity:.45; animation: floatY 8s infinite; }.a1{background:#66e7ff; left:8%; top:4%}.a2{background:#8a7cff; right:8%; bottom:8%; animation-delay:1s}.hero,.login-card{position:relative;z-index:1}.hero h1{font-size:62px;line-height:1.05;max-width:860px;margin:34px 0 18px;letter-spacing:-2px}.hero p{color:rgba(238,246,255,.72);font-size:18px;max-width:720px;line-height:1.9}.hero-cards{display:flex;gap:16px;margin-top:34px}.hero-cards div{padding:18px 22px;border-radius:20px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)}.hero-cards b{font-size:24px;display:block}.hero-cards span{color:var(--muted);font-size:13px}.login-card{border-radius:30px;padding:34px}h2{margin:0;font-size:28px}.subtitle{color:var(--muted);margin-bottom:24px}.submit{width:100%;margin-top:8px}.switches{display:flex;justify-content:center;gap:18px;margin-top:18px}.switches button{background:transparent;border:0;color:var(--brand);cursor:pointer}@media (max-width: 960px){.login-page{grid-template-columns:1fr;padding:40px 22px}.hero h1{font-size:42px}.login-card{max-width:520px}}
</style>