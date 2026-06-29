import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import type { User } from '@/types/domain'

export const useAuthStore = defineStore('auth', {
  state: () => ({ token: localStorage.getItem('access_token') || '', user: null as User | null, loading: false }),
  getters: { isAuthed: s => Boolean(s.token), isAdmin: s => s.user?.role === 'admin' },
  actions: {
    async login(account: string, password: string) {
      this.loading = true
      try {
        const res = await authApi.login(account, password)
        this.token = res.access_token; this.user = res.user
        localStorage.setItem('access_token', res.access_token)
        return res.user
      } finally { this.loading = false }
    },
    async register(
        payload: {
          username: string;
          password: string;
          confirm_password: string;
          email?: string;
          phone?: string;
          code: string
        })
    {
      const res = await authApi.register(payload)
      this.token = res.access_token; this.user = res.user
      localStorage.setItem('access_token', res.access_token)
      return res.user
    },
    async loadMe() {
      if (!this.token) return null
      this.user = await authApi.me()
      return this.user
    },
    logout() { this.token = ''; this.user = null; localStorage.removeItem('access_token') }
  }
})