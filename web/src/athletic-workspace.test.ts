/* Verify the source-level contract for the modern athletic workspace. */
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const source = (relativePath: string) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8")

const css = source("./index.css").toLowerCase()
const layout = source("./components/layout.tsx")
const dashboard = source("./pages/dashboard/index.tsx")
const coach = source("./components/digital-coach.tsx")

// Calculate WCAG contrast for the approved primary color contracts.
function contrastRatio(foreground: string, background: string) {
  const luminance = (hex: string) => {
    const channels = hex.match(/[a-f\d]{2}/gi)?.map((channel) => Number.parseInt(channel, 16) / 255) ?? []
    const [red, green, blue] = channels.map((channel) =>
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
    )
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue
  }
  const values = [luminance(foreground), luminance(background)].sort((left, right) => right - left)
  return (values[0] + 0.05) / (values[1] + 0.05)
}

describe("modern athletic workspace", () => {
  it("uses the approved graphite, forest, coral, and cool-neutral system", () => {
    for (const color of ["#171a17", "#f4f6f1", "#3f5f4a", "#b84f39", "#477a89"]) {
      expect(css).toContain(color)
    }
    expect(contrastRatio("#b84f39", "#ffffff")).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio("#b84f39", "#f4f6f1")).toBeGreaterThanOrEqual(4.5)
    expect(css).toContain("--font-body: 'geist variable'")
    expect(css).not.toContain("--font-body: 'lora variable'")
  })

  it("uses a desktop sidebar with always-visible mobile bottom navigation", () => {
    expect(layout).toContain("<Sidebar />")
    expect(layout).toContain("md:pl-60")
    expect(layout).toContain('aria-label="移动主导航"')
    expect(layout).toContain("fixed inset-x-0 bottom-0 z-50")
    expect(layout).toContain("pb-28 md:pb-10")
    expect(layout).not.toContain("SheetContent")
  })

  it("presents one recommendation and only three secondary actions", () => {
    expect(dashboard).toContain("const recommendedAction = coachActions.find")
    expect(dashboard).toContain("const secondaryActions = coachActions.filter")
    expect(dashboard).toContain("secondaryActions.map")
    expect(dashboard).toContain("建议下一步")
    expect(dashboard).not.toContain("coachActions.map")
  })

  it("keeps the shared 2D coach present as a compact status signal", () => {
    expect(dashboard).toContain('variant="portrait"')
    expect(coach).toContain('variant: "stage" | "portrait"')
    expect(coach).toContain('data-coach-renderer="layered-2d"')
    expect(coach).toContain('variant === "portrait" ? "aspect-square bg-transparent"')
  })

  it("exposes the selected training difficulty to assistive technology", () => {
    expect(dashboard).toContain('role="radiogroup"')
    expect(dashboard).toContain('aria-labelledby="difficulty-label"')
    expect(dashboard).toContain('role="radio"')
    expect(dashboard).toContain("aria-checked={rating === difficulty}")
  })
})
