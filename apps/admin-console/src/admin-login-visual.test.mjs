// lock the admin login visual panel to a minimalist spotlight composition; left auth hero only; verify with node apps/admin-console/src/admin-login-visual.test.mjs
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const component = readFileSync(resolve(currentDir, 'components/AdminLoginShell.vue'), 'utf8')
const styles = readFileSync(resolve(currentDir, 'styles.css'), 'utf8')

assert.match(component, /class="admin-auth-spotlight"/)
assert.match(component, /class="admin-auth-mark"/)
assert.match(component, /class="admin-auth-slogan"/)
assert.doesNotMatch(component, /admin-auth-scorecard/)
assert.doesNotMatch(component, /admin-auth-meter/)
assert.doesNotMatch(component, /admin-auth-footnote/)

assert.match(styles, /\.admin-auth-spotlight\s*{/)
assert.match(styles, /\.admin-auth-mark\s*{/)
assert.match(styles, /\.admin-auth-slogan\s*{/)
