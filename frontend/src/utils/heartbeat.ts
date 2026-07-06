import { authApi } from '@/api/auth'

const HEARTBEAT_INTERVAL = 60 * 1000
const IDLE_TIMEOUT = 60 * 1000

let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let lastActivityTime = Date.now()
let isPageVisible = true

function resetActivityTimer() {
  lastActivityTime = Date.now()
}

function isActive(): boolean {
  return isPageVisible && (Date.now() - lastActivityTime) < IDLE_TIMEOUT
}

async function sendHeartbeat() {
  if (!isActive()) return
  try {
    await authApi.heartbeat()
  } catch {
    // 心跳失败不影响主流程
  }
}

function startHeartbeat() {
  if (heartbeatTimer) return

  resetActivityTimer()

  document.addEventListener('visibilitychange', () => {
    isPageVisible = document.visibilityState === 'visible'
    if (isPageVisible) {
      resetActivityTimer()
      sendHeartbeat()
    }
  })

  document.addEventListener('mousemove', resetActivityTimer)
  document.addEventListener('keydown', resetActivityTimer)
  document.addEventListener('scroll', resetActivityTimer)

  sendHeartbeat()

  heartbeatTimer = setInterval(() => {
    sendHeartbeat()
  }, HEARTBEAT_INTERVAL)
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
  document.removeEventListener('visibilitychange', () => {})
  document.removeEventListener('mousemove', resetActivityTimer)
  document.removeEventListener('keydown', resetActivityTimer)
  document.removeEventListener('scroll', resetActivityTimer)
}

export { startHeartbeat, stopHeartbeat, isActive }
