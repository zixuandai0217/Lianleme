<template>
  <!-- switch between the branded login gate and the existing admin console based on persisted session state; admin auth gate only; verify with npm --workspace apps/admin-console run build -->
  <AdminLoginShell
    v-if="!session"
    :draft="draft"
    :errors="errors"
    :hint="authHint"
    :submitting="submitting"
    @submit="handleLogin"
    @forgot="showAuthHint('忘记密码流程当前先保留占位，后续接管理员重置能力。')"
    @placeholder="showAuxiliaryHint"
    @update:account="setAccount"
    @update:password="setPassword"
    @update:remember-device="setRememberDevice"
  />

  <AdminConsoleShell v-else :operator="session" @logout="handleLogout" />
</template>

<script setup lang="ts">
import { ref } from 'vue'

import AdminConsoleShell from './components/AdminConsoleShell.vue'
import AdminLoginShell from './components/AdminLoginShell.vue'
import { useAdminAuth } from './composables/useAdminAuth'

const defaultAuthHint = '演示环境：账号任意，密码至少 8 位即可进入后台。'

const {
  draft,
  errors,
  session,
  submitting,
  setAccount,
  setPassword,
  setRememberDevice,
  submitLogin,
  logout,
} = useAdminAuth()

const authHint = ref(defaultAuthHint)

const showAuthHint = (message: string) => {
  authHint.value = message
}

const showAuxiliaryHint = (label: string) => {
  authHint.value = `${label} 入口先保留占位，待接真实后台流程。`
}

const handleLogin = async () => {
  authHint.value = defaultAuthHint
  await submitLogin()
}

// keep logout side effects and helper copy reset at the App gate so the console shell stays presentation-focused; root admin auth gate only; verify with npm --workspace apps/admin-console run build
const handleLogout = () => {
  logout()
  authHint.value = defaultAuthHint
}
</script>
