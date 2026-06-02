/* 主布局：侧边栏导航 + 用户信息 + 退出登录 + 响应式框架 */
import { useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import {
  LayoutDashboard,
  ScanEye,
  CalendarDays,
  MessageSquare,
  Scale,
  User,
  Menu,
  X,
  Dumbbell,
  LogOut,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { Separator } from "@/components/ui/separator"
import { useAuth } from "@/hooks/use-auth"

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "首页" },
  { to: "/analysis", icon: ScanEye, label: "体型分析" },
  { to: "/plan", icon: CalendarDays, label: "训练计划" },
  { to: "/coach", icon: MessageSquare, label: "AI 陪练" },
  { to: "/weight", icon: Scale, label: "体重记录" },
  { to: "/profile", icon: User, label: "个人资料" },
]

function NavContent({ onNavigate, onLogout }: { onNavigate?: () => void; onLogout: () => void }) {
  const { user } = useAuth()

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-5">
        <Dumbbell className="h-7 w-7 text-primary" />
        <span className="text-xl font-bold">练了么</span>
      </div>
      <Separator />
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={onNavigate}
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

      <div className="border-t px-3 py-3 space-y-2">
        {user && (
          <div className="flex items-center gap-2 px-3 py-1.5">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
              <User className="h-3.5 w-3.5 text-primary" />
            </div>
            <span className="text-sm font-medium truncate">
              {user.nickname || "用户"}
            </span>
          </div>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-3 px-3 text-muted-foreground hover:text-destructive"
          onClick={() => {
            onNavigate?.()
            onLogout()
          }}
        >
          <LogOut className="h-4 w-4" />
          退出登录
        </Button>
      </div>
    </div>
  )
}

export default function Layout() {
  const [open, setOpen] = useState(false)
  const { logout } = useAuth()

  return (
    <div className="flex h-screen bg-background">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex md:w-60 md:flex-col md:border-r bg-card">
        <NavContent onLogout={logout} />
      </aside>

      {/* Mobile sidebar */}
      <Sheet open={open} onOpenChange={setOpen}>
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Top bar (mobile) */}
          <header className="flex h-14 items-center gap-3 border-b px-4 md:hidden">
            <SheetTrigger
              className="inline-flex items-center justify-center rounded-lg h-9 w-9 hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </SheetTrigger>
            <div className="flex items-center gap-2">
              <Dumbbell className="h-5 w-5 text-primary" />
              <span className="font-semibold">练了么</span>
            </div>
          </header>

          {/* Main content */}
          <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
            <Outlet />
          </main>
        </div>
        <SheetContent side="left" className="w-60 p-0">
          <NavContent onNavigate={() => setOpen(false)} onLogout={logout} />
        </SheetContent>
      </Sheet>
    </div>
  )
}
