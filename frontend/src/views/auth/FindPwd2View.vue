<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import BrandMark from '@/components/common/BrandMark.vue'
import { authApi } from '@/api/auth';

const router = useRouter();
const loading = ref(false)
const codeLoading = ref(false)

const form = reactive({
    token: '',
    password: '',
    confirm_password: ''
})

// 初始化时获取token
onMounted(() => {
    // 从路由参数中获取token
    const token = router.currentRoute.value.query.token as string
    form.token = token
})

// 密码校验规则
const validatePassword = () => {
    if (!form.password) {
        return '请输入新密码'
    }
    if (form.password.length < 6 || form.password.length > 18) {
        return '密码长度必须在6-18位之间'
    }
    if (!form.confirm_password) {
        return '请确认新密码'
    }
    
    // 密码复杂性校验
    // if (!/(?=.*[a-zA-Z])(?=.*\d)/.test(form.password)) {
    //     return ElMessage.warning('密码必须同时包含字母和数字')
    // }
    return ''
}

// 提交重置密码
async function submit() {
    // 校验密码
    const passwordError = validatePassword()
    if (passwordError) {
        return ElMessage.warning(passwordError)
    }
    if (form.password !== form.confirm_password) {
        return ElMessage.warning('两次密码不一致')
    }

    loading.value = true
    try {
        await authApi.resetPassword({
            token: form.token,
            password: form.password,
            confirm_password: form.confirm_password
        })
        ElMessage.success('密码重置成功，请重新登录')
        setTimeout(() => {
            router.push('/login')
        }, 1500)
    }
    catch (error: any){
        ElMessage.error(error.response?.data?.detail || '密码重置失败')
    }
    finally {
        loading.value = false
    }
}

// 返回上一步
function goBack() {
    router.push('/find-pwd-1')
}

// 返回登录界面
function goToLogin() {
    router.push('/login')
}
</script>
<template>
  <main class="login-page page-shell">
    <!-- 背景 -->
    <div class="aurora a1" />
    <div class="aurora a2" />
    <div class="grid" />

    <!-- 左侧区域 -->
    <section class="hero fade-slide">
      <BrandMark />
      <h1 class="gradient-title">把论文变成可问、可比、可复现的知识系统</h1>
      <p>文献上传、结构化解析、RAG溯源问答、研读报告、多文献对比、知识图谱与复现实验建议的一体化科研工作台。</p >
      <div class="hero-cards">
        <div>
          <b>RAG</b>
          <span>检索增强生成</span>
        </div>
        <div>
          <b>Graph</b>
          <span>主题实体网络</span>
        </div>
        <div>
          <b>Agent</b>
          <span>报告与复现推导</span>
        </div>
      </div>
    </section>

    <!-- 右侧表单 -->
    <section class="login-card glass fade-slide">
      <h2>重置密码 - 第二步</h2>
      <p class="subtitle">请设置新密码</p>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="新密码">
          <el-input v-model="form.password" size="large" show-password placeholder="请输入新密码（6-18位，需包含字母和数字）"/>
        </el-form-item>

        <el-form-item label="确认密码">
          <el-input v-model="form.confirm_password" size="large" show-password placeholder="请再次输入新密码"/>
        </el-form-item>

        <el-button class="submit is-glow" size="large" :loading="loading" @click="submit">
          确认修改
        </el-button>
      </el-form>

      <!-- 底部按钮 -->
      <div class="switches">
        <button @click="goBack">上一步</button>
        <button @click="goToLogin">返回登录</button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page { position:relative; overflow:hidden; display:grid; grid-template-columns: 1.1fr 460px; gap: 48px; align-items:center; padding: 70px 8vw; }
.grid { position:absolute; inset:0; background-image: linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px); background-size: 48px 48px; mask-image: radial-gradient(circle at center, #000, transparent 72%); }
.aurora { position:absolute; width:360px; height:360px; border-radius:50%; filter: blur(50px); opacity:.45; animation: floatY 8s infinite; }.a1{background:#66e7ff; left:8%; top:4%}.a2{background:#8a7cff; right:8%; bottom:8%; animation-delay:1s}.hero,.login-card{position:relative;z-index:1}.hero h1{font-size:62px;line-height:1.05;max-width:860px;margin:34px 0 18px;letter-spacing:-2px}.hero p{color:rgba(238,246,255,.72);font-size:18px;max-width:720px;line-height:1.9}.hero-cards{display:flex;gap:16px;margin-top:34px}.hero-cards div{padding:18px 22px;border-radius:20px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)}.hero-cards b{font-size:24px;display:block}.hero-cards span{color:var(--muted);font-size:13px}.login-card{border-radius:30px;padding:34px}h2{margin:0;font-size:28px}.subtitle{color:var(--muted);margin-bottom:24px}.submit{width:100%;margin-top:8px}.switches{display:flex;justify-content:center;gap:18px;margin-top:18px}.switches button{background:transparent;border:0;color:var(--brand);cursor:pointer}@media (max-width: 960px){.login-page{grid-template-columns:1fr;padding:40px 22px}.hero h1{font-size:42px}.login-card{max-width:520px}}
</style>
