<script setup lang="ts">

import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthHeroPanel from '@/components/auth/AuthHeroPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { codeSentMessage } from '@/utils/authMessages'

const router = useRouter()

const auth = useAuthStore()
const mode = ref<'login'|'register'>('login')
const form = reactive({
  phone: '',
  username: '',
  password: '',
  confirm_password: '',
  name: '',
  email: '',
  code: ''
})

const title = computed(() => mode.value === 'login' ? '登录' : '注册')
const subtitle = computed(() => mode.value === 'login'
  ? '使用手机号和密码登录'
  : '填写信息完成账号注册')

const phoneNum = computed(() => form.phone)

async function getCode() {
  if (!phoneNum.value) {
    return ElMessage.warning('请输入手机号')
  }
  if (!/^1[3-9]\d{9}$/.test(phoneNum.value)) {
    return ElMessage.warning('请输入正确的手机号')
  }

  const res = await authApi.sendCode(phoneNum.value, 'register')
  if (res.dev_code) {
    form.code = res.dev_code
  }
  ElMessage.success(codeSentMessage(res.dev_code))
}

async function submit() {
  if (mode.value === 'login') {
    if (!form.phone) return ElMessage.warning('请输入手机号')
    if (!form.password) return ElMessage.warning('请输入密码')

    try {
      const user = await auth.login(form.phone, form.password)
      if (user.role !== 'researcher') {
        auth.logout()
        return ElMessage.warning('该账号请使用管理员入口登录')
      }
      await router.replace('/dashboard')
    } catch {
      // 错误提示由请求拦截器统一处理
    }
    return
  }

  if (!form.username.trim()) return ElMessage.warning('请输入用户名')
  if (!form.phone) return ElMessage.warning('请输入手机号')
  if (!/^1[3-9]\d{9}$/.test(form.phone)) return ElMessage.warning('请输入正确的手机号')
  if (!form.password) return ElMessage.warning('请输入密码')
  if (form.password.length < 6 || form.password.length > 18) {
    return ElMessage.warning('密码长度为 6-18 位')
  }
  if (!/(?=.*[a-zA-Z])(?=.*\d)/.test(form.password)) {
    return ElMessage.warning('密码需包含字母和数字')
  }
  if (form.password !== form.confirm_password) return ElMessage.warning('两次密码不一致')
  if (!form.code) return ElMessage.warning('请输入验证码')

  try {
    auth.logout()
    localStorage.removeItem('access_token')
    sessionStorage.removeItem('access_token')
    await authApi.register({
      username: form.username,
      password: form.password,
      confirm_password: form.confirm_password,
      email: form.email,
      phone: form.phone,
      code: form.code
    })
    ElMessage.success('注册成功，请登录')
    setTimeout(() => {
      window.location.replace('/login')
    }, 1500)
  } catch {
    // 错误提示由请求拦截器统一处理
  }
}
</script>
<template>
  <main class="login-page page-shell" :class="{ 'is-register': mode === 'register' }">
    <div class="aurora a1" />
    <div class="aurora a2" />
    <div class="grid" />

    <AuthHeroPanel />

    <section class="login-card glass fade-slide" :class="{ 'is-register': mode === 'register' }">
      <h2>{{ title }}</h2>
      <p class="subtitle">{{ subtitle }}</p>

      <el-form label-position="top" @submit.prevent>
        <el-form-item v-if="mode === 'login'" label="手机号">
          <el-input v-model="form.phone" size="large" placeholder="请输入手机号" />
        </el-form-item>

        <template v-if="mode === 'register'">
          <el-form-item label="用户名">
            <el-input v-model="form.username" placeholder="请输入用户名" />
          </el-form-item>

          <el-form-item label="邮箱">
            <el-input v-model="form.email" placeholder="请输入邮箱（选填）" />
          </el-form-item>

          <el-form-item label="手机号">
            <el-input v-model="form.phone" placeholder="请输入手机号" />
          </el-form-item>
        </template>

        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            :size="mode === 'login' ? 'large' : 'default'"
            show-password
            :placeholder="mode === 'login' ? '请输入密码' : '6-18 位，包含字母和数字'"
          />
        </el-form-item>

        <el-form-item v-if="mode !== 'login'" label="确认密码">
          <el-input v-model="form.confirm_password" show-password placeholder="请再次输入密码" />
        </el-form-item>

        <el-form-item v-if="mode !== 'login'" label="验证码">
          <el-input v-model="form.code" placeholder="请输入验证码">
            <template #append>
              <el-button @click="getCode">获取验证码</el-button>
            </template>
          </el-input>
        </el-form-item>

        <el-button
          class="submit is-glow"
          :size="mode === 'login' ? 'large' : 'default'"
          :loading="auth.loading"
          @click="submit"
        >
          {{ mode === 'login' ? '登录' : '注册' }}
        </el-button>
      </el-form>

      <div class="switches">
        <button v-if="mode !== 'login'" @click="mode='login'">返回登录</button>
        <button v-if="mode !== 'register'" @click="mode='register'">没有账号？注册</button>
        <button v-if="mode === 'login'" @click="router.push('/find-pwd-1')">忘记密码</button>
      </div>
    </section>
  </main>
</template>
<style scoped>
.login-page {
  position: relative;
  overflow: hidden;
  display: grid;
  grid-template-columns: 1.1fr 460px;
  gap: 48px;
  align-items: center;
  padding: 70px 8vw;
}

.login-page.is-register {
  grid-template-columns: 1.1fr 380px;
  gap: 56px;
  padding: 72px 8vw;
}

.grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(circle at center, #000, transparent 72%);
}

.aurora {
  position: absolute;
  width: 360px;
  height: 360px;
  border-radius: 50%;
  filter: blur(50px);
  opacity: 0.45;
  animation: floatY 8s infinite;
}

.a1 { background: #66e7ff; left: 8%; top: 4%; }
.a2 { background: #8a7cff; right: 8%; bottom: 8%; animation-delay: 1s; }

.hero,
.login-card {
  position: relative;
  z-index: 1;
}

.login-card {
  border-radius: 30px;
  padding: 34px;
}

.login-card.is-register {
  border-radius: 24px;
  padding: 28px 30px 24px;
  align-self: center;
}

h2 {
  margin: 0;
  font-size: 28px;
}

.login-card.is-register h2 {
  margin: 0 0 4px;
  font-size: 24px;
  letter-spacing: -0.02em;
}

.subtitle {
  color: var(--muted);
  margin: 0 0 24px;
  line-height: 1.6;
}

.login-card.is-register .subtitle {
  margin: 0 0 18px;
  line-height: 1.5;
  font-size: 13px;
}

.login-card.is-register :deep(.el-form-item) {
  margin-bottom: 14px;
}

.login-card.is-register :deep(.el-form-item__label) {
  margin-bottom: 4px;
  padding-bottom: 0;
  font-weight: 500;
  font-size: 13px;
  line-height: 1.4;
}

.submit {
  width: 100%;
  margin-top: 8px;
}

.login-card.is-register .submit {
  margin-top: 4px;
  height: 38px;
}

.switches {
  display: flex;
  justify-content: center;
  gap: 18px;
  margin-top: 18px;
}

.login-card.is-register .switches {
  gap: 16px;
  margin-top: 16px;
}

.switches button {
  background: transparent;
  border: 0;
  color: var(--brand);
  cursor: pointer;
  font-size: 14px;
}

.login-card.is-register .switches button {
  padding: 4px 0;
}

@media (max-width: 960px) {
  .login-page,
  .login-page.is-register {
    grid-template-columns: 1fr;
    gap: 40px;
    padding: 40px 22px;
  }

  .login-card,
  .login-card.is-register {
    max-width: 520px;
  }

  .login-card.is-register {
    max-width: 400px;
    padding: 26px 24px 22px;
  }
}
</style>

