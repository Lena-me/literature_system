<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthHeroPanel from '@/components/auth/AuthHeroPanel.vue'
import { authApi } from '@/api/auth'
import { codeSentMessage } from '@/utils/authMessages'

const router = useRouter()
const loading = ref(false)
const codeLoading = ref(false)

const form = reactive({
  phone: '',
  code: ''
})

const phoneNum = computed(() => form.phone)

async function getCode() {
  if (!phoneNum.value) {
    return ElMessage.warning('请先填写手机号')
  }
  if (!/^1[3-9]\d{9}$/.test(phoneNum.value)) {
    return ElMessage.warning('请填写正确的 11 位手机号')
  }

  codeLoading.value = true
  try {
    const res = await authApi.sendCode(phoneNum.value, 'reset_password')
    if (res.dev_code) {
      form.code = res.dev_code
    }
    ElMessage.success(codeSentMessage(res.dev_code))
  } catch {
    // 错误提示由请求拦截器统一处理
  } finally {
    codeLoading.value = false
  }
}

async function submit() {
  if (!form.phone) {
    return ElMessage.warning('请先填写手机号')
  }
  if (!/^1[3-9]\d{9}$/.test(form.phone)) {
    return ElMessage.warning('请填写正确的 11 位手机号')
  }
  if (!form.code) {
    return ElMessage.warning('请填写短信验证码')
  }

  loading.value = true
  try {
    const res = await authApi.verifyCode(form.phone, 'reset_password', form.code)
    router.push({
      path: '/find-pwd-2',
      query: {
        token: res.token,
        phone: res.phone
      }
    })
  } catch {
    // 错误提示由请求拦截器统一处理
  } finally {
    loading.value = false
  }
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
      <h2>找回密码</h2>
      <p class="subtitle">请输入手机号和验证码</p>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" size="large" placeholder="请输入手机号" />
        </el-form-item>

        <el-form-item label="验证码">
          <el-input v-model="form.code" size="large" placeholder="请输入验证码">
            <template #append>
              <el-button :loading="codeLoading" @click="getCode">获取验证码</el-button>
            </template>
          </el-input>
        </el-form-item>

        <el-button class="submit is-glow" size="large" :loading="loading" @click="submit">
          下一步
        </el-button>
      </el-form>

      <div class="switches">
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

