import { authApi } from '@/api/auth'

const HEARTBEAT_INTERVAL_MS = 60_000

let timer: ReturnType<typeof setInterval> | null = null

function tick() {
  if (!localStorage.getItem('access_token')) return
  authApi.heartbeat().catch(() => {})
}

export function startHeartbeat(intervalMs = HEARTBEAT_INTERVAL_MS) {
  stopHeartbeat()
  tick()
  timer = setInterval(tick, intervalMs)
}

export function stopHeartbeat() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
