<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api/auth';

const router = useRouter();
const loading = ref(false)
const codeLoading = ref(false)

const form = reactive({
  'phone': '',
  'code': ''
})

// 手机号
const phoneNum = computed(() => form.phone)

// 发送验证码
async function getCode(){
    if(!phoneNum.value){
        return ElMessage.error('请输入手机号')
    }
    // 验证手机号格式
    if (!/^1[3-9]\d{9}$/.test(phoneNum.value)) {
        return ElMessage.error('请输入有效的手机号')
    }

    // 调用发送短信接口
    const res = await authApi.sendCode(phoneNum.value, 'reset_password')
    if (res.dev_code){
        form.code = res.dev_code
    }
    ElMessage.success(res.dev_code ? `验证码已生成：${res.dev_code}` : res.message)
}

// 验证验证码并跳转
async function submit(){
    // 验证完整性
    if (!form.phone){
        return ElMessage.error('请输入手机号')
    }
    if (!form.code){
        return ElMessage.error('请输入验证码')
    }

    loading.value = true
    try {
        // 后端验证验证码，获取重置token并传给第二步

        // 验证验证码
        const res = await authApi.verifyCode(form.phone, 'reset_password', form.code)
        // 验证成功，跳转到第二步
        router.push({
            path: '/find-pwd-2',
            query: {
                token: res.token,
                phone: res.phone
            }
        })
    }
    catch (error: any){
        ElMessage.error(error.response?.data?.detail || '验证码验证失败')
    }
    finally {
        loading.value = false
    }
}

// 返回登录页面
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
      <h2>重置密码 - 第一步</h2>
      <p class="subtitle">请输入您的手机号并验证身份</p>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" size="large" placeholder="请输入手机号"/>
        </el-form-item>

        <el-form-item label="验证码">
          <el-input v-model="form.code" size="large" placeholder="请输入验证码">
            <template #append>
              <el-button :loading="codeLoading" @click="getCode">获取验证码</el-button>
            </template>
          </el-input>
        </el-form-item>

        <el-button class="submit is-glow" size="large" :loading="loading" @click="submit">
          验证并继续
        </el-button>
      </el-form>

      <!-- 底部按钮 -->
      <div class="switches">
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