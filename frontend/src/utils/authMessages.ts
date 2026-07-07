const AUTH_ERROR_MAP: Record<string, string> = {
  '该账号未注册': '该手机号尚未注册，请先创建账号',
  '账号、邮箱或手机号已存在': '该手机号或用户名已被使用，请更换后重试',
  '账号已被禁用': '账号已暂停使用，如有疑问请联系管理员',
  '验证码不存在或已过期，请重新获取': '验证码已失效，请重新获取',
  '验证码错误': '验证码不正确，请核对后重试',
  '重置密码token不存在或已过期，请重新获取': '验证已过期，请返回上一步重新验证',
  '账号不存在': '未找到对应账号，请返回重新验证',
  '用户名不能为空': '请填写用户名',
  '该用户名已被使用': '该用户名已被占用，请换一个试试',
  'No permission to access this resource': '暂无访问权限',
}

export function toAuthUserMessage(
  detail: unknown,
  fallback = '操作未成功，请稍后再试',
): string {
  if (!detail) return fallback
  if (typeof detail === 'string') return mapAuthDetail(detail)
  if (Array.isArray(detail)) {
    const first = detail[0]
    if (first && typeof first === 'object' && 'msg' in first) {
      return mapAuthDetail(String((first as { msg?: string }).msg))
    }
  }
  if (typeof detail === 'object') {
    try {
      return mapAuthDetail(JSON.stringify(detail))
    } catch {
      return fallback
    }
  }
  return fallback
}

function mapAuthDetail(raw: string): string {
  const text = raw.trim()
  if (!text) return '操作未成功，请稍后再试'

  if (AUTH_ERROR_MAP[text]) return AUTH_ERROR_MAP[text]

  const remainMatch = text.match(/账号或密码错误，剩余尝试次数：(\d+)/)
  if (remainMatch) {
    return `手机号或密码不正确，还可尝试 ${remainMatch[1]} 次`
  }

  const lockMatch = text.match(/账号已被锁定，请\s*(\d+)\s*分钟后重试/)
  if (lockMatch) {
    return `为保障账号安全，已暂时锁定，请 ${lockMatch[1]} 分钟后再试`
  }

  const lockFailMatch = text.match(/密码连续错误达到\d+次，账号已锁定(\d+)分钟/)
  if (lockFailMatch) {
    return `多次输入错误，账号已锁定 ${lockFailMatch[1]} 分钟`
  }

  if (text.includes('Network Error') || text.includes('timeout')) {
    return '网络不太稳定，请检查连接后重试'
  }

  if (text.includes('Request failed') || text === '请求失败') {
    return '服务暂时不可用，请稍后再试'
  }

  return text
}

export function codeSentMessage(devCode?: string | null) {
  if (devCode) return '验证码已发送（测试环境已自动填入）'
  return '验证码已发送，请查收短信'
}

export function isAuthRoute(pathname = location.pathname) {
  return /\/(login|find-pwd-1|find-pwd-2)(\/|$)/.test(pathname)
}
