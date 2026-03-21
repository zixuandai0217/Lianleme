// keep the admin login gate stateful but deterministic; admin auth form and session flow only; verify with npm --workspace apps/admin-console run build
import { reactive, ref } from 'vue'

import {
  buildAdminSession,
  clearAdminSession,
  getBrowserAdminStorage,
  hasAdminLoginErrors,
  persistAdminSession,
  restoreAdminSession,
  validateAdminLoginDraft,
} from '../lib/adminAuth'
import type { AdminLoginDraft, AdminLoginErrors, AdminSession } from '../types/admin'

const createDraft = (session: AdminSession | null): AdminLoginDraft => ({
  account: session?.account ?? '',
  password: '',
  rememberDevice: session?.rememberDevice ?? true,
})

export const useAdminAuth = () => {
  const storage = getBrowserAdminStorage()
  const session = ref<AdminSession | null>(restoreAdminSession(storage))
  const draft = reactive<AdminLoginDraft>(createDraft(session.value))
  const errors = reactive<AdminLoginErrors>({})
  const submitting = ref(false)

  const clearErrors = () => {
    errors.account = undefined
    errors.password = undefined
  }

  const setAccount = (value: string) => {
    draft.account = value
    errors.account = undefined
  }

  const setPassword = (value: string) => {
    draft.password = value
    errors.password = undefined
  }

  const setRememberDevice = (value: boolean) => {
    draft.rememberDevice = value
  }

  const submitLogin = async () => {
    clearErrors()

    const nextErrors = validateAdminLoginDraft(draft)
    errors.account = nextErrors.account
    errors.password = nextErrors.password

    if (hasAdminLoginErrors(nextErrors)) {
      return false
    }

    submitting.value = true

    try {
      const nextSession = buildAdminSession(draft)
      persistAdminSession(nextSession, draft.rememberDevice, storage)
      session.value = nextSession
      draft.password = ''
      return true
    } finally {
      submitting.value = false
    }
  }

  const logout = () => {
    const lastAccount = session.value?.account ?? draft.account

    clearAdminSession(storage)
    session.value = null
    draft.account = lastAccount
    draft.password = ''
    draft.rememberDevice = true
    clearErrors()
  }

  return {
    draft,
    errors,
    session,
    submitting,
    setAccount,
    setPassword,
    setRememberDevice,
    submitLogin,
    logout,
  }
}
