// keep admin login validation and storage rules deterministic; admin auth helpers only; verify with npm --workspace apps/admin-console run test -- adminAuth
import type { AdminLoginDraft, AdminLoginErrors, AdminSession } from '../types/admin'

export interface StorageLike {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
  removeItem: (key: string) => void
}

export interface AdminAuthStorage {
  local: StorageLike
  session: StorageLike
}

export const ADMIN_LOCAL_SESSION_KEY = 'lianleme.admin.session.local'
export const ADMIN_SESSION_SESSION_KEY = 'lianleme.admin.session.session'

const createMemoryBucket = (): StorageLike => {
  const records = new Map<string, string>()

  return {
    getItem: (key) => records.get(key) ?? null,
    setItem: (key, value) => {
      records.set(key, value)
    },
    removeItem: (key) => {
      records.delete(key)
    },
  }
}

const formatDisplayName = (account: string) => {
  const accountAlias = account.split('@')[0]?.trim() || account.trim()
  const normalizedName = accountAlias.replace(/[._-]+/g, ' ').trim()

  if (!normalizedName) {
    return '管理员'
  }

  return normalizedName
    .split(/\s+/)
    .filter(Boolean)
    .map((segment) => {
      if (/[\u4e00-\u9fa5]/.test(segment)) {
        return segment
      }
      return segment.charAt(0).toUpperCase() + segment.slice(1)
    })
    .join(' ')
}

const formatAvatarLabel = (displayName: string, account: string) => {
  const nameParts = displayName
    .split(/\s+/)
    .map((segment) => segment.trim())
    .filter(Boolean)

  if (nameParts.length >= 2) {
    return `${nameParts[0][0] || ''}${nameParts[1][0] || ''}`.toUpperCase()
  }

  const compactSource = displayName.replace(/\s+/g, '') || account.replace(/\s+/g, '')
  return compactSource.slice(0, 2).toUpperCase() || 'AD'
}

const parseStoredSession = (value: string | null): AdminSession | null => {
  if (!value) {
    return null
  }

  try {
    return JSON.parse(value) as AdminSession
  } catch {
    return null
  }
}

export const createMemoryStorage = (): AdminAuthStorage => ({
  local: createMemoryBucket(),
  session: createMemoryBucket(),
})

export const getBrowserAdminStorage = (): AdminAuthStorage => {
  const fallback = createMemoryStorage()

  if (typeof window === 'undefined') {
    return fallback
  }

  return {
    local: window.localStorage,
    session: window.sessionStorage,
  }
}

export const validateAdminLoginDraft = (draft: AdminLoginDraft): AdminLoginErrors => {
  const errors: AdminLoginErrors = {}

  if (!draft.account.trim()) {
    errors.account = '请输入管理员账号'
  }

  if (draft.password.trim().length < 8) {
    errors.password = '密码至少需要 8 位字符'
  }

  return errors
}

export const hasAdminLoginErrors = (errors: AdminLoginErrors) => {
  return Boolean(errors.account || errors.password)
}

export const buildAdminSession = (draft: AdminLoginDraft, loginAt = new Date().toISOString()): AdminSession => {
  const account = draft.account.trim()
  const displayName = formatDisplayName(account)

  return {
    account,
    displayName,
    roleLabel: '系统管理员',
    avatarLabel: formatAvatarLabel(displayName, account),
    loginAt,
    rememberDevice: draft.rememberDevice,
  }
}

export const restoreAdminSession = (storage: AdminAuthStorage = getBrowserAdminStorage()): AdminSession | null => {
  return (
    parseStoredSession(storage.local.getItem(ADMIN_LOCAL_SESSION_KEY)) ??
    parseStoredSession(storage.session.getItem(ADMIN_SESSION_SESSION_KEY))
  )
}

export const persistAdminSession = (
  session: AdminSession,
  rememberDevice: boolean,
  storage: AdminAuthStorage = getBrowserAdminStorage(),
) => {
  clearAdminSession(storage)

  const payload = JSON.stringify({
    ...session,
    rememberDevice,
  })

  if (rememberDevice) {
    storage.local.setItem(ADMIN_LOCAL_SESSION_KEY, payload)
    return
  }

  storage.session.setItem(ADMIN_SESSION_SESSION_KEY, payload)
}

export const clearAdminSession = (storage: AdminAuthStorage = getBrowserAdminStorage()) => {
  storage.local.removeItem(ADMIN_LOCAL_SESSION_KEY)
  storage.session.removeItem(ADMIN_SESSION_SESSION_KEY)
}
