import fs from 'node:fs'
import path from 'node:path'

// keep the mp-weixin build free of scoped universal selectors because 微信开发者工具 rejects the generated wxss and renders a blank screen; compiled mp stylesheet only; verify with `npm --workspace apps/mobile-client run build:mp-weixin && node tests/e2e/mobile_mp_style_contract.mjs`.
const target = path.resolve('apps/mobile-client/dist/build/mp-weixin/app.wxss')

if (!fs.existsSync(target)) {
  throw new Error(`mp-weixin stylesheet not found at ${target}`)
}

const source = fs.readFileSync(target, 'utf8')
const unsupportedSelectors = source.match(/\*\.data-v-[a-z0-9]+|\*\s*\.data-v-[a-z0-9]+|\*\.data-v|\*\s*::(?:before|after)/gi) ?? []
const scopedUniversalLines = source
  .split(/\r?\n/)
  .filter((line) => line.includes('*.data-v-') || line.includes('*::before') || line.includes('*::after'))

if (unsupportedSelectors.length || scopedUniversalLines.length) {
  throw new Error(
    `Unsupported mp-weixin selectors found in app.wxss:\n${scopedUniversalLines.slice(0, 12).join('\n')}`,
  )
}

console.log('mp-weixin stylesheet contract passed')
