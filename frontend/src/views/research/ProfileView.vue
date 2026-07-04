<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/papers'
import { featuresApi } from '@/api/features'
import { authApi } from '@/api/auth'

const router = useRouter()
const auth = useAuthStore()
const store = usePaperStore()
const user = auth.user!

const paperCount = ref(0)
const completedCount = ref(0)
const learningOverview = ref<any>(null)

const showPhoneModal = ref(false)
const showEmailModal = ref(false)
const showUsernameModal = ref(false)
const editUsername = ref('')

const usernameError = ref('')

function validateUsername() {
  const name = editUsername.value.trim()
  if (!name) {
    usernameError.value = '请输入用户名'
    return false
  }
  if (name.length < 2) {
    usernameError.value = '用户名至少需要2个字符'
    return false
  }
  if (name.length > 20) {
    usernameError.value = '用户名最多20个字符'
    return false
  }
  usernameError.value = ''
  return true
}

function maskPhone(phone: string): string {
  if (!phone || phone.length < 7) return phone
  return phone.slice(0, 3) + '****' + phone.slice(-4)
}

async function updateUsername() {
  if (!validateUsername()) return
  const newName = editUsername.value.trim()
  try {
    await authApi.updateProfile({ username: newName })
    auth.user!.username = newName
    showUsernameModal.value = false
    editUsername.value = ''
    usernameError.value = ''
  } catch (error: any) {
    usernameError.value = error.response?.data?.detail || '修改失败'
  }
}

onMounted(async () => {
  await store.load()
  paperCount.value = store.list.length
  completedCount.value = store.list.filter(p => p.parse_status === 'completed').length

  try {
    learningOverview.value = await featuresApi.overview()
  } catch { /* ignore */ }
})

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="profile-page slim-scroll">
    <div class="profile-card">
      <div class="avatar-circle">{{ user.username?.slice(0, 1)?.toUpperCase() }}</div>
      <div class="profile-info">
        <h2>{{ user.name || user.username }}</h2>
        <div class="meta-row">
          <span v-if="user.email">{{ user.email }}</span>
          <span v-if="user.phone">{{ maskPhone(user.phone) }}</span>
          <span>注册时间 {{ user.created_at ? new Date(user.created_at).toLocaleDateString('zh-CN') : '-' }}</span>
        </div>
      </div>
      <button class="logout-btn" @click="logout">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        退出登录
      </button>
    </div>

    <div class="section">
      <h3>学习概览</h3>
    </div>

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

    <div v-if="learningOverview" class="section">
      <div class="overview-grid">
        <div class="kv"><span>连续学习</span><b>{{ learningOverview.streak_days || 0 }} 天</b></div>
        <div class="kv"><span>累计时长</span><b>{{ learningOverview.total_minutes || 0 }} 分钟</b></div>
      </div>
    </div>

    <div class="section">
      <h3>帐号信息</h3>
      <div class="info-list">
        <div class="info-row">
          <span>用户名</span>
          <div class="info-right">
            <b>{{ user.username }}</b>
            <button class="edit-btn" @click="editUsername = user.username; showUsernameModal = true" title="编辑用户名">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
            </button>
          </div>
        </div>
        <div class="info-row">
          <span>邮箱</span>
          <div class="info-right">
            <b>{{ user.email || '未设置' }}</b>
            <button class="arrow-btn" @click="showEmailModal = true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
        </div>
        <div class="info-row">
          <span>手机</span>
          <div class="info-right">
            <b>{{ user.phone ? maskPhone(user.phone) : '未设置' }}</b>
            <button class="arrow-btn" @click="showPhoneModal = true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showPhoneModal" class="modal-overlay" @click="showPhoneModal = false">
        <div class="modal-content" @click.stop>
          <h4>手机号码</h4>
          <p>{{ maskPhone(user.phone || '') }}</p>
          <button class="modal-close" @click="showPhoneModal = false">关闭</button>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showEmailModal" class="modal-overlay" @click="showEmailModal = false">
        <div class="modal-content" @click.stop>
          <h4>邮箱</h4>
          <p>{{ user.email || '未设置' }}</p>
          <button class="modal-close" @click="showEmailModal = false">关闭</button>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showUsernameModal" class="modal-overlay" @click="showUsernameModal = false">
        <div class="modal-content" @click.stop>
          <h4>编辑用户名</h4>
          <input v-model="editUsername" type="text" class="modal-input" placeholder="请输入用户名" maxlength="20" @input="validateUsername" />
          <span v-if="usernameError" class="modal-error">{{ usernameError }}</span>
          <div class="modal-actions">
            <button class="modal-cancel" @click="showUsernameModal = false">取消</button>
            <button class="modal-confirm" @click="updateUsername">确认</button>
          </div>
        </div>
      </div>
    </Teleport>
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
  align-items: center;
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

.info-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-right b {
  font-size: 13px;
  color: var(--academic-text-body);
  font-weight: 500;
}

.edit-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.edit-btn:hover {
  color: var(--academic-primary);
  background: var(--academic-primary-light);
}

.arrow-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--academic-text-muted);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.arrow-btn:hover {
  color: var(--academic-primary);
  background: var(--academic-primary-light);
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  min-width: 280px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
}

.modal-content h4 {
  margin: 0 0 16px;
  font-size: 16px;
  color: var(--academic-text-main);
}

.modal-content p {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--academic-text-body);
}

.modal-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  font-size: 14px;
  margin-bottom: 8px;
  box-sizing: border-box;
}

.modal-error {
  display: block;
  color: #ef4444;
  font-size: 12px;
  margin-bottom: 16px;
}

.modal-input:focus {
  outline: none;
  border-color: var(--academic-primary);
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.modal-close, .modal-cancel {
  padding: 8px 16px;
  border: 1px solid var(--academic-border);
  border-radius: 8px;
  background: #fff;
  color: var(--academic-text-body);
  font-size: 13px;
  cursor: pointer;
}

.modal-close:hover, .modal-cancel:hover {
  background: var(--academic-canvas);
}

.modal-confirm {
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: var(--academic-primary);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.modal-confirm:hover {
  background: var(--academic-primary-hover);
}
</style>