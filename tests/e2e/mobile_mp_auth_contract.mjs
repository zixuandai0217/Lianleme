// keep mini-program auth source aligned with full-bleed screens, guarded tabBar entry, and direct gateway access; mobile auth source contracts only; verify with `node tests/e2e/mobile_mp_auth_contract.mjs`.
import fs from 'node:fs'
import path from 'node:path'

const projectRoot = path.resolve('.')

const read = (relativePath) => {
  return fs.readFileSync(path.join(projectRoot, relativePath), 'utf8')
}

const assert = (condition, message) => {
  if (!condition) {
    throw new Error(message)
  }
}

const loginSource = read('apps/mobile-client/src/pages/auth/login.vue')
const registerSource = read('apps/mobile-client/src/pages/auth/register.vue')
const clientSource = read('apps/mobile-client/src/api/client.js')

for (const [name, source] of [
  ['login', loginSource],
  ['register', registerSource],
]) {
  assert(
    source.includes('uni.switchTab({') && source.includes("url: '/pages/workout/index'"),
    `${name} auth page must switchTab into the workout tab after successful login`,
  )

  assert(
    source.includes('fail:'),
    `${name} auth page is missing a switchTab failure fallback for mini-program entry`,
  )

  assert(
    source.includes("uni.reLaunch({ url: '/pages/workout/index' })"),
    `${name} auth page is missing a fallback reLaunch for the workout landing page`,
  )

  assert(
    source.includes('safe-area-inset-top') && source.includes('safe-area-inset-bottom'),
    `${name} auth page is missing mini-program safe-area padding`,
  )

  assert(
    source.includes('auth-page--immersive') && source.includes('auth-shell--immersive'),
    `${name} auth page is missing the immersive full-bleed mini-program layout classes`,
  )
}

assert(
  !clientSource.includes("typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5273'"),
  'mobile API client still falls back to the H5 localhost preview origin outside the browser runtime',
)

assert(
  clientSource.includes('http://127.0.0.1:18000'),
  'mobile API client is missing a direct gateway fallback for mini-program debugging',
)

console.log('mini-program auth source contract passed')
