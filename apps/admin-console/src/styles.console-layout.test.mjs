// keep the authenticated admin shell full-bleed so the console uses the full browser viewport instead of sitting inside a centered outer card; console shell layout contract only; verify with `npm --workspace apps/admin-console run test -- src/styles.console-layout.test.mjs`.
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const styles = readFileSync(resolve(currentDir, 'styles.css'), 'utf8')

describe('admin console layout contract', () => {
  it('keeps the authenticated shell full-bleed across the viewport', () => {
    expect(styles).toMatch(/\.app-frame\s*{[^}]*padding:\s*0;/s)
    expect(styles).toMatch(/\.console-shell\s*{[^}]*width:\s*100%;/s)
    expect(styles).toMatch(/\.console-shell\s*{[^}]*min-height:\s*100vh;/s)
    expect(styles).toMatch(/\.console-shell\s*{[^}]*border-radius:\s*0;/s)
    expect(styles).not.toMatch(/\.console-shell\s*{[^}]*max-width:\s*1480px;/s)
    expect(styles).not.toMatch(/\.console-shell\s*{[^}]*margin:\s*0 auto;/s)
  })
})
