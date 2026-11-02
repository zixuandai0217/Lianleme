// @vitest-environment jsdom
/* 用户列表页：URL 状态（搜索防抖/筛选/排序/分页）、清空、导出可用性与行跳转。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { AdminUsersRequest } from "@/lib/admin-query"
import type { PaginatedUsers } from "@/api/types"

const apiState = vi.hoisted(() => ({
  requests: [] as Record<string, unknown>[],
  response: null as unknown,
  exportRequests: [] as Record<string, unknown>[],
  exportError: null as Error | null,
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    userId: 1,
    user: { id: 1, openid: "admin-openid", nickname: "管理员", is_admin: true },
    isAdmin: true,
    logout: () => undefined,
  }),
}))

vi.mock("@/api", () => ({
  getAdminUsers: (request: Record<string, unknown>) => {
    apiState.requests.push(request)
    return Promise.resolve(apiState.response)
  },
  downloadAdminUsersExport: (request: Record<string, unknown>) => {
    apiState.exportRequests.push(request)
    return apiState.exportError
      ? Promise.reject(apiState.exportError)
      : Promise.resolve(undefined)
  },
}))

import AdminUsersPage from "@/pages/admin/users"

let root: Root | null
let container: HTMLDivElement

const userRow = {
  id: 7,
  nickname: "张三",
  openid: "wx-zh***1234",
  email_masked: "z***@example.com",
  is_admin: false,
  has_api_key: true,
  llm_provider: "qwen",
  created_at: "2026-06-01T00:00:00Z",
  has_plan: true,
  plan_difficulty_factor: 1.2,
  total_checkins: 9,
  checkins_30d: 4,
  last_checkin_date: "2026-06-10",
  last_active_at: "2026-06-10T08:00:00Z",
  days_since_last_checkin: 2,
  flags: ["inactive_14d" as const],
}

function paginated(overrides: Partial<PaginatedUsers> = {}): PaginatedUsers {
  return {
    items: [userRow],
    total: 1,
    page: 1,
    page_size: 20,
    ...overrides,
  }
}

function LocationProbe() {
  /** 观测地址栏与列表页交给详情页的返回地址。 */
  const location = useLocation()
  return (
    <output
      data-testid="probe"
      data-path={location.pathname}
      data-search={location.search}
      data-from={(location.state as { from?: string } | null)?.from ?? ""}
    />
  )
}

const probe = () => container.querySelector<HTMLOutputElement>('[data-testid="probe"]')

const flush = async () => {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function renderList(initialEntry = "/admin/users") {
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="/admin/users/:id" element={<LocationProbe />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>,
    )
  })
  await flush()
}

async function typeSearch(input: HTMLInputElement, value: string) {
  await act(async () => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!
    setValue.call(input, value)
    input.dispatchEvent(new Event("input", { bubbles: true }))
  })
}

async function chooseSelect(select: HTMLSelectElement, value: string) {
  await act(async () => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!
    setValue.call(select, value)
    select.dispatchEvent(new Event("change", { bubbles: true }))
  })
  await flush()
}

const searchInput = () =>
  container.querySelector<HTMLInputElement>(
    'input[placeholder="搜索昵称 / 邮箱 / 用户 ID / openid"]',
  )

const buttonByLabel = (label: string) =>
  Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.trim().includes(label),
  )

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.useFakeTimers()
  apiState.requests = []
  apiState.exportRequests = []
  apiState.exportError = null
  apiState.response = paginated()
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
  vi.useRealTimers()
})

describe("用户列表页", () => {
  it("按 URL 还原请求并渲染服务端已脱敏的行", async () => {
    apiState.response = paginated({ total: 45, page: 2 })
    await renderList("/admin/users?has_plan=true&q=%E5%BC%A0&page=2&page_size=20")

    expect(apiState.requests).toHaveLength(1)
    expect(apiState.requests[0]).toMatchObject({ has_plan: true, q: "张", page: 2 })
    expect(container.textContent).toContain("张三")
    expect(container.textContent).toContain("z***@example.com")
    expect(container.textContent).toContain("wx-zh***1234")
    expect(container.textContent).toContain("共 45 位用户")
    expect(container.textContent).toContain("2 / 3")
  })

  it("搜索停止输入约 300 毫秒后只发一次请求，请求与 URL 都带该词", async () => {
    await renderList()
    expect(apiState.requests).toHaveLength(1)

    const input = searchInput()!
    await typeSearch(input, "张")
    await typeSearch(input, "张三")

    await act(async () => {
      await vi.advanceTimersByTimeAsync(299)
    })
    await flush()
    expect(apiState.requests).toHaveLength(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    await flush()

    expect(apiState.requests).toHaveLength(2)
    expect(apiState.requests[1]).toMatchObject({ q: "张三", page: 1 })
    expect(probe()?.dataset.search).toContain("q=%E5%BC%A0%E4%B8%89")
  })

  it("筛选变化写进 URL 并回到第 1 页", async () => {
    apiState.response = paginated({ total: 45 })
    await renderList("/admin/users?page=2")

    const hasPlan = container.querySelector<HTMLSelectElement>('select[aria-label="是否有计划"]')!
    await chooseSelect(hasPlan, "true")

    const last = apiState.requests.at(-1) as unknown as AdminUsersRequest
    expect(last.has_plan).toBe(true)
    expect(last.page).toBe(1)
    expect(probe()?.dataset.search).toContain("has_plan=true")
    expect(probe()?.dataset.search).not.toContain("page=2")
  })

  it("一键清空筛选后 URL 与请求都回到默认", async () => {
    await renderList(
      "/admin/users?q=%E5%BC%A0&has_plan=true&flag=inactive_14d&sort=last_active_asc&page=3",
    )

    const clear = buttonByLabel("清空筛选")!
    await act(async () => {
      clear.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flush()

    const last = apiState.requests.at(-1)
    expect(last).toMatchObject({ sort: "registered_desc", page: 1, page_size: 20 })
    expect(probe()?.dataset.search).toBe("")
    expect(searchInput()?.value).toBe("")
  })

  it("下一页把页码写进 URL 并重新请求", async () => {
    apiState.response = paginated({ total: 45, page: 1 })
    await renderList()

    const next = container.querySelector<HTMLButtonElement>('button[aria-label="下一页"]')!
    await act(async () => {
      next.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flush()

    expect(apiState.requests.at(-1)).toMatchObject({ page: 2 })
    expect(probe()?.dataset.search).toContain("page=2")
  })

  it("0 行时禁用导出并说明原因，有行时可用且按当前筛选导出", async () => {
    apiState.response = paginated({ items: [], total: 0 })
    await renderList("/admin/users?has_plan=true")

    const exportButton = buttonByLabel("导出 CSV") as HTMLButtonElement
    expect(exportButton.disabled).toBe(true)
    expect(container.textContent).toContain("当前筛选结果为空，暂无可导出的用户")

    apiState.response = paginated({ total: 1 })
    await act(async () => {
      buttonByLabel("重试")?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flush()

    const enabled = buttonByLabel("导出 CSV") as HTMLButtonElement
    expect(enabled.disabled).toBe(false)
    await act(async () => {
      enabled.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flush()

    expect(apiState.exportRequests).toHaveLength(1)
    expect(apiState.exportRequests[0]).toMatchObject({ has_plan: true, sort: "registered_desc" })
  })

  it("点击用户进入详情页，并带上可返回的列表地址", async () => {
    await renderList("/admin/users?has_plan=true&page=2")

    const link = Array.from(container.querySelectorAll("a")).find((anchor) =>
      anchor.textContent?.includes("张三"),
    )!
    await act(async () => {
      link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }))
    })
    await flush()

    expect(probe()?.dataset.path).toBe("/admin/users/7")
    expect(probe()?.dataset.from).toBe("/admin/users?has_plan=true&page=2")
  })

  it("筛选结果为空时给出可操作的空态", async () => {
    apiState.response = paginated({ items: [], total: 0 })
    await renderList("/admin/users?q=nobody")

    expect(container.textContent).toContain("没有符合条件的用户")
    expect(buttonByLabel("清空筛选")).toBeTruthy()
  })
})
