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
        confirm_password: payload.confirm_password,
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
  me: () => http.get<any, User>('/users/me'),

  // 更新用户信息
  updateProfile: (payload: { username: string }) => http.put('/auth/profile', payload),

  uploadAvatar: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<any, { message: string; avatar_url: string }>('/users/me/avatar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  deleteAvatar: () => http.delete<any, { message: string }>('/users/me/avatar'),

  // 修改密码
  changePassword: (payload: { old_password: string; new_password: string }) => http.put('/auth/change-password', payload),

  heartbeat: () => http.post('/users/heartbeat'),

  getLearningDuration: (period: string = 'today') => http.get<any, { period: string; minutes: number }>(`/users/learning-duration?period=${period}`),

  getAllLearningDuration: () => http.get<any, { today: number; week: number; month: number; year: number; total: number }>('/users/learning-duration/all'),
}