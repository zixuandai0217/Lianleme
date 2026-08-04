/* Verify that the shared coach is a local 2D renderer with no Rive or gaze runtime. */
import { existsSync, readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

// Read a repository file as text for build-time integration contracts.
const source = (relativePath: string) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8")

const packageJson = source("../package.json")
const renderer = source("./components/digital-coach.tsx")
const coachPage = source("./pages/coach/index.tsx")
const dashboard = source("./pages/dashboard/index.tsx")
const bodyAsset = fileURLToPath(new URL("../public/coach/rock-coach.webp", import.meta.url))

describe("layered 2D digital coach", () => {
  it("removes the Rive runtime and asset contract", () => {
    expect(packageJson).not.toContain("@rive-app")
    expect(packageJson).not.toContain("validate-coach-rive")
    expect(renderer).not.toContain("useRive")
    expect(renderer).not.toContain("RuntimeLoader")
    expect(renderer).not.toContain(".riv")
  })

  it("uses one aligned character renderer for stage and portrait", () => {
    expect(existsSync(bodyAsset)).toBe(true)
    expect(renderer).toContain('variant: "stage" | "portrait"')
    expect(renderer).toContain('BODY_ASSET = "/coach/rock-coach.webp"')
    expect(renderer).toContain("FACE_ASSETS")
    expect(renderer).toContain('data-coach-renderer="layered-2d"')
    expect(renderer).toContain('data-face-rig="layered"')
    expect(coachPage).toContain('variant="stage"')
    expect(dashboard).toContain('variant="portrait"')
  })

  it("does not restore pointer gaze or per-frame character updates", () => {
    expect(renderer).not.toContain("analyser?:")
    expect(renderer).not.toContain("pointermove")
    expect(renderer).not.toContain("gazeTarget")
    expect(renderer).not.toContain("requestAnimationFrame")
    expect(renderer).not.toContain("speechEnergy")
  })
})
