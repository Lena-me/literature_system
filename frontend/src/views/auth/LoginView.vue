<script setup lang="ts">

import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import BrandMark from '@/components/common/BrandMark.vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'


const router = useRouter();
const auth = useAuthStore();
const mode = ref<'login'|'register'|'reset'>('login')
const form = reactive({
  account: 'admin',
  username: '',
  password: 'admin123456',
  confirm_password: '',
  name: '',
  email: '',
  phone: '',
  code: ''
})
// 根据 mode 切换标题
const title = computed(() => {
  if(mode.value === 'login'){
    return '登录科研知识平台'
  }
  else if(mode.value === 'register'){
    return '创建科研账户'
  }
  else {
    return '重置密码'
  }
})

// 验证码机制，根据手机号获取验证码
const codeAccount = computed(() => {return form.phone})

// 获取验证码
async function getCode() {
  if (!codeAccount.value) {
    return ElMessage.warning('请先填写手机号')
  }
  let scene: 'register' | 'reset_password'
  if (mode.value === 'reset'){
    scene = 'reset_password'
  }
  else {
    scene = 'register'
  }
  // 调用发送短信接口
  const res = await authApi.sendCode(codeAccount.value, scene)
  if (res.dev_code) {
    form.code = res.dev_code
  }
  ElMessage.success(res.dev_code ? `验证码已生成：${res.dev_code}` : res.message)
}


async function submit() {
  // 登录功能
  if (mode.value === 'login') {
    const user = await auth.login(form.phone, form.password)
    router.push(user.role === 'admin' ? '/admin' : '/research')
  }

  // 注册功能
  else if (mode.value === 'register') {
    if (form.password !== form.confirm_password) return ElMessage.warning('两次密码不一致')
    if (!form.code) return ElMessage.warning('请输入验证码')
    const user = await auth.register({
      username: form.username,
      password: form.password,
      confirm_password: form.confirm_password,
      email: form.email,
      phone: form.phone,
      code: form.code
    })
    router.push(user.role === 'admin' ? '/admin' : '/research')
  }

  // 修改密码功能
  else {
    if (!form.code) {
      return ElMessage.warning('请输入验证码')
    }
    await authApi.resetPassword({
      phone: form.phone,
      password: form.password,
      confirm_password: form.confirm_password,
      code: form.code
    })
    ElMessage.success('密码已重置，请重新登录');
    mode.value = 'login'
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
      <h2>{{ title }}</h2>
      <!-- 注意删除 -->
      <p class="subtitle">默认管理员：13800138000 / admin123456</p >

      <el-form label-position="top" @submit.prevent>
        <!-- 只有登录和重置密码显示这个 -->
        <el-form-item v-if="mode !== 'register'" label="手机号">
          <el-input v-model="form.phone" size="large"/>
        </el-form-item>

        <!-- 注册表单 -->
        <template v-if="mode === 'register'">
          <el-form-item label="用户名">
            <el-input v-model="form.username" size="large"/>
          </el-form-item>

          <el-form-item label="邮箱">
            <el-input v-model="form.email" size="large"/>
          </el-form-item>

          <el-form-item label="手机号">
            <el-input v-model="form.phone" size="large"/>
          </el-form-item>
        </template>

        <el-form-item label="密码">
          <el-input v-model="form.password" size="large" show-password/>
        </el-form-item>

        <el-form-item v-if="mode !== 'login'" label="确认密码">
          <el-input v-model="form.confirm_password" size="large" show-password/>
        </el-form-item>

        <el-form-item v-if="mode !== 'login'" label="验证码">
          <el-input v-model="form.code" size="large">
            <template #append>
              <el-button @click="getCode">获取验证码</el-button>
            </template>
          </el-input>
        </el-form-item>

        <el-button class="submit is-glow" size="large" :loading="auth.loading" @click="submit">
          {{ mode === 'login' ? '登录' : mode === 'register' ? '注册并进入' : '重置密码' }}
        </el-button>
      </el-form>

      <!-- 底部按钮 -->
      <div class="switches">
        <button v-if="mode !== 'login'" @click="mode='login'">登录</button>
        <button v-if="mode !== 'register'" @click="mode='register'">注册</button>
        <button v-if="mode !== 'reset'" @click="mode='reset'">忘记密码</button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page { position:relative; overflow:hidden; display:grid; grid-template-columns: 1.1fr 460px; gap: 48px; align-items:center; padding: 70px 8vw; }
.grid { position:absolute; inset:0; background-image: linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px); background-size: 48px 48px; mask-image: radial-gradient(circle at center, #000, transparent 72%); }
.aurora { position:absolute; width:360px; height:360px; border-radius:50%; filter: blur(50px); opacity:.45; animation: floatY 8s infinite; }.a1{background:#66e7ff; left:8%; top:4%}.a2{background:#8a7cff; right:8%; bottom:8%; animation-delay:1s}.hero,.login-card{position:relative;z-index:1}.hero h1{font-size:62px;line-height:1.05;max-width:860px;margin:34px 0 18px;letter-spacing:-2px}.hero p{color:rgba(238,246,255,.72);font-size:18px;max-width:720px;line-height:1.9}.hero-cards{display:flex;gap:16px;margin-top:34px}.hero-cards div{padding:18px 22px;border-radius:20px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)}.hero-cards b{font-size:24px;display:block}.hero-cards span{color:var(--muted);font-size:13px}.login-card{border-radius:30px;padding:34px}h2{margin:0;font-size:28px}.subtitle{color:var(--muted);margin-bottom:24px}.submit{width:100%;margin-top:8px}.switches{display:flex;justify-content:center;gap:18px;margin-top:18px}.switches button{background:transparent;border:0;color:var(--brand);cursor:pointer}@media (max-width: 960px){.login-page{grid-template-columns:1fr;padding:40px 22px}.hero h1{font-size:42px}.login-card{max-width:520px}}
</style>