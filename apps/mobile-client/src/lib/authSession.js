// centralize mobile email-session persistence and guarded entry behavior; mobile login/register and protected-page gate only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`.
const MOBILE_SESSION_KEY = 'lianleme.mobile.session'

const canUseUniStorage = () => {
  return typeof uni !== 'undefined' && typeof uni.getStorageSync === 'function'
}

const readStorage = (key) => {
  if (canUseUniStorage()) {
    return uni.getStorageSync(key) || ''
  }

  if (typeof window !== 'undefined' && window.localStorage) {
    return window.localStorage.getItem(key) || ''
  }

  return ''
}

const writeStorage = (key, value) => {
  if (canUseUniStorage()) {
    uni.setStorageSync(key, value)
    return
  }

  if (typeof window !== 'undefined' && window.localStorage) {
    window.localStorage.setItem(key, value)
  }
}

const removeStorage = (key) => {
  if (canUseUniStorage()) {
    uni.removeStorageSync(key)
    return
  }

  if (typeof window !== 'undefined' && window.localStorage) {
    window.localStorage.removeItem(key)
  }
}

export const loadMobileSession = () => {
  const rawValue = readStorage(MOBILE_SESSION_KEY)

  if (!rawValue) {
    return null
  }

  try {
    return JSON.parse(rawValue)
  } catch {
    removeStorage(MOBILE_SESSION_KEY)
    return null
  }
}

export const saveMobileSession = (session) => {
  writeStorage(MOBILE_SESSION_KEY, JSON.stringify(session))
}

export const clearMobileSession = () => {
  removeStorage(MOBILE_SESSION_KEY)
}

export const getMobileAuthHeaders = () => {
  const session = loadMobileSession()
  const headers = {}

  if (session?.accessToken) {
    headers.Authorization = `Bearer ${session.accessToken}`
  }

  if (session?.userId) {
    headers['x-user-id'] = session.userId
  }

  return headers
}

export const redirectToMobileLogin = () => {
  if (typeof uni !== 'undefined' && typeof uni.reLaunch === 'function') {
    uni.reLaunch({ url: '/pages/auth/login' })
  }
}

export const requireMobileAuth = () => {
  const session = loadMobileSession()

  if (session?.userId) {
    return session
  }

  if (typeof window === 'undefined') {
    redirectToMobileLogin()
  }

  return null
}
