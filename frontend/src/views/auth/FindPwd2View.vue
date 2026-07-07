<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthHeroPanel from '@/components/auth/AuthHeroPanel.vue'
import { authApi } from '@/api/auth'

const router = useRouter()
const loading = ref(false)

const form = reactive({
  token: '',
  password: '',
  confirm_password: ''
})

onMounted(() => {
  const token = router.currentRoute.value.query.token as string
  if (!token) {
    ElMessage.warning('验证已过期，请重新找回密码')
    router.replace('/find-pwd-1')
    return
  }
  form.token = token
})

function validatePassword() {
  if (!form.password) return '请先设置新密码'
  if (form.password.length < 6 || form.password.length > 18) {
    return '密码长度需为 6-18 位'
  }
  if (!form.confirm_password) return '请再次确认新密码'
  if (!/(?=.*[a-zA-Z])(?=.*\d)/.test(form.password)) {
    return '密码需同时包含字母和数字'
  }
  return ''
}

async function submit() {
  const passwordError = validatePassword()
  if (passwordError) {
    return ElMessage.warning(passwordError)
  }
  if (form.password !== form.confirm_password) {
    return ElMessage.warning('两次输入的密码不一致')
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
    }, 1200)
  } catch {
    // 错误提示由请求拦截器统一处理
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/find-pwd-1')
}

function goToLogin() {
  router.push('/login')
}
</script>
<template>
  <main class="login-page page-shell">
    <div class="aurora a1" />
    <div class="aurora a2" />
    <div class="grid" />

    <AuthHeroPanel />

    <section class="login-card glass fade-slide">
      <h2>设置新密码</h2>
      <p class="subtitle">密码需 6-18 位，包含字母和数字</p>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="新密码">
          <el-input
            v-model="form.password"
            size="large"
            show-password
            placeholder="6-18 位，包含字母和数字"
          />
        </el-form-item>

        <el-form-item label="确认密码">
          <el-input
            v-model="form.confirm_password"
            size="large"
            show-password
            placeholder="请再次输入新密码"
          />
        </el-form-item>

        <el-button class="submit is-glow" size="large" :loading="loading" @click="submit">
          确认修改
        </el-button>
      </el-form>

      <div class="switches">
        <button @click="goBack">返回上一步</button>
        <button @click="goToLogin">返回登录</button>
      </div>
    </section>
  </main>
</template>
<style scoped>
.login-page { position:relative; overflow:hidden; display:grid; grid-template-columns: 1.1fr 460px; gap: 48px; align-items:center; padding: 70px 8vw; }
.grid { position:absolute; inset:0; background-image: linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px); background-size: 48px 48px; mask-image: radial-gradient(circle at center, #000, transparent 72%); }
.aurora { position:absolute; width:360px; height:360px; border-radius:50%; filter: blur(50px); opacity:.45; animation: floatY 8s infinite; }.a1{background:#66e7ff; left:8%; top:4%}.a2{background:#8a7cff; right:8%; bottom:8%; animation-delay:1s}.hero,.login-card{position:relative;z-index:1}.login-card{border-radius:30px;padding:34px}h2{margin:0;font-size:28px}.subtitle{color:var(--muted);margin:0 0 24px;line-height:1.6}.submit{width:100%;margin-top:8px}.switches{display:flex;justify-content:center;gap:18px;margin-top:18px}.switches button{background:transparent;border:0;color:var(--brand);cursor:pointer;font-size:14px}@media (max-width: 960px){.login-page{grid-template-columns:1fr;padding:40px 22px}.login-card{max-width:520px}}
</style>

