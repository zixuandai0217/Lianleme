// @vitest-environment jsdom
/* 管理端三页工作台的路由、侧边栏高亮与前端权限回归（非管理员一律跳走）。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { AdminUserDetailResponse } from "@/api/types"

const authState = vi.hoisted(() => ({
  isAdmin: true,
  user: null as { id: number; openid: string; nickname: string; is_admin: boolean } | null,
}))

const apiState = vi.hoisted(() => ({
  detail: null as unknown,
  list: null as unknown,
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    userId: authState.user?.id ?? null,
    user: authState.user,
    isAuthenticated: authState.user !== null,
    isAdmin: authState.isAdmin,
    logout: () => undefined,
  }),
}))

vi.mock("@/api", () => ({
  getAdminStats: () => Promise.resolve({
    total_users: 3,
    total_plans: 5,
    total_workouts: 42,
    active_users_7d: 2,
  }),
  getAdminUsers: () => Promise.resolve(apiState.list),
  getAdminUserDetail: () => Promise.resolve(apiState.detail),
  downloadAdminUsersExport: () => Promise.resolve(undefined),
}))

import { adminRouteTree } from "@/pages/admin/routes"

let root: Root | null
let container: HTMLDivElement

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="probe" data-path={location.pathname} data-search={location.search} />
}

const probe = () => container.querySelector<HTMLOutputElement>('[data-testid="probe"]')

const navLink = (label: string) =>
  Array.from(container.querySelectorAll("a")).filter(
    (anchor) => anchor.textContent?.trim().includes(label) && anchor.getAttribute("href"),
  )

const flush = async () => {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function renderAdminRoutes(initialEntry: string) {
  /** 每次挂载都是一次「直接输入地址 / 刷新」。 */
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          {adminRouteTree}
          <Route path="*" element={<LocationProbe />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>,
    )
  })
  await flush()
}

const detailResponse: AdminUserDetailResponse = {
  user_id: 7,
  sections: ["profile"],
  profile: {
    id: 7,
    nickname: "张三",
    openid: "wx-zh***1234",
    email_masked: "z***@example.com",
    is_admin: false,
    has_api_key: false,
    llm_provider: null,
    created_at: "2026-06-01T00:00:00Z",
    has_plan: true,
    plan_difficulty_factor: null,
    total_checkins: 0,
    checkins_30d: 0,
    last_checkin_date: null,
    last_active_at: "2026-06-01T00:00:00Z",
    days_since_last_checkin: null,
    flags: [],
  },
}

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  authState.isAdmin = true
  authState.user = { id: 1, openid: "admin-openid", nickname: "管理员", is_admin: true }
  apiState.detail = detailResponse
  apiState.list = { items: [], total: 0, page: 1, page_size: 20 }
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
})

describe("管理端三条路由", () => {
  it.each([
    ["/admin", "总用户数"],
    ["/admin/users", "用户列表"],
    ["/admin/users/7", "用户详情"],
  ])("直接访问 %s 渲染对应页面，重新挂载（刷新）仍然渲染", async (path, heading) => {
    await renderAdminRoutes(path)
    expect(container.textContent).toContain(heading)
    expect(probe()?.dataset.path).toBe(path)

    if (root) await act(async () => root?.unmount())
    root = createRoot(container)
    await renderAdminRoutes(path)
    expect(container.textContent).toContain(heading)
    expect(probe()?.dataset.path).toBe(path)
  })

  it("侧边栏两个入口，当前项按路径前缀高亮", async () => {
    await renderAdminRoutes("/admin/users/7")

    expect(navLink("数据概览")).toHaveLength(2)
    expect(navLink("用户")).toHaveLength(2)

    for (const link of navLink("用户")) {
      expect(link.getAttribute("aria-current")).toBe("page")
    }
    for (const link of navLink("数据概览")) {
      expect(link.getAttribute("aria-current")).toBeNull()
    }
  })

  it("概览页上只高亮数据概览", async () => {
    await renderAdminRoutes("/admin")
    for (const link of navLink("数据概览")) {
      expect(link.getAttribute("aria-current")).toBe("page")
    }
    for (const link of navLink("用户")) {
      expect(link.getAttribute("aria-current")).toBeNull()
    }
  })

  it.each(["/admin", "/admin/users", "/admin/users/7"])(
    "非管理员访问 %s 被重定向回用户端，不渲染任何管理页内容",
    async (path) => {
      authState.isAdmin = false
      authState.user = { id: 2, openid: "normal-openid", nickname: "普通用户", is_admin: false }

      await renderAdminRoutes(path)

      expect(probe()?.dataset.path).toBe("/")
      expect(container.textContent).not.toContain("总用户数")
      expect(container.textContent).not.toContain("用户列表")
      expect(container.textContent).not.toContain("用户详情")
    },
  )
})
