// centralize mobile auth session persistence and guarded entry behavior; mobile login/register and protected-page gate only; verify with npm run build:mobile:h5
const MOBILE_SESSION_KEY = 'lianleme.mobile.session'
const MOBILE_PREFILL_PHONE_KEY = 'lianleme.mobile.prefill-phone'

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
  clearPrefilledPhone()
}

export const clearMobileSession = () => {
  removeStorage(MOBILE_SESSION_KEY)
}

export const loadPrefilledPhone = () => {
  return readStorage(MOBILE_PREFILL_PHONE_KEY)
}

export const savePrefilledPhone = (phone) => {
  writeStorage(MOBILE_PREFILL_PHONE_KEY, phone.trim())
}

export const clearPrefilledPhone = () => {
  removeStorage(MOBILE_PREFILL_PHONE_KEY)
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
