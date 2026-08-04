/* Verify the source-level product contract for the shared 2D digital coach. */
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const source = (relativePath: string) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8")

const layout = source("./components/layout.tsx")
const dashboard = source("./pages/dashboard/index.tsx")
const coachPage = source("./pages/coach/index.tsx")

describe("2D digital coach", () => {
  it("uses the shared stage coach as the primary conversation surface", () => {
    expect(coachPage).toContain("DigitalCoach")
    expect(coachPage).toContain('variant="stage"')
    expect(coachPage).toContain("当前训练")
    expect(coachPage).toContain("对话记录")
  })

  it("keeps all five primary navigation destinations available", () => {
    expect(layout).toContain('{ to: "/coach", icon: Bot, label: "数字教练" }')
    expect(layout).toContain('{ to: "/analysis", icon: Activity, label: "体型分析" }')
    expect(layout).toContain('{ to: "/plan", icon: ClipboardList, label: "训练计划" }')
    expect(layout).toContain('{ to: "/weight", icon: ChartNoAxesCombined, label: "体重记录" }')
    expect(layout).toContain('{ to: "/profile", icon: User, label: "我的" }')
  })

  it("routes coach-led homepage actions to every internal workflow", () => {
    for (const destination of ["/analysis", "/plan", "/coach", "/weight"]) {
      expect(dashboard).toContain(`to: "${destination}"`)
    }
    expect(dashboard).toContain("recommendedAction")
    expect(dashboard).toContain("secondaryActions.map")
    expect(dashboard).not.toContain("coachActions.map")
  })

  it("shows actionable streaming, voice, and error states", () => {
    expect(coachPage).toContain("正在思考")
    expect(coachPage).toContain("正在说话")
    expect(coachPage).toContain("连接失败")
    expect(coachPage).toContain('aria-live="polite"')
  })
})
