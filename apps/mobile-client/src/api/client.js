// Why: prefer fetch in H5 browser runtime because uni.request can fail in web preview with non-descriptive errors.
// Scope: mobile-client API helper behavior for GET/POST requests.
// Verify: workout home fetches /v1/home/workout and no longer falls back to request-failed message.
import { getMobileAuthHeaders } from '../lib/authSession'

const API_PREFIX = '/v1'
const MINI_PROGRAM_DIRECT_API_ORIGIN = 'http://127.0.0.1:18000'

const normalizeOrigin = (value) => {
  return typeof value === 'string' ? value.trim().replace(/\/+$/, '') : ''
}

const resolveApiOrigin = () => {
  if (typeof window !== 'undefined') {
    return window.location.origin
  }

  // keep mini-program requests off the H5 preview proxy so login and tab data load in wx devtools without depending on localhost:5273; non-browser mobile runtime only; verify with `node tests/e2e/mobile_mp_auth_contract.mjs` plus mp-weixin login.
  return normalizeOrigin(globalThis?.__LIANLEME_API_ORIGIN__) || MINI_PROGRAM_DIRECT_API_ORIGIN
}

const buildUrl = (path) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const origin = resolveApiOrigin()
  return `${origin}${API_PREFIX}${normalizedPath}`
}

const isBrowserFetchAvailable = () => {
  return typeof window !== 'undefined' && typeof fetch === 'function'
}

export const apiGet = async (path) => {
  const url = buildUrl(path)
  const headers = getMobileAuthHeaders()

  if (isBrowserFetchAvailable()) {
    const response = await fetch(url, { headers })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return response.json()
  }

  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method: 'GET',
      header: headers,
      success: (res) => resolve(res.data),
      fail: reject,
    })
  })
}

export const apiPost = async (path, data) => {
  const url = buildUrl(path)
  const headers = {
    'Content-Type': 'application/json',
    ...getMobileAuthHeaders(),
  }

  if (isBrowserFetchAvailable()) {
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return response.json()
  }

  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method: 'POST',
      data,
      header: headers,
      success: (res) => resolve(res.data),
      fail: reject,
    })
  })
}
