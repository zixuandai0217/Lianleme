/* Unit + product contracts for coach voice waveform and TTS wiring. */
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"
import { barsFromFrequencyData, truncateForTTS } from "./components/coach-audio"

const source = (relativePath: string) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8")

describe("barsFromFrequencyData", () => {
  it("maps frequency bins into a fixed number of normalized bar heights", () => {
    const data = new Uint8Array([0, 64, 128, 192, 255, 10, 20, 30])
    const bars = barsFromFrequencyData(data, 4)
    expect(bars).toHaveLength(4)
    expect(Math.max(...bars)).toBeLessThanOrEqual(1)
    expect(Math.min(...bars)).toBeGreaterThanOrEqual(0)
    expect(bars[0]).toBe(bars[3])
    expect(bars[1]).toBe(bars[2])
    expect(Math.max(...bars)).toBeGreaterThan(Math.min(...bars))
  })

  it("returns calm baseline bars for empty analyser data", () => {
    const bars = barsFromFrequencyData(new Uint8Array(16), 8)
    expect(bars).toHaveLength(8)
    expect(bars.every((value) => value >= 0.04 && value <= 0.08)).toBe(true)
  })
})

describe("truncateForTTS", () => {
  it("keeps short text intact and trims long coach replies to 500 chars", () => {
    expect(truncateForTTS("hello")).toBe("hello")
    const long = "练".repeat(600)
    expect(truncateForTTS(long).length).toBe(500)
  })
})

describe("coach voice product contract", () => {
  const waveform = source("./components/voice-waveform.tsx")
  const coachPage = source("./pages/coach/index.tsx")
  const voiceHook = source("./hooks/use-coach-voice.ts")
  const api = source("./api/index.ts")
  const client = source("./api/client.ts")

  it("exposes TTS status and binary WAV fetch helpers", () => {
    expect(api).toContain("getCoachTTSStatus")
    expect(api).toContain("fetchCoachTTS")
    expect(client).toContain("/api/coach/tts")
    expect(client).toContain("audio/wav")
  })

  it("renders reduced-motion aware waveform driven by AnalyserNode", () => {
    expect(waveform).toContain("prefers-reduced-motion")
    expect(waveform).toContain("getByteFrequencyData")
    expect(waveform).toContain("#ff6a00")
    expect(waveform).toContain("min-w-0 flex-1")
    expect(waveform).not.toContain("w-72 md:w-96")
  })

  it("integrates TTS playback with the shared 2D coach and waveform analyser", () => {
    expect(coachPage).toContain("DigitalCoach")
    expect(coachPage).toContain('variant="stage"')
    expect(coachPage).toContain("useCoachVoice")
    expect(coachPage).toContain("voice.analyser")
    expect(coachPage).toContain("VoiceWaveform")
  })

  it("cancels stale speech synthesis before it can take over playback", () => {
    expect(voiceHook).toContain("playbackRequestRef")
    expect(voiceHook).toContain("requestId !== playbackRequestRef.current")
    expect(coachPage).toContain('conversationStatus === "thinking" || voice.status === "loading"')
  })
})
