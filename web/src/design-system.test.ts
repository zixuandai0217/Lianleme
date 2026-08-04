/* Verify the shared source-level contract for the athletic product system. */
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const cssPath = fileURLToPath(new URL("./index.css", import.meta.url))
const css = readFileSync(cssPath, "utf8").toLowerCase()
const layout = readFileSync(fileURLToPath(new URL("./components/layout.tsx", import.meta.url)), "utf8")
const analysis = readFileSync(fileURLToPath(new URL("./pages/analysis/index.tsx", import.meta.url)), "utf8")
const dialog = readFileSync(fileURLToPath(new URL("./components/ui/dialog.tsx", import.meta.url)), "utf8")

describe("athletic design system", () => {
  it("uses the complete product palette", () => {
    for (const color of ["#171a17", "#f4f6f1", "#b84f39", "#477a89", "#3f5f4a"]) {
      expect(css).toContain(color)
    }
    expect(css).not.toContain("#e36f4f")
  })

  it("loads the display and interface typefaces", () => {
    expect(css).toContain('@fontsource/poppins/600.css')
    expect(css).toContain('@fontsource/poppins/700.css')
    expect(css).toContain('@fontsource-variable/geist')
    expect(css).toContain("--font-heading: 'poppins'")
    expect(css).toContain("--font-body: 'geist variable'")
  })

  it("keeps interface corners restrained and supports reduced motion", () => {
    expect(css).toContain("--radius: 0.5rem")
    expect(css).toContain("@media (prefers-reduced-motion: reduce)")
    expect(analysis).not.toContain("rounded-xl")
    expect(dialog).not.toContain("rounded-xl")
  })

  it("keeps primary destinations visible on desktop and mobile", () => {
    expect(layout).toContain("<Sidebar />")
    expect(layout).toContain('aria-label="移动主导航"')
    expect(layout).toContain("fixed inset-x-0 bottom-0 z-50")
    expect(layout).not.toContain("SheetContent")
  })

  it("exposes photo selection through a real keyboard-operable button", () => {
    expect(analysis).toContain('aria-label="选择体型分析照片"')
    expect(analysis).toContain('onClick={() => fileRef.current?.click()}')
    expect(analysis).toContain('id="analysis-photo"')
    expect(analysis).toContain('className="hidden"')
  })
})
