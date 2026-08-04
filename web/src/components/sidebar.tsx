/**
 * Desktop sidebar navigation with grouped sections and collapsible "数字人" section.
 * Hidden on mobile (< md), fixed on desktop (>= md).
 */
import { useState } from "react"
import { NavLink, useLocation } from "react-router-dom"
import {
  Activity,
  Bot,
  ChartNoAxesCombined,
  ChevronDown,
  ClipboardList,
  Dumbbell,
  LogOut,
  User,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useAuth } from "@/hooks/use-auth"

// ── Navigation data model ──────────────────────────────────────────

interface NavLeaf {
  to: string
  icon: LucideIcon
  label: string
}

type NavEntry =
  | NavLeaf
  | { label: string; icon?: LucideIcon; children: NavLeaf[] }

const sidebarNav: NavEntry[] = [
  {
    label: "数字人",
    children: [
      { to: "/coach", icon: Bot, label: "数字教练" },
      { to: "/analysis", icon: Activity, label: "体型分析" },
    ],
  },
  { to: "/plan", icon: ClipboardList, label: "训练计划" },
  { to: "/weight", icon: ChartNoAxesCombined, label: "体重记录" },
  { to: "/profile", icon: User, label: "我的" },
]

// ── Sub-components ─────────────────────────────────────────────────

/** Sidebar-branded logo and title (dark theme variant). */
function BrandSignature() {
  return (
    <div className="flex items-center gap-3 px-5 py-5">
      <span className="grid size-9 place-items-center rounded-md bg-sidebar-accent text-sidebar-foreground">
        <Dumbbell className="size-4.5" />
      </span>
      <span className="min-w-0">
        <span className="block font-heading text-lg leading-none font-semibold text-sidebar-foreground">
          练了么
        </span>
        <span className="mt-1 block font-sans text-[0.58rem] font-semibold uppercase text-sidebar-foreground/60 [letter-spacing:0.12em]">
          Move with intent
        </span>
      </span>
    </div>
  )
}

/** A standalone flat navigation link. */
function NavItemLink({ to, icon: Icon, label }: NavLeaf) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-md px-4 py-2.5 text-sm font-semibold transition-colors duration-150",
          isActive
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
        )
      }
    >
      <Icon className="size-4.5 shrink-0" />
      <span>{label}</span>
    </NavLink>
  )
}

/** A collapsible group section (e.g. "数字人"). */
function NavGroup({
  label,
  children,
}: {
  label: string
  children: NavLeaf[]
}) {
  const [expanded, setExpanded] = useState(true)
  const { pathname } = useLocation()

  // Group is "active" if any child route matches the current path
  const isActive = children.some((child) => pathname.startsWith(child.to))

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className={cn(
          "flex w-full items-center gap-3 rounded-md px-4 py-2.5 text-sm font-semibold transition-colors duration-150",
          isActive
            ? "text-sidebar-primary"
            : "text-sidebar-foreground/70 hover:text-sidebar-foreground",
        )}
      >
        <ChevronDown
          className={cn(
            "size-3.5 shrink-0 transition-transform duration-200",
            expanded ? "rotate-0" : "-rotate-90",
          )}
        />
        <span>{label}</span>
      </button>

      {expanded && (
        <div className="mt-0.5 space-y-0.5 pl-6">
          {children.map((item) => (
            <NavItemLink key={item.to} {...item} />
          ))}
        </div>
      )}
    </div>
  )
}

/** Render a nav entry that is either a standalone link or a group. */
function NavEntryItem({ entry }: { entry: NavEntry }) {
  if ("children" in entry) {
    return <NavGroup label={entry.label} children={entry.children} />
  }
  return <NavItemLink to={entry.to} icon={entry.icon} label={entry.label} />
}

// ── Main sidebar ───────────────────────────────────────────────────

export function Sidebar() {
  const { logout, user } = useAuth()

  return (
    <aside className="hidden md:flex md:flex-col md:w-60 md:fixed md:inset-y-0 md:left-0 md:z-40 bg-sidebar border-r border-sidebar-border">
      {/* Brand */}
      <BrandSignature />

      {/* Divider */}
      <div className="mx-4 h-px bg-sidebar-border/50" />

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {sidebarNav.map((entry) => (
          <NavEntryItem key={"children" in entry ? entry.label : entry.to} entry={entry} />
        ))}
      </nav>

      {/* User section */}
      <div className="border-t border-sidebar-border px-3 py-3">
        <div className="flex items-center gap-3 rounded-md px-2 py-2">
          <span className="grid size-8 shrink-0 place-items-center rounded-md bg-sidebar-accent text-sidebar-foreground/80">
            <User className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-sans text-sm font-semibold text-sidebar-foreground">
              {user?.nickname || "My homie"}
            </p>
            <p className="font-sans text-xs text-sidebar-foreground/50">
              Get swole or go home 💪
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="mt-1 w-full justify-start gap-3 px-2 text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground"
          onClick={logout}
        >
          <LogOut className="size-4" />
          退出登录
        </Button>
      </div>
    </aside>
  )
}
