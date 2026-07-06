import { http } from './client'

/** 后台管理端接口合集 */
export const adminApi = {
  // ===================== 运维总览 =====================
  overview: () => http.get<any, any>('/admin/overview'),

  systemPauseState: () => http.get<any, { paused: boolean }>('/admin/system/pause'),

  setSystemPause: (paused: boolean) =>
    http.post<any, { paused: boolean; message: string }>('/admin/system/pause', { paused }),

  // ===================== 用户管理模块 =====================
  users: (params?: { keyword?: string; status?: string; sort_by?: string; sort_order?: string }) =>
    http.get<any, any[]>('/admin/users', { params }),

  userDetail: (id: number) => http.get<any, any>(`/admin/users/${id}/detail`),

  createUser: (payload: Record<string, any>) =>
    http.post<any, { id: number; message: string }>('/admin/users', payload),

  updateUser: (id: number, payload: Record<string, any>) =>
    http.put<any, { message: string }>(`/admin/users/${id}`, payload),

  deleteUser: (id: number) => http.delete<any, { message: string }>(`/admin/users/${id}`),

  resetPassword: (id: number, new_password: string) =>
    http.post<any, { message: string }>(`/admin/users/${id}/reset-password`, null, {
      params: { new_password },
    }),

  // ===================== 模型配置模块 =====================
  models: () => http.get<any, any[]>('/model-configs'),

  modelsMonitor: () => http.get<any, any>('/admin/models/monitor'),

  modelScenarios: () => http.get<any, Array<{ id: string; name: string }>>('/admin/models/scenarios'),

  saveModel: (payload: Record<string, any>) => http.post<any, { id: number }>('/model-configs', payload),

  updateModel: (id: number, payload: Record<string, any>) =>
    http.put<any, { message: string }>(`/model-configs/${id}`, payload),

  activeLlmRuntime: () => http.get<any, any>('/model-configs/active-llm'),

  modelDetail: (id: number) => http.get<any, any>(`/model-configs/${id}/detail`),

  // ===================== 任务调度模块 =====================
  tasks: (params?: { page?: number; page_size?: number; status?: string }) =>
    http.get<any, { items: any[]; total: number; page: number; page_size: number }>('/admin/tasks', {
      params,
    }),

  batchRetryTasks: (task_ids: number[]) =>
    http.post<any, { retried_task_ids: number[] }>('/admin/tasks/batch-retry', { task_ids }),

  batchCancelTasks: (task_ids: number[]) =>
    http.post<any, { cancelled_task_ids: number[] }>('/admin/tasks/batch-cancel', { task_ids }),

  cancelTask: (id: number) => http.post<any, { message: string }>(`/tasks/${id}/cancel`),

  retryTask: (id: number) => http.post<any, { message: string }>(`/tasks/${id}/retry`),

  setTaskPriority: (id: number, priority: number) =>
    http.put<any, { message: string }>(`/tasks/${id}/priority`, { priority }),

  failureStats: () => http.get<any, any>('/tasks/failure-stats'),

  schedulerConfig: () => http.get<any, any>('/tasks/scheduler-config'),

  saveSchedulerConfig: (payload: Record<string, any>) =>
    http.put<any, { message: string }>('/tasks/scheduler-config', payload),

  // ===================== 审计日志模块 =====================
  logs: (module?: string) => http.get<any, any[]>('/audit-logs', { params: { module } }),

  // ===================== 向量库备份模块 =====================
  vectorStats: () => http.get<any, any>('/vector-store/stats'),

  vectorBackups: () => http.get<any, any[]>('/vector-store/backups'),

  createBackup: () => http.post<any, any>('/vector-store/backups'),

  restoreBackup: (backup_id: number) => http.post<any, any>('/vector-store/restore', { backup_id }),

  // ===================== 系统监控模块（兼容） =====================
  systemHealth: () => http.get<any, any>('/system/health'),

  operationStats: () => http.get<any, any>('/system/operation-stats'),

  dailyStats: () => http.get<any, any>('/system/daily-stats'),
}
