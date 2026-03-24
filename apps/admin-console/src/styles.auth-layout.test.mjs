// lock the admin login screen to a full-bleed viewport shell; auth-only layout contract; verify with node apps/admin-console/src/styles.auth-layout.test.mjs
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const styles = readFileSync(resolve(currentDir, 'styles.css'), 'utf8')

assert.match(styles, /\.app-frame--auth\s*{[^}]*padding:\s*0;/s)
assert.match(styles, /\.admin-auth-shell\s*{[^}]*width:\s*100%;/s)
assert.match(styles, /\.admin-auth-shell\s*{[^}]*min-height:\s*100vh;/s)
assert.match(styles, /\.admin-auth-shell\s*{[^}]*border-radius:\s*0;/s)
