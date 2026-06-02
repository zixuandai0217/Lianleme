/* 应用根组件：路由定义 + 认证守卫 + 用户/管理分离 */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { TooltipProvider } from "@/components/ui/tooltip"
import Layout from "@/components/layout"
import AdminLayout from "@/components/admin-layout"
import LoginPage from "@/pages/login"
import AdminLoginPage from "@/pages/admin-login"
import DashboardPage from "@/pages/dashboard"
import AnalysisPage from "@/pages/analysis"
import PlanPage from "@/pages/plan"
import CoachPage from "@/pages/coach"
import ProfilePage from "@/pages/profile"
import WeightPage from "@/pages/weight"
import AdminPage from "@/pages/admin"
import { AuthProvider, useAuth } from "@/hooks/use-auth"
import { Loader2 } from "lucide-react"

function LoadingScreen() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    </div>
  )
}

function UserGate({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading, isAdmin } = useAuth()

  if (loading) {
    return <LoadingScreen />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (isAdmin) {
    return <Navigate to="/admin" replace />
  }

  return <>{children}</>
}

function AdminGate({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading, isAdmin } = useAuth()

  if (loading) {
    return <LoadingScreen />
  }

  if (!isAuthenticated) {
    return <Navigate to="/admin/login" replace />
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

function LoginRedirect() {
  const { isAuthenticated, loading, isAdmin } = useAuth()

  if (loading) {
    return <LoadingScreen />
  }

  if (isAuthenticated) {
    return <Navigate to={isAdmin ? "/admin" : "/"} replace />
  }

  return <LoginPage />
}

function AdminLoginRedirect() {
  const { isAuthenticated, loading, isAdmin } = useAuth()

  if (loading) {
    return <LoadingScreen />
  }

  if (isAuthenticated) {
    return <Navigate to={isAdmin ? "/admin" : "/"} replace />
  }

  return <AdminLoginPage />
}

export default function App() {
  return (
    <BrowserRouter>
      <TooltipProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginRedirect />} />
            <Route path="/admin/login" element={<AdminLoginRedirect />} />

            {/* 用户端路由 */}
            <Route
              element={
                <UserGate>
                  <Layout />
                </UserGate>
              }
            >
              <Route path="/" element={<DashboardPage />} />
              <Route path="/analysis" element={<AnalysisPage />} />
              <Route path="/plan" element={<PlanPage />} />
              <Route path="/coach" element={<CoachPage />} />
              <Route path="/weight" element={<WeightPage />} />
              <Route path="/profile" element={<ProfilePage />} />
            </Route>

            {/* 管理后台路由（独立布局） */}
            <Route
              element={
                <AdminGate>
                  <AdminLayout />
                </AdminGate>
              }
            >
              <Route path="/admin" element={<AdminPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </TooltipProvider>
    </BrowserRouter>
  )
}
