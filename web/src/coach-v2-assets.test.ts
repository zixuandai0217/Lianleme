/* Verify the versioned comic coach bundle before the renderer can consume it. */
import { existsSync, readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const V2_DIR = fileURLToPath(new URL("../public/coach/v2/", import.meta.url))
const MANIFEST_PATH = fileURLToPath(new URL("../public/coach/v2/manifest.json", import.meta.url))
const REQUIRED_ROLES = new Set([
  "body",
  "mouth-A",
  "mouth-B",
  "mouth-C",
  "mouth-D",
  "mouth-E",
  "mouth-F",
  "mouth-G",
  "mouth-H",
  "mouth-X",
  "eyes-blink",
  "brow-thinking",
])

interface CoachV2Manifest {
  canvas: [number, number]
  format: string
  total_bytes: number
  assets: Array<{
    role: string
    file: string
    width: number
    height: number
    alpha_bbox: [number, number, number, number]
    bytes: number
  }>
}

// Load the checked-in asset contract after proving the manifest exists.
function readManifest(): CoachV2Manifest {
  return JSON.parse(readFileSync(MANIFEST_PATH, "utf8")) as CoachV2Manifest
}

describe("comic coach v2 asset bundle", () => {
  it("publishes the complete aligned runtime contract", () => {
    expect(existsSync(MANIFEST_PATH), "missing coach v2 manifest").toBe(true)
    if (!existsSync(MANIFEST_PATH)) return

    const manifest = readManifest()
    expect(manifest.canvas).toEqual([1254, 1254])
    expect(manifest.format).toBe("lossless-webp-rgba")
    expect(new Set(manifest.assets.map((asset) => asset.role))).toEqual(REQUIRED_ROLES)
    expect(manifest.total_bytes).toBeLessThanOrEqual(2_000_000)

    for (const asset of manifest.assets) {
      expect([asset.width, asset.height], asset.role).toEqual(manifest.canvas)
      expect(asset.alpha_bbox[2], asset.role).toBeGreaterThan(asset.alpha_bbox[0])
      expect(asset.alpha_bbox[3], asset.role).toBeGreaterThan(asset.alpha_bbox[1])
      expect(asset.bytes, asset.role).toBeGreaterThan(0)
      expect(existsSync(`${V2_DIR}${asset.file}`), asset.file).toBe(true)
    }
  })
})
