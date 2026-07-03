import { http } from './client'

/**
 * 后台管理端接口合集
 */
export const adminApi = {
  // ===================== 用户管理模块 =====================
  /**
   * 获取用户列表
   * @param params 筛选参数：keyword 搜索关键词 / status 用户状态 / sort_by 排序字段 / sort_order 排序方向
   */
  users: (params?: { keyword?: string; status?: string; sort_by?: string; sort_order?: string }) =>
    http.get<any, any[]>('/admin/users', { params }),

  /**
   * 新建用户
   * @param payload 用户表单数据
   */
  createUser: (payload: Record<string, any>) =>
    http.post<any, { id: number; message: string }>(
      '/admin/users',
      payload
    ),

  /**
   * 更新用户信息
   * @param id 用户ID
   * @param payload 更新表单数据
   */
  updateUser: (id: number, payload: Record<string, any>) =>
    http.put<any, { message: string }>(`/admin/users/${id}`, payload),

  /**
   * 删除用户
   * @param id 用户ID
   */
  deleteUser: (id: number) =>
    http.delete<any, { message: string }>(`/admin/users/${id}`),

  /**
   * 重置用户密码
   * @param id 用户ID
   * @param new_password 新密码
   */
  resetPassword: (id: number, new_password: string) =>
    http.post<any, { message: string }>(
      `/admin/users/${id}/reset-password`,
      null,
      { params: { new_password } }
    ),

  // ===================== 模型配置模块 =====================
  /**
   * 获取全部模型配置
   */
  models: () => http.get<any, any[]>('/model-configs'),

  /**
   * 保存/新增模型配置
   * @param payload 模型配置表单
   */
  saveModel: (payload: Record<string, any>) =>
    http.post<any, { id: number }>('/model-configs', payload),

  updateModel: (id: number, payload: Record<string, any>) =>
    http.put<any, { message: string }>(`/model-configs/${id}`, payload),

  // ===================== 任务调度模块 =====================
  /**
   * 获取任务列表
   * @param status 任务状态筛选
   */
  tasks: (status?: string) =>
    http.get<any, any[]>('/tasks', { params: { status } }),

  /**
   * 取消任务
   * @param id 任务ID
   */
  cancelTask: (id: number) =>
    http.post<any, { message: string }>(`/tasks/${id}/cancel`),

  /**
   * 重试失败任务
   * @param id 任务ID
   */
  retryTask: (id: number) =>
    http.post<any, { message: string }>(`/tasks/${id}/retry`),

  /**
   * 设置任务优先级
   * @param id 任务ID
   * @param priority 优先级数值
   */
  setTaskPriority: (id: number, priority: number) =>
    http.put<any, { message: string }>(`/tasks/${id}/priority`, { priority }),

  /**
   * 获取任务失败统计数据
   */
  failureStats: () => http.get<any, any>('/tasks/failure-stats'),

  /**
   * 获取调度器配置
   */
  schedulerConfig: () => http.get<any, any>('/tasks/scheduler-config'),

  /**
   * 保存调度器配置
   * @param payload 调度配置表单
   */
  saveSchedulerConfig: (payload: Record<string, any>) =>
    http.put<any, { message: string }>('/tasks/scheduler-config', payload),

  // ===================== 审计日志模块 =====================
  /**
   * 获取操作审计日志
   * @param module 模块筛选
   */
  logs: (module?: string) =>
    http.get<any, any[]>('/audit-logs', { params: { module } }),

  // ===================== 向量库备份模块 =====================
  /**
   * 获取向量库统计信息
   */
  vectorStats: () => http.get<any, any>('/vector-store/stats'),

  /**
   * 获取向量库备份列表
   */
  vectorBackups: () => http.get<any, any[]>('/vector-store/backups'),

  /**
   * 创建向量库备份
   */
  createBackup: () => http.post<any, any>('/vector-store/backups'),

  /**
   * 从备份恢复向量库
   * @param backup_id 备份ID
   */
  restoreBackup: (backup_id: number) =>
    http.post<any, any>('/vector-store/restore', { backup_id }),

  // ===================== 系统监控模块 =====================
  /**
   * 系统健康检查
   */
  systemHealth: () => http.get<any, any>('/system/health'),

  /**
   * 系统操作量统计
   */
  operationStats: () => http.get<any, any>('/system/operation-stats'),

  /**
   * 每日统计数据
   */
  dailyStats: () => http.get<any, any>('/system/daily-stats')
}
