// @vitest-environment jsdom
/* 收件箱页面的用户可见行为：列表、未读筛选、单条已读跳转、全部已读与空态。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { NotificationItem, NotificationListResponse } from "@/api/types"

const inbox = vi.hoisted(() => ({
  items: [] as NotificationItem[],
  unread: 0,
  calls: [] as Array<{ unreadOnly?: boolean }>,
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ userId: 1, user: { id: 1, openid: "u-1" } }),
}))

vi.mock("@/api", () => ({
  getNotifications: (_userId: number, options: { unreadOnly?: boolean } = {}) => {
    inbox.calls.push({ unreadOnly: options.unreadOnly })
    const items = options.unreadOnly ? inbox.items.filter((item) => !item.is_read) : inbox.items
    const response: NotificationListResponse = {
      items,
      total: items.length,
      unread_count: inbox.unread,
      page: 1,
      page_size: 20,
    }
    return Promise.resolve(response)
  },
  markNotificationRead: (_userId: number, notificationId: number) => {
    const target = inbox.items.find((item) => item.id === notificationId)
    if (target) {
      target.is_read = true
      inbox.unread = Math.max(0, inbox.unread - 1)
    }
    return Promise.resolve({
      notification_id: notificationId,
      read_at: "2026-03-18T12:00:00Z",
      unread_count: inbox.unread,
    })
  },
  markAllNotificationsRead: () => {
    inbox.items = inbox.items.map((item) => ({ ...item, is_read: true }))
    inbox.unread = 0
    return Promise.resolve({ updated: inbox.items.length, unread_count: 0 })
  },
}))

import NotificationsPage from "@/pages/notifications"

let root: Root | null
let container: HTMLDivElement

function notification(overrides: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: 1,
    rule_code: "daily_training",
    title: "今天的训练还没打卡",
    body: "胸背约 45 分钟，练完记得打卡。",
    target_path: "/plan",
    created_at: "2026-03-18T11:00:00Z",
    read_at: null,
    is_read: false,
    ...overrides,
  }
}

async function renderInbox() {
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={["/notifications"]}>
        <Routes>
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/plan" element={<div>训练计划页</div>} />
        </Routes>
      </MemoryRouter>,
    )
  })
  await act(async () => {})
  return container.textContent ?? ""
}

const buttonLabels = () =>
  Array.from(container.querySelectorAll("button")).map((button) => button.textContent?.trim() ?? "")

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
  inbox.items = [notification(), notification({ id: 2, title: "恢复日提醒", body: "今天轻量活动。", read_at: "2026-03-17T10:00:00Z", is_read: true })]
  inbox.unread = 1
  inbox.calls = []
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
})

describe("收件箱页面", () => {
  it("展示通知、未读数与未读标记", async () => {
    const text = await renderInbox()

    expect(text).toContain("今天的训练还没打卡")
    expect(text).toContain("胸背约 45 分钟")
    expect(text).toContain("有 1 条未读提醒")
    expect(text).toContain("1 条未读")
    expect(text).toContain("未读")
  })

  it("切换到只看未读会按未读筛选请求", async () => {
    await renderInbox()

    const filterButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.trim() === "全部",
    )
    await act(async () => {
      filterButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    expect(inbox.calls.some((call) => call.unreadOnly === true)).toBe(true)
  })

  it("点击通知会标为已读并跳到目标页", async () => {
    await renderInbox()

    const item = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("今天的训练还没打卡"),
    )
    await act(async () => {
      item?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    expect(await Promise.resolve(container.textContent)).toContain("训练计划页")
    expect(inbox.unread).toBe(0)
  })

  it("全部已读后未读数归零，按钮在无未读时禁用", async () => {
    await renderInbox()

    const readAll = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("全部已读"),
    )
    await act(async () => {
      readAll?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    const text = container.textContent ?? ""
    expect(text).toContain("全部已读，保持这个节奏。")
    expect(text).toContain("无未读")
    const readAllAgain = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("全部已读"),
    )
    expect(readAllAgain?.hasAttribute("disabled")).toBe(true)
  })

  it("没有通知时给出空态说明", async () => {
    inbox.items = []
    inbox.unread = 0

    const text = await renderInbox()

    expect(text).toContain("还没有通知")
    expect(buttonLabels().some((label) => label.includes("全部已读"))).toBe(true)
  })
})
