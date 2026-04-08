// keep the mobile visual contract explicit while the interface system is being rebuilt; source-level mobile page and tabbar structure only; verify with `node tests/e2e/mobile_surface_contract.mjs`
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'

const read = (relativePath) => readFileSync(path.resolve(relativePath), 'utf8')

const profilePage = read('apps/mobile-client/src/pages/profile/index.vue')
const coachChatPage = read('apps/mobile-client/src/pages/workout/ai-chat.vue')
const tabbar = read('apps/mobile-client/src/components/MobileTabBar.vue')
const theme = read('apps/mobile-client/src/uni.scss')

assert.match(profilePage, /class="[^"]*profile-command-grid/, 'expected profile page to expose the new command grid section')
assert.match(profilePage, /class="[^"]*profile-hero-card/, 'expected profile page to expose the new hero card')
assert.match(coachChatPage, /class="[^"]*coach-chat-shell/, 'expected AI chat page to expose the new shell container')
assert.match(coachChatPage, /class="[^"]*composer-shell/, 'expected AI chat page to expose the new composer shell')
assert.match(tabbar, /class="[^"]*nav-item-badge/, 'expected bottom tab bar to expose the new badge label')
assert.match(theme, /\.app-mobile-section-kicker\s*{/, 'expected shared mobile theme to define the section kicker primitive')

console.log('mobile_surface_contract: ok')
