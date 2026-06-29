import { http } from './client'
export const adminApi = {
  users: (params?: { keyword?: string; status?: string }) => http.get<any, any[]>('/admin/users', { params }),
  createUser: (payload: Record<string, any>) => http.post<any, { id: number; message: string }>('/admin/users', payload),
  updateUser: (id: number, payload: Record<string, any>) => http.put<any, { message: string }>(`/admin/users/${id}`, payload),
  deleteUser: (id: number) => http.delete<any, { message: string }>(`/admin/users/${id}`),
  resetPassword: (id: number, new_password: string) => http.post<any, { message: string }>(`/admin/users/${id}/reset-password`, null, { params: { new_password } }),
  models: () => http.get<any, any[]>('/model-configs'),
  saveModel: (payload: Record<string, any>) => http.post<any, { id: number }>('/model-configs', payload),
  tasks: (status?: string) => http.get<any, any[]>('/tasks', { params: { status } }),
  cancelTask: (id: number) => http.post<any, { message: string }>(`/tasks/${id}/cancel`),
  retryTask: (id: number) => http.post<any, { message: string }>(`/tasks/${id}/retry`),
  setTaskPriority: (id: number, priority: number) => http.put<any, { message: string }>(`/tasks/${id}/priority`, { priority }),
  failureStats: () => http.get<any, any>('/tasks/failure-stats'),
  schedulerConfig: () => http.get<any, any>('/tasks/scheduler-config'),
  saveSchedulerConfig: (payload: Record<string, any>) => http.put<any, { message: string }>('/tasks/scheduler-config', payload),
  logs: (module?: string) => http.get<any, any[]>('/audit-logs', { params: { module } }),
  vectorStats: () => http.get<any, any>('/vector-store/stats'),
  vectorBackups: () => http.get<any, any[]>('/vector-store/backups'),
  createBackup: () => http.post<any, any>('/vector-store/backups'),
  restoreBackup: (backup_id: number) => http.post<any, any>('/vector-store/restore', { backup_id }),
  systemHealth: () => http.get<any, any>('/system/health'),
  operationStats: () => http.get<any, any>('/system/operation-stats')
}
