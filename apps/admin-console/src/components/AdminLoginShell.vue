<template>
  <!-- present the admin login as a branded split-screen gate before the console shell mounts; admin authentication entry only; verify with npm --workspace apps/admin-console run build -->
  <div class="app-frame app-frame--auth">
    <section class="admin-auth-shell">
      <aside class="admin-auth-visual">
        <!-- reduce the left hero to one logo lockup and one slogan; admin auth visual only; verify with node apps/admin-console/src/admin-login-visual.test.mjs -->
        <div class="admin-auth-spotlight">
          <div class="admin-auth-mark">
            <div class="admin-auth-mark__core">
              <div class="brand-card__logo admin-auth-brand__logo">
                <AppIcon name="sparkles" :size="28" />
              </div>
            </div>
            <div class="admin-auth-wordmark">
              <span class="admin-auth-eyebrow">LIANLEME ADMIN</span>
              <strong>练了么后台</strong>
            </div>
          </div>

          <p class="admin-auth-slogan">让内容、教练与运营，同频协作。</p>
        </div>
      </aside>

      <form class="admin-login-panel" @submit.prevent="emit('submit')">
        <div class="admin-login-header">
          <div class="admin-login-badge">
            <AppIcon name="sparkles" :size="18" />
          </div>
          <div>
            <h2>管理员登录</h2>
            <p>登录后台并管理您的健身生态系统</p>
          </div>
        </div>

        <label class="admin-login-field" :class="{ 'admin-login-field--error': errors.account }">
          <span>管理员账号</span>
          <div class="admin-login-input">
            <AppIcon name="users" :size="18" />
            <input
              :value="draft.account"
              type="text"
              placeholder="用户名或电子邮箱"
              autocomplete="username"
              @input="emit('update:account', ($event.target as HTMLInputElement).value)"
            />
          </div>
          <small v-if="errors.account">{{ errors.account }}</small>
        </label>

        <label class="admin-login-field" :class="{ 'admin-login-field--error': errors.password }">
          <span>密码</span>
          <div class="admin-login-input">
            <AppIcon name="settings" :size="18" />
            <input
              :value="draft.password"
              type="password"
              placeholder="至少 8 位字符"
              autocomplete="current-password"
              @input="emit('update:password', ($event.target as HTMLInputElement).value)"
            />
          </div>
          <small v-if="errors.password">{{ errors.password }}</small>
        </label>

        <div class="admin-login-row">
          <label class="admin-login-check">
            <input
              :checked="draft.rememberDevice"
              type="checkbox"
              @change="emit('update:remember-device', ($event.target as HTMLInputElement).checked)"
            />
            <span>记住此设备</span>
          </label>

          <button class="admin-login-link" type="button" @click="emit('forgot')">忘记密码？</button>
        </div>

        <p class="admin-login-helper">演示环境：账号任意，密码至少 8 位即可进入后台。</p>
        <p v-if="hint" class="admin-login-feedback">{{ hint }}</p>

        <button class="primary-button admin-login-submit" type="submit" :disabled="submitting">
          <span>{{ submitting ? '登录中...' : '登录' }}</span>
          <AppIcon name="chevronRight" :size="16" />
        </button>

        <div class="admin-login-footer">
          <button class="admin-login-link" type="button" @click="emit('placeholder', '技术支持')">技术支持</button>
          <button class="admin-login-link" type="button" @click="emit('placeholder', '使用条款')">使用条款</button>
          <span class="admin-login-copyright">© 2026 练了么</span>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { AdminLoginDraft, AdminLoginErrors } from '../types/admin'
import AppIcon from './AppIcon.vue'

defineProps<{
  draft: AdminLoginDraft
  errors: AdminLoginErrors
  hint: string
  submitting?: boolean
}>()

// keep the login panel stateless so App can own validation and session decisions; admin login form bindings only; verify with npm --workspace apps/admin-console run build
const emit = defineEmits<{
  submit: []
  forgot: []
  placeholder: [label: string]
  'update:account': [value: string]
  'update:password': [value: string]
  'update:remember-device': [value: boolean]
}>()
</script>
