/* 管理后台独立布局：与用户端分离，简洁的顶栏 + 内容区 */
import { NavLink, Outlet, Navigate } from "react-router-dom"
import { ShieldCheck, BarChart3, LogOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { useAuth } from "@/hooks/use-auth"

const adminNav = [
  { to: "/admin", icon: BarChart3, label: "数据概览", end: true },
]

export default function AdminLayout() {
  const { isAdmin, logout, user } = useAuth()

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Admin sidebar */}
      <aside className="hidden md:flex md:w-56 md:flex-col md:border-r bg-card">
        <div className="flex flex-col h-full">
          <div className="flex items-center gap-2 px-4 py-5">
            <ShieldCheck className="h-6 w-6 text-primary" />
            <span className="text-lg font-bold">管理后台</span>
          </div>
          <Separator />
          <nav className="flex-1 px-3 py-4 space-y-1">
            {adminNav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  }`
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="border-t px-3 py-3 space-y-1">
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start gap-3 px-3 text-muted-foreground hover:text-destructive"
              onClick={logout}
            >
              <LogOut className="h-4 w-4" />
              退出登录
            </Button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile top bar */}
        <header className="flex h-14 items-center justify-between border-b px-4 md:hidden">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <span className="font-semibold">管理后台</span>
          </div>
        </header>

        {/* Mobile nav */}
        <div className="flex border-b px-4 md:hidden">
          {adminNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  isActive
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground"
                }`
              }
            >
              <item.icon className="h-3.5 w-3.5" />
              {item.label}
            </NavLink>
          ))}
        </div>

        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          {user && (
            <div className="mb-6 flex items-center gap-2 text-sm text-muted-foreground">
              <ShieldCheck className="h-4 w-4" />
              管理员：{user.nickname || "Admin"}
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  )
}
