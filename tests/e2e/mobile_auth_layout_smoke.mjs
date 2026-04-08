import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'

const CHROME_CANDIDATES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
]

const DEVTOOLS_PORT = 9333 + Math.floor(Math.random() * 1000)
const TARGET_URL = 'http://localhost:5273'
const VIEWPORT = { width: 1365, height: 768 }

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const findBrowserBinary = () => {
  const candidate = CHROME_CANDIDATES.find((entry) => fs.existsSync(entry))
  assert(candidate, `No Chromium browser found. Checked: ${CHROME_CANDIDATES.join(', ')}`)
  return candidate
}

const fetchJson = async (url) => {
  const response = await fetch(url)
  assert(response.ok, `Request failed for ${url}: ${response.status}`)
  return response.json()
}

async function connectToPageTarget() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const targets = await fetchJson(`http://127.0.0.1:${DEVTOOLS_PORT}/json/list`)
      const pageTarget = targets.find((entry) => entry.type === 'page')

      if (pageTarget?.webSocketDebuggerUrl) {
        return pageTarget.webSocketDebuggerUrl
      }
    } catch {}

    await sleep(200)
  }

  throw new Error('Timed out waiting for a Chrome DevTools page target')
}

async function inspectAuthLayout() {
  const browserBinary = findBrowserBinary()
  const userDataDir = path.resolve('tmp/chrome-profile-mobile-auth-layout')
  fs.mkdirSync(userDataDir, { recursive: true })

  const browser = spawn(
    browserBinary,
    [
      '--headless=new',
      '--disable-gpu',
      '--disable-background-networking',
      '--disable-component-update',
      `--remote-debugging-port=${DEVTOOLS_PORT}`,
      `--user-data-dir=${userDataDir}`,
      `--window-size=${VIEWPORT.width},${VIEWPORT.height}`,
      'about:blank',
    ],
    { stdio: ['ignore', 'ignore', 'pipe'] },
  )

  let stderr = ''
  browser.stderr.on('data', (chunk) => {
    stderr += chunk.toString()
  })

  let succeeded = false

  try {
    const websocketUrl = await connectToPageTarget()
    const socket = new WebSocket(websocketUrl)
    const pending = new Map()
    let nextId = 0

    const send = (method, params = {}) => {
      nextId += 1
      const id = nextId
      socket.send(JSON.stringify({ id, method, params }))

      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject })
        setTimeout(() => {
          if (pending.has(id)) {
            pending.delete(id)
            reject(new Error(`Timed out waiting for ${method}`))
          }
        }, 10_000)
      })
    }

    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve, { once: true })
      socket.addEventListener('error', reject, { once: true })
    })

    socket.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data.toString())

      if (payload.id && pending.has(payload.id)) {
        const { resolve, reject } = pending.get(payload.id)
        pending.delete(payload.id)

        if (payload.error) {
          reject(new Error(payload.error.message))
          return
        }

        resolve(payload.result ?? {})
      }
    })

    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', { url: TARGET_URL })
    await sleep(2_500)

    const evaluation = await send('Runtime.evaluate', {
      expression: `(() => {
        const shell = document.querySelector('.auth-shell')
        const brand = document.querySelector('.auth-brand-mark')
        if (!shell || !brand) {
          return null
        }

        const shellRect = shell.getBoundingClientRect().toJSON()
        const brandRect = brand.getBoundingClientRect().toJSON()
        const shellStyles = getComputedStyle(shell)
        return {
          viewport: { width: window.innerWidth, height: window.innerHeight },
          shellRect,
          brandRect,
          shellDisplay: shellStyles.display,
        }
      })()`,
      returnByValue: true,
    })

    socket.close()

    assert(evaluation.result?.value, 'Auth shell or brand mark not found on localhost:5273')
    succeeded = true
    return evaluation.result.value
  } finally {
    browser.kill('SIGTERM')
    if (!succeeded && stderr) {
      process.stderr.write(stderr)
    }
  }
}

// protect the H5 auth card from falling back to inline layout so centering and max-width survive on desktop preview; login preview shell only; verify with `node tests/e2e/mobile_auth_layout_smoke.mjs`.
const layout = await inspectAuthLayout()
const shellCenter = layout.shellRect.left + layout.shellRect.width / 2
const brandCenter = layout.brandRect.left + layout.brandRect.width / 2
const viewportCenter = layout.viewport.width / 2

assert.notEqual(layout.shellDisplay, 'inline', `Expected .auth-shell to use block formatting, got ${layout.shellDisplay}`)
assert(layout.shellRect.width <= 430, `Expected auth shell width <= 430px, got ${layout.shellRect.width}px`)
assert(Math.abs(shellCenter - viewportCenter) <= 8, `Expected auth shell to be centered, got left ${layout.shellRect.left}px width ${layout.shellRect.width}px`)
assert(Math.abs(brandCenter - shellCenter) <= 8, `Expected brand mark to be centered in auth shell, got shell center ${shellCenter}px and brand center ${brandCenter}px`)

console.log('mobile_auth_layout_smoke: ok')
