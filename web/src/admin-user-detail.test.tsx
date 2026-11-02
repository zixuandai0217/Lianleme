// @vitest-environment jsdom
/* 用户详情页：七张分区卡片各自加载/空态/错误态，单分区失败不拖垮其他分区。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type {
  AdminUserDetailResponse,
  AdminUserDetailSection,
  PaginatedUsers,
} from "@/api/types"

const apiState = vi.hoisted(() => ({
  detailCalls: [] as { sections?: string[] }[],
  failSections: [] as string[],
  detail: null as unknown,
  listCalls: [] as Record<string, unknown>[],
  list: null as unknown,
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
  getAdminUserDetail: (_userId: number, options: { sections?: string[] }) => {
    apiState.detailCalls.push({ sections: options.sections })
    const section = options.sections?.[0]
    if (section && apiState.failSections.includes(section)) {
      return Promise.reject(new Error("计划服务暂不可用"))
    }
    return Promise.resolve(apiState.detail)
  },
  getAdminUsers: (request: Record<string, unknown>) => {
    apiState.listCalls.push(request)
    return Promise.resolve(apiState.list)
  },
}))

import AdminUsersPage from "@/pages/admin/users"
import AdminUserDetailPage from "@/pages/admin/user-detail"

let root: Root | null
let container: HTMLDivElement

const profileRow = {
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

function detail(payload: Record<string, unknown>): AdminUserDetailResponse {
  return {
    user_id: 7,
    sections: Object.keys(payload) as AdminUserDetailSection[],
    ...payload,
  } as AdminUserDetailResponse
}

const richDetail = () =>
  detail({
    profile: profileRow,
    body_analysis: {
      body_type: "ectomorph",
      body_fat_range: "18-22%",
      weak_muscles: ["胸", "肩"],
      strengths: ["腿"],
      summary: "偏瘦，先补胸背",
      analyzed_at: "2026-06-02T09:00:00Z",
      source: "analysis_record",
    },
    plan: {
      plan_id: 12,
      week_start: "2026-06-08",
      difficulty_factor: 1.1,
      status: "active",
      week_structure: [
        {
          day: 1,
          focus: "胸背",
          is_rest_day: false,
          exercise_count: 2,
          total_sets: 7,
          estimated_duration: 55,
        },
      ],
      generation: null,
      latest_adjustment: {
        direction: "decrease",
        trigger: "completion_rate",
        completion_rate: 0.42,
        occurred_at: "2026-06-14T10:00:00Z",
        reason: "完成率偏低，下周降强度",
      },
    },
    checkins: {
      window_days: 90,
      series: [
        { workout_date: "2026-06-10", completion_rate: 0.9, duration_minutes: 40, difficulty_rating: 3 },
      ],
      streak_days: 3,
      total_checkins: 9,
      completion_rate_distribution: { "80-100": 1 },
    },
    weights: {
      window_days: 90,
      series: [{ recorded_date: "2026-06-09", weight: 72.5 }],
      record_count: 1,
      records_per_week: 0.78,
      latest_weight: 72.5,
      last_recorded_date: "2026-06-09",
    },
    timeline: {
      items: [
        {
          type: "first_plan_generated",
          occurred_at: "2026-06-03T08:00:00Z",
          summary: "生成了第一份训练计划",
          message: "生成第一份训练计划（难度系数 1.0）",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    },
    usage: {
      has_api_key: true,
      llm_provider: "qwen",
      chat_message_count: 12,
      user_message_count: 6,
      assistant_message_count: 6,
      last_chat_at: "2026-06-10T08:00:00Z",
    },
  })

const emptyDetail = () =>
  detail({
    profile: profileRow,
    body_analysis: null,
    plan: null,
    checkins: {
      window_days: 90,
      series: [],
      streak_days: 0,
      total_checkins: 0,
      completion_rate_distribution: {},
    },
    weights: {
      window_days: 90,
      series: [],
      record_count: 0,
      records_per_week: 0,
      latest_weight: null,
      last_recorded_date: null,
    },
    timeline: { items: [], total: 0, page: 1, page_size: 20 },
    usage: {
      has_api_key: false,
      llm_provider: null,
      chat_message_count: 0,
      user_message_count: 0,
      assistant_message_count: 0,
      last_chat_at: null,
    },
  })

function LocationProbe() {
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

async function renderApp(initialEntry: string) {
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="/admin/users/:id" element={<AdminUserDetailPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>,
    )
  })
  await flush()
}

const listPage = (): PaginatedUsers => ({
  items: [profileRow],
  total: 45,
  page: 2,
  page_size: 20,
})

const buttonByLabel = (label: string) =>
  Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.trim().includes(label),
  )

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  apiState.detailCalls = []
  apiState.failSections = []
  apiState.detail = null
  apiState.listCalls = []
  apiState.list = listPage()
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
})

describe("用户详情页分区", () => {
  it("每个分区按 sections 单独请求并渲染自己的数据", async () => {
    apiState.detail = richDetail()
    await renderApp("/admin/users/7")

    expect(apiState.detailCalls.map((call) => call.sections?.[0])).toEqual([
      "profile",
      "body_analysis",
      "plan",
      "checkins",
      "weights",
      "timeline",
      "usage",
    ])

    const text = container.textContent ?? ""
    expect(text).toContain("张三")
    expect(text).toContain("z***@example.com")
    expect(text).toContain("ectomorph")
    expect(text).toContain("18-22%")
    expect(text).toContain("胸背")
    expect(text).toContain("完成率偏低，下周降强度")
    expect(text).toContain("3")
    expect(text).toContain("72.5")
    expect(text).toContain("生成第一份训练计划")
    expect(text).toContain("12")
  })

  it("缺数据的分区显示空态，而不是报错或占位成有数据", async () => {
    apiState.detail = emptyDetail()
    await renderApp("/admin/users/7")

    const text = container.textContent ?? ""
    expect(text).toContain("暂无体型分析数据")
    expect(text).toContain("当前没有训练计划")
    expect(text).toContain("近 90 天没有打卡记录")
    expect(text).toContain("近 90 天没有体重记录")
    expect(text).toContain("暂无行为轨迹")
  })

  it("单个分区接口失败时其他分区仍然渲染", async () => {
    apiState.detail = richDetail()
    apiState.failSections = ["plan"]
    await renderApp("/admin/users/7")

    const text = container.textContent ?? ""
    expect(text).toContain("张三")
    expect(text).toContain("ectomorph")
    expect(text).toContain("生成第一份训练计划")
    expect(text).toContain("加载失败")
    expect(text).toContain("计划服务暂不可用")

    const alerts = Array.from(container.querySelectorAll('[role="alert"]'))
    expect(alerts).toHaveLength(1)
  })

  it("从列表进详情再返回，URL 与请求都还原到原来的筛选结果", async () => {
    apiState.detail = richDetail()
    await renderApp("/admin/users?has_plan=true&page=2")

    expect(apiState.listCalls.at(-1)).toMatchObject({ has_plan: true, page: 2 })
    expect(container.textContent).toContain("共 45 位用户")

    const link = Array.from(container.querySelectorAll("a")).find((anchor) =>
      anchor.textContent?.includes("张三"),
    )!
    await act(async () => {
      link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }))
    })
    await flush()

    expect(probe()?.dataset.path).toBe("/admin/users/7")
    expect(probe()?.dataset.from).toBe("/admin/users?has_plan=true&page=2")

    const back = buttonByLabel("返回用户列表")!
    await act(async () => {
      back.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flush()

    expect(probe()?.dataset.path).toBe("/admin/users")
    expect(probe()?.dataset.search).toBe("?has_plan=true&page=2")
    expect(apiState.listCalls.at(-1)).toMatchObject({ has_plan: true, page: 2 })
    expect(container.textContent).toContain("共 45 位用户")
  })

  it("直接进入详情页（没有列表来源）时返回落到列表默认页", async () => {
    apiState.detail = richDetail()
    await renderApp("/admin/users/7")

    const back = buttonByLabel("返回用户列表")!
    await act(async () => {
      back.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flush()

    expect(probe()?.dataset.path).toBe("/admin/users")
    expect(probe()?.dataset.search).toBe("")
  })
})
