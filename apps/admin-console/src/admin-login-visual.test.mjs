// keep the admin login visual contract inside Vitest; this file must be a real suite for workspace test runs; verify with npm --workspace apps/admin-console run test
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const component = readFileSync(resolve(currentDir, 'components/AdminLoginShell.vue'), 'utf8')
const styles = readFileSync(resolve(currentDir, 'styles.css'), 'utf8')

describe('admin login visual contract', () => {
  it('keeps the spotlight composition and includes the new operating-system copy blocks', () => {
    expect(component).toMatch(/class="admin-auth-spotlight"/)
    expect(component).toMatch(/class="admin-auth-mark"/)
    expect(component).toMatch(/class="admin-auth-slogan"/)
    expect(component).toMatch(/class="admin-auth-telemetry"/)
    expect(component).toMatch(/class="admin-login-surface-note"/)
    expect(component).not.toMatch(/admin-auth-scorecard/)
    expect(component).not.toMatch(/admin-auth-meter/)
    expect(component).not.toMatch(/admin-auth-footnote/)
  })

  it('defines the spotlight-specific styles', () => {
    expect(styles).toMatch(/\.admin-auth-spotlight\s*{/)
    expect(styles).toMatch(/\.admin-auth-mark\s*{/)
    expect(styles).toMatch(/\.admin-auth-slogan\s*{/)
    expect(styles).toMatch(/\.admin-auth-telemetry\s*{/)
    expect(styles).toMatch(/\.admin-login-surface-note\s*{/)
  })
})
