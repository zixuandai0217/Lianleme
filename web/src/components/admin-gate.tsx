/* 管理端路由守卫：非管理员不得进入任何 /admin* 路由。
 *
 * 这是体验优化而不是安全边界：后端每个管理端接口都独立校验 token 是否管理员，
 * 未登录 401、非管理员 403（回归测试见 backend/tests/test_admin_permissions.py）。
 * 前端这里只负责把非管理员送回用户端，避免渲染出一个注定 403 的页面。 */
import { Navigate } from "react-router-dom"

import { useAuth } from "@/hooks/use-auth"

export function AdminGate({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading, isAdmin } = useAuth()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/admin/login" replace />
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
