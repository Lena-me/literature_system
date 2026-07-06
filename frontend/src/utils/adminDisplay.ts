/** 管理后台：面向业务的展示文案，避免暴露数据库主键等底层字段 */

export function tableRowIndex(page: number, pageSize: number, index: number) {
  return (page - 1) * pageSize + index + 1
}

export const auditModuleLabels: Record<string, string> = {
  auth: '账号',
  papers: '文献',
  qa: '问答',
  reports: '报告',
}

export const auditActionLabels: Record<string, string> = {
  login: '登录',
  login_failed: '登录失败',
  register: '注册',
  reset_password: '重置密码',
  update_profile: '修改资料',
  upload: '上传',
  delete: '删除',
  reparse: '重新解析',
  ask: '提问',
  ask_stream: '流式提问',
  generate: '生成报告',
}

export function formatAuditModule(value?: string) {
  return (value && auditModuleLabels[value]) || value || '—'
}

export function formatAuditAction(value?: string) {
  return (value && auditActionLabels[value]) || value || '—'
}

export function formatAuditSummary(
  module?: string,
  operationType?: string,
  raw?: string | null,
  json?: unknown,
) {
  if (json && typeof json === 'object') {
    const data = json as Record<string, unknown>
    if (module === 'papers') {
      if (operationType === 'upload' && typeof data.file_size === 'number') {
        const kb = Math.floor(data.file_size / 1024)
        return kb > 0 ? `上传文献（约 ${kb} KB）` : '上传文献'
      }
      if (operationType === 'upload') return '上传文献'
      if (operationType === 'delete') return '删除文献'
      if (operationType === 'reparse') return '重新解析文献'
    }
    if (module === 'qa') {
      const count = Array.isArray(data.paper_ids) ? data.paper_ids.length : 0
      if (operationType === 'ask_stream') {
        return count ? `发起流式问答（${count} 篇文献）` : '发起流式问答'
      }
      if (operationType === 'ask') {
        return count ? `发起问答（${count} 篇文献）` : '发起问答'
      }
    }
    if (module === 'reports') {
      if (operationType === 'generate') return '生成研读报告'
      if (operationType === 'delete') return '删除报告'
    }
    if (module === 'auth') {
      const authLabels: Record<string, string> = {
        login: '登录成功',
        login_failed: '登录失败',
        register: '注册账号',
        reset_password: '重置密码',
        update_profile: '修改个人资料',
      }
      if (operationType && authLabels[operationType]) return authLabels[operationType]
    }
  }
  const moduleLabel = formatAuditModule(module)
  const actionLabel = formatAuditAction(operationType)
  if (actionLabel && actionLabel !== '—' && actionLabel !== moduleLabel) {
    return `${moduleLabel} · ${actionLabel}`
  }
  return moduleLabel !== '—' ? moduleLabel : raw || '—'
}

/** @deprecated 使用 formatAuditSummary；保留兼容旧字段 */
export function formatAuditContent(raw?: string | null, json?: unknown, module?: string, operationType?: string) {
  if (module || operationType) {
    return formatAuditSummary(module, operationType, raw, json)
  }
  if (json && typeof json === 'object') {
    return formatAuditSummary(undefined, undefined, raw, json)
  }
  const text = raw || ''
  if (text.startsWith('{') || text.startsWith('[')) {
    try {
      return formatAuditSummary(undefined, undefined, raw, JSON.parse(text))
    } catch {
      /* ignore */
    }
  }
  return '—'
}

export const taskStatusLabels: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  running: '执行中',
  queued: '排队中',
  cancelled: '已终止',
}

export const taskTypeLabels: Record<string, string> = {
  document_parse: '文献解析',
}

export function formatTaskStatus(value?: string) {
  return (value && taskStatusLabels[value]) || value || '—'
}

export function formatTaskType(value?: string) {
  return (value && taskTypeLabels[value]) || value || '解析任务'
}

export function formatDateTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

export function formatUserDisplayName(user?: { username?: string; name?: string; phone?: string | null }) {
  if (!user) return '未知用户'
  return user.username || user.name || user.phone || '未知用户'
}

/** 解析管理端脱敏后的错误日志，用于卡片展示 */
export function parseAdminErrorLog(text?: string | null): { type: string; detail: string } {
  const raw = (text || '').trim()
  if (!raw) return { type: 'UnknownError', detail: '暂无错误详情' }

  const lines = raw.split('\n').map(l => l.trim()).filter(Boolean)
  const head = lines[0]
  const match = head.match(/^([A-Za-z_][\w.]*(?:Error|Exception))(?::\s*(.*))?$/)
  if (match) {
    const tail = match[2]?.trim() || lines.slice(1).join('\n')
    return { type: match[1], detail: tail || '—' }
  }
  return { type: 'Error', detail: raw }
}
