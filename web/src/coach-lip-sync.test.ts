/* Behavioral and integration contracts for synchronized coach facial animation. */
import { existsSync, readFileSync, statSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const loadLipSync = () => import("./components/coach-lip-sync").catch(() => null)

const source = (relativePath: string) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8")

describe("coach viseme timeline", () => {
  it("switches only at cue boundaries and returns to rest outside speech", async () => {
    const lipSync = await loadLipSync()
    expect(lipSync).not.toBeNull()
    if (!lipSync) return
    const cues = [
      { start: 0, end: 0.1, value: "X" as const },
      { start: 0.1, end: 0.24, value: "B" as const },
      { start: 0.24, end: 0.4, value: "D" as const },
      { start: 0.4, end: 0.5, value: "X" as const },
    ]

    expect(lipSync.visemeAtTime(cues, -0.01)).toBe("X")
    expect(lipSync.visemeAtTime(cues, 0.099)).toBe("X")
    expect(lipSync.visemeAtTime(cues, 0.1)).toBe("B")
    expect(lipSync.visemeAtTime(cues, 0.239)).toBe("B")
    expect(lipSync.visemeAtTime(cues, 0.24)).toBe("D")
    expect(lipSync.visemeAtTime(cues, 0.5)).toBe("X")
  })

  it("resets for pause, replay, and a newly selected message", async () => {
    const lipSync = await loadLipSync()
    expect(lipSync).not.toBeNull()
    if (!lipSync) return
    const clock = new lipSync.CoachVisemeClock([
      { start: 0, end: 0.1, value: "X" },
      { start: 0.1, end: 0.3, value: "C" },
      { start: 0.3, end: 0.4, value: "X" },
    ])

    expect(clock.update(0.2)).toBe("C")
    expect(clock.reset()).toBe("X")
    expect(clock.update(0)).toBe("X")
    clock.setCues([
      { start: 0, end: 0.08, value: "X" },
      { start: 0.08, end: 0.2, value: "H" },
      { start: 0.2, end: 0.3, value: "X" },
    ])
    expect(clock.current).toBe("X")
    expect(clock.update(0.1)).toBe("H")
  })

  it("maps analyser energy to the restrained X/B/C/D fallback set", async () => {
    const lipSync = await loadLipSync()
    expect(lipSync).not.toBeNull()
    if (!lipSync) return

    expect(lipSync.fallbackVisemeFromEnergy(0)).toBe("X")
    expect(lipSync.fallbackVisemeFromEnergy(0.2)).toBe("B")
    expect(lipSync.fallbackVisemeFromEnergy(0.5)).toBe("C")
    expect(lipSync.fallbackVisemeFromEnergy(0.9)).toBe("D")
  })

  it("decodes the animated API audio payload without starting playback", async () => {
    const lipSync = await loadLipSync()
    expect(lipSync).not.toBeNull()
    if (!lipSync) return
    const encoded = btoa("RIFF-test-wave")

    const blob = lipSync.audioBlobFromBase64(encoded, "audio/wav")

    expect(blob.type).toBe("audio/wav")
    expect(blob.size).toBe(14)
  })
})

describe("layered face integration", () => {
  const hook = source("./hooks/use-coach-voice.ts")
  const portrait = source("./components/digital-coach.tsx")
  const coachPage = source("./pages/coach/index.tsx")
  const client = source("./api/client.ts")

  it("waits for the animated payload and drives the portrait with audio time", () => {
    expect(client).toContain("/api/coach/tts/animated")
    expect(hook).toContain("fetchCoachAnimatedTTS")
    expect(hook).toContain("audio.currentTime")
    expect(hook).toContain("CoachVisemeClock")
    expect(hook).toContain("cancelAnimationFrame")
    expect(coachPage).toContain('viseme={voice.viseme}')
    expect(coachPage).toContain("正在准备语音与口型")
  })

  it("uses one square coordinate system for independently preloaded face layers", () => {
    expect(portrait).toContain("aspect-square")
    expect(portrait).toContain('data-face-rig="layered"')
    expect(portrait).toContain("FACE_ASSETS")
    expect(portrait).toContain("new Image()")
    expect(portrait).toContain('data-coach-layer="mouth"')
    expect(portrait).toContain('data-coach-layer="eyes-closed"')
    expect(portrait).not.toContain('data-coach-layer="pupils"')
    expect(portrait).toContain('data-coach-layer="brow-thinking"')
  })

  it("freezes facial motion, limits blinking to the stage, and omits gaze tracking", () => {
    expect(portrait).toContain('state === "speaking"')
    expect(portrait).toContain("BLINK_MIN_MS = 3_200")
    expect(portrait).toContain("BLINK_MAX_MS = 5_800")
    expect(portrait).toContain('variant !== "stage" || reducedMotion')
    expect(portrait).not.toContain("pointermove")
    expect(portrait).not.toContain("--coach-pupil-x")
  })

  it("ships aligned WebP layers within a restrained asset budget", () => {
    const assets = [
      "../public/coach/v2/coach-base.webp",
      ..."ABCDEFGHX".split("").map((viseme) => `../public/coach/v2/face/mouth-${viseme}.webp`),
      "../public/coach/v2/face/eyes-blink.webp",
      "../public/coach/v2/face/brow-thinking.webp",
    ]
    let totalBytes = 0
    for (const asset of assets) {
      const path = fileURLToPath(new URL(asset, import.meta.url))
      expect(existsSync(path), asset).toBe(true)
      if (!existsSync(path)) continue
      const data = readFileSync(path)
      totalBytes += statSync(path).size
      expect(data.subarray(0, 4).toString("ascii"), asset).toBe("RIFF")
      expect(data.subarray(8, 12).toString("ascii"), asset).toBe("WEBP")
    }
    expect(totalBytes).toBeLessThan(2_000_000)
  })

  it("keeps the closed consonant A pose visually distinct from resting X", () => {
    const mouthA = readFileSync(fileURLToPath(new URL("../public/coach/v2/face/mouth-A.webp", import.meta.url)))
    const mouthX = readFileSync(fileURLToPath(new URL("../public/coach/v2/face/mouth-X.webp", import.meta.url)))

    expect(mouthA.equals(mouthX)).toBe(false)
  })
})
