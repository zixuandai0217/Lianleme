<template>
  <!-- present the admin login as a branded split-screen gate before the console shell mounts; admin authentication entry only; verify with npm --workspace apps/admin-console run build -->
  <div class="app-frame app-frame--auth">
    <section class="admin-auth-shell">
      <aside class="admin-auth-visual">
        <div class="admin-auth-brand">
          <div class="brand-card__logo admin-auth-brand__logo">
            <AppIcon name="sparkles" :size="20" />
          </div>
          <div>
            <span class="admin-auth-eyebrow">LIANLEME ADMIN</span>
            <strong>练了么后台</strong>
          </div>
        </div>

        <div class="admin-auth-hero">
          <span class="admin-auth-pill">OPERATIONS ECOSYSTEM</span>
          <h1>释放内容、教练与运营的协作效率</h1>
          <p>统一查看用户状态、菜谱素材与 AI 教练配置，让每天的健身服务节奏更稳定。</p>
        </div>

        <div class="admin-auth-scorecard">
          <div class="admin-auth-scorecard__brand">练了么</div>
          <div class="admin-auth-scorecard__body">
            <strong>后台作战室</strong>
            <span>用户增长 · 菜谱管理 · AI 调度</span>
          </div>
        </div>

        <div class="admin-auth-meter">
          <div class="admin-auth-meter__row">
            <span>系统完备性</span>
            <strong>99.9%</strong>
          </div>
          <div class="admin-auth-meter__track">
            <span />
          </div>
        </div>

        <div class="admin-auth-footnote">
          <span>为现代健身运营团队打造的一体化工作台</span>
          <span>V1 演示环境</span>
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
