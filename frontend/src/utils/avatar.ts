import { API_PREFIX } from '@/api/client'
import type { User } from '@/types/domain'

export function resolveAvatarUrl(user?: Pick<User, 'avatar_url'> | null, cacheBust?: number | string) {
  const raw = user?.avatar_url?.trim()
  if (!raw) return ''

  let base: string
  if (raw.startsWith('http')) {
    base = raw
  } else if (raw.startsWith(API_PREFIX)) {
    base = raw
  } else {
    base = `${API_PREFIX}${raw.startsWith('/') ? raw : `/${raw}`}`
  }

  if (cacheBust === undefined || cacheBust === null || cacheBust === '') return base
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}t=${cacheBust}`
}
