// keep the auth layout contract inside Vitest; this file must be a real suite for workspace test runs; verify with npm --workspace apps/admin-console run test
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const styles = readFileSync(resolve(currentDir, 'styles.css'), 'utf8')

describe('admin auth layout contract', () => {
  it('keeps the login shell full bleed across the viewport and the console shell in the new editorial chrome', () => {
    expect(styles).toMatch(/\.app-frame--auth\s*{[^}]*padding:\s*0;/s)
    expect(styles).toMatch(/\.admin-auth-shell\s*{[^}]*width:\s*100%;/s)
    expect(styles).toMatch(/\.admin-auth-shell\s*{[^}]*min-height:\s*100vh;/s)
    expect(styles).toMatch(/\.admin-auth-shell\s*{[^}]*border-radius:\s*0;/s)
    expect(styles).toMatch(/\.sidebar__badge\s*{/)
    expect(styles).toMatch(/\.console-hero\s*{/)
    expect(styles).toMatch(/\.console-shell\s*{[^}]*backdrop-filter:/s)
  })
})
