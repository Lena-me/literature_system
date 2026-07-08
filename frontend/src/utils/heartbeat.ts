import { authApi } from '@/api/auth'

const HEARTBEAT_INTERVAL = 60 * 1000
const IDLE_TIMEOUT = 3 * 60 * 1000
const LEADER_KEY = 'heartbeat_leader'
const LEADER_TIMEOUT = 90 * 1000

let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let lastActivityTime = Date.now()
let isPageVisible = true
let isLeader = false
let leaderCheckTimer: ReturnType<typeof setInterval> | null = null

function resetActivityTimer() {
  lastActivityTime = Date.now()
}

function isActive(): boolean {
  return isPageVisible && (Date.now() - lastActivityTime) < IDLE_TIMEOUT
}

function tryBecomeLeader(): boolean {
  const now = Date.now()
  const leaderData = localStorage.getItem(LEADER_KEY)
  if (leaderData) {
    try {
      const { tabId, timestamp } = JSON.parse(leaderData)
      if (tabId && now - timestamp < LEADER_TIMEOUT) {
        if (tabId === getCurrentTabId()) {
          return true
        }
        return false
      }
    } catch {
      // ignore
    }
  }
  const tabId = getCurrentTabId()
  localStorage.setItem(LEADER_KEY, JSON.stringify({ tabId, timestamp: now }))
  return true
}

function getCurrentTabId(): string {
  let tabId = sessionStorage.getItem('heartbeat_tab_id')
  if (!tabId) {
    tabId = Math.random().toString(36).slice(2, 10)
    sessionStorage.setItem('heartbeat_tab_id', tabId)
  }
  return tabId
}

function renewLeadership() {
  const tabId = getCurrentTabId()
  localStorage.setItem(LEADER_KEY, JSON.stringify({ tabId, timestamp: Date.now() }))
}

function checkLeadership() {
  if (isLeader) {
    renewLeadership()
  } else {
    isLeader = tryBecomeLeader()
  }
}

async function sendHeartbeat() {
  if (!isActive()) return
  if (!isLeader) return
  try {
    await authApi.heartbeat()
  } catch (error: any) {
    const status = error?.response?.status
    if (status === 401) {
      stopHeartbeat()
    }
  }
}

function startHeartbeat() {
  if (heartbeatTimer) return

  resetActivityTimer()
  isLeader = tryBecomeLeader()

  document.addEventListener('visibilitychange', () => {
    isPageVisible = document.visibilityState === 'visible'
    if (isPageVisible) {
      resetActivityTimer()
      isLeader = tryBecomeLeader()
      sendHeartbeat()
    }
  })

  document.addEventListener('mousemove', resetActivityTimer)
  document.addEventListener('keydown', resetActivityTimer)
  document.addEventListener('scroll', resetActivityTimer)

  leaderCheckTimer = setInterval(() => {
    checkLeadership()
  }, 30 * 1000)

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
  if (leaderCheckTimer) {
    clearInterval(leaderCheckTimer)
    leaderCheckTimer = null
  }
  document.removeEventListener('visibilitychange', () => {})
  document.removeEventListener('mousemove', resetActivityTimer)
  document.removeEventListener('keydown', resetActivityTimer)
  document.removeEventListener('scroll', resetActivityTimer)
  if (isLeader) {
    localStorage.removeItem(LEADER_KEY)
  }
}

export { startHeartbeat, stopHeartbeat, isActive }
