/* Application shell: desktop sidebar + mobile bottom navigation. */
import { NavLink, Outlet } from "react-router-dom"
import { Activity, Bot, ChartNoAxesCombined, ClipboardList, Dumbbell, LogOut, User } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sidebar } from "@/components/sidebar"
import { useAuth } from "@/hooks/use-auth"

const navItems = [
  { to: "/coach", icon: Bot, label: "数字教练" },
  { to: "/analysis", icon: Activity, label: "体型分析" },
  { to: "/plan", icon: ClipboardList, label: "训练计划" },
  { to: "/weight", icon: ChartNoAxesCombined, label: "体重记录" },
  { to: "/profile", icon: User, label: "我的" },
]

// Render the compact product signature used across navigation surfaces.
function BrandSignature() {
  return (
    <div className="flex items-center gap-3">
      <span className="grid size-9 place-items-center rounded-md bg-brand-dark text-primary shadow-sm">
        <Dumbbell className="size-4.5" />
      </span>
      <span className="min-w-0">
        <span className="block font-heading text-lg leading-none font-semibold text-foreground">练了么</span>
        <span className="mt-1 block font-sans text-[0.58rem] font-semibold uppercase text-muted-foreground [letter-spacing:0.12em]">
          Move with intent
        </span>
      </span>
    </div>
  )
}

// Keep all three primary destinations visible within thumb reach on mobile.
function MobileNavigation() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-5 border-t border-border bg-card/95 px-2 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-[0_-8px_24px_rgba(23,26,23,0.08)] backdrop-blur md:hidden"
      aria-label="移动主导航"
    >
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) =>
            `flex min-h-14 flex-col items-center justify-center gap-1 rounded-md font-sans text-[0.68rem] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 ${
              isActive ? "bg-card text-primary shadow-sm" : "text-muted-foreground hover:bg-muted hover:text-foreground"
            }`
          }
        >
          <item.icon className="size-5" />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

// Frame authenticated product pages: sidebar on desktop, bottom nav on mobile.
export default function Layout() {
  const { logout } = useAuth()

  return (
    <div className="min-h-[100dvh] bg-background">
      {/* Desktop sidebar */}
      <Sidebar />

      {/* Main content area (offset for fixed sidebar on desktop) */}
      <div className="md:pl-60">
        {/* Mobile-only top header */}
        <header className="sticky top-0 z-40 border-b border-border bg-background/92 backdrop-blur-xl md:hidden">
          <div className="mx-auto flex h-16 w-full max-w-[1280px] items-center justify-between px-4 sm:px-6 md:px-8 xl:px-10">
            <BrandSignature />
            <div className="flex items-center gap-2">
              <NavLink
                to="/profile"
                aria-label="打开个人资料"
                className="grid size-9 place-items-center rounded-md border border-border bg-card text-brand-green"
              >
                <User className="size-4" />
              </NavLink>
              <Button
                variant="ghost"
                size="icon"
                className="size-9 border border-border bg-card text-muted-foreground"
                aria-label="退出登录"
                title="退出登录"
                onClick={logout}
              >
                <LogOut className="size-4" />
              </Button>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1280px] px-4 pt-5 pb-28 md:pb-10 sm:px-6 md:px-8 md:pt-8 xl:px-10">
          <Outlet />
        </main>
      </div>

      <MobileNavigation />
    </div>
  )
}
