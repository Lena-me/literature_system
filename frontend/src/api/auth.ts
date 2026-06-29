import { http } from './client'
import type { TokenOut, User } from '@/types/domain'
export const authApi = {
  sendCode: (account: string, purpose: 'register' | 'reset_password') => http.post<any, { message: string; dev_code?: string }>('/auth/verification-code', { account, purpose }),
  login: (account: string, password: string) => http.post<any, TokenOut>('/auth/login', { account, password }),
  register: (payload: { username: string; password: string; name?: string; email?: string; phone?: string; verification_code: string }) => http.post<any, TokenOut>('/auth/register', payload),
  resetPassword: (payload: { account: string; new_password: string; verification_code: string }) => http.post('/auth/reset-password', payload),
  me: () => http.get<any, User>('/users/me')
}
