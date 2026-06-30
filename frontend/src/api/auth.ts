import { http } from './client'
import type { TokenOut, User } from '@/types/domain'
export const authApi = {
  
  sendCode: (
      phone: string,
      purpose: 'register' | 'reset_password'
  ) => http.post<any, { message: string; dev_code?: string }>('/auth/verification-code', { phone, purpose }),

  // 验证验证码并获取重置token
  verifyCode:(
    phone: string,
    purpose: 'register' | 'reset_password',
    code: string
  ) => http.post<any, { token: string; phone: string }>('/auth/verify-code', { phone, purpose, code }),

  login: (
      phone: string, password: string
  ) => http.post<any, TokenOut>('/auth/login', { phone, password }),

  // 注册功能
  register: (
      payload: {
          username: string;
          password: string;
          confirm_password: string;
          email?: string;
          phone?: string;
          code: string
      }) => http.post<any, TokenOut>('/auth/register', {
        username: payload.username,
        password: payload.password,
        confirm_password: payload.password,
        email: payload.email,
        phone: payload.phone,
        code: payload.code
      }),

  // 重置密码功能
  resetPassword: (
      payload: {
        token: string;
        password: string;
        confirm_password: string;
      }) => http.post('/auth/reset-password', {
        token: payload.token,
        password: payload.password,
        confirm_password: payload.confirm_password,
      }),

  // 获取用户信息
  me: () => http.get<any, User>('/users/me')
}