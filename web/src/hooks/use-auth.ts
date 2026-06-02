/* 认证状态管理：Context + 手动登录/登出 + 持久化 */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react"
import { createElement } from "react"
import { devAdminLogin, devLogin, getCurrentUser } from "@/api"
import type { UserResponse } from "@/api/types"

interface AuthState {
  token: string | null
  userId: number | null
  user: UserResponse | null
  loading: boolean
  error: string | null
  isAuthenticated: boolean
  isAdmin: boolean
  loginAsUser: () => Promise<void>
  loginAsAdmin: () => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"))
  const [user, setUser] = useState<UserResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const userId = user?.id ?? null
  const isAuthenticated = !!token && !!user
  const isAdmin = !!user?.is_admin

  /** Resolve the authenticated user from the current bearer token. */
  const loadCurrentUser = useCallback(async () => {
    const currentUser = await getCurrentUser()
    setUser(currentUser)
    return currentUser
  }, [])

  /** Exchange a development login endpoint for a bearer token and current user. */
  const loginWith = useCallback(async (loginRequest: () => Promise<{ token: string }>) => {
    try {
      setLoading(true)
      setError(null)
      const res = await loginRequest()
      localStorage.setItem("token", res.token)
      setToken(res.token)
      await loadCurrentUser()
    } catch (e) {
      setError(e instanceof Error ? e.message : "登录失败")
    } finally {
      setLoading(false)
    }
  }, [loadCurrentUser])

  const loginAsUser = useCallback(async () => {
    await loginWith(devLogin)
  }, [loginWith])

  const loginAsAdmin = useCallback(async () => {
    await loginWith(devAdminLogin)
  }, [loginWith])

  const logout = useCallback(() => {
    localStorage.removeItem("token")
    localStorage.removeItem("userId")
    setToken(null)
    setUser(null)
    setError(null)
  }, [])

  const refreshUser = useCallback(async () => {
    if (!token) return
    try {
      await loadCurrentUser()
    } catch {
      // silently ignore
    }
  }, [loadCurrentUser, token])

  useEffect(() => {
    const restore = async () => {
      const savedToken = localStorage.getItem("token")
      if (savedToken) {
        try {
          await loadCurrentUser()
        } catch {
          localStorage.removeItem("token")
          localStorage.removeItem("userId")
          setToken(null)
          setUser(null)
        }
      }
      setLoading(false)
    }
    restore()
  }, [loadCurrentUser])

  const value: AuthState = {
    token,
    userId,
    user,
    loading,
    error,
    isAuthenticated,
    isAdmin,
    loginAsUser,
    loginAsAdmin,
    logout,
    refreshUser,
  }

  return createElement(AuthContext.Provider, { value }, children)
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
