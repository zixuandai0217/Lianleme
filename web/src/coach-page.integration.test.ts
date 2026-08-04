/* Verify that the coach page keeps its conversation, voice, and accessibility workflows. */
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

// Read a source file for page-level integration assertions.
const source = (relativePath: string) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8")

const coachPage = source("./pages/coach/index.tsx")
const app = source("./App.tsx")
const client = source("./api/client.ts")
const voiceHook = source("./hooks/use-coach-voice.ts")

describe("AI coach page", () => {
  it("restores history, workout context, streaming AI, and coach voice", () => {
    expect(coachPage).toContain("DigitalCoach")
    expect(coachPage).toContain("getChatHistory")
    expect(coachPage).toContain("getTodayWorkout")
    expect(coachPage).toContain("getCoachTTSStatus")
    expect(coachPage).toContain("streamFetch")
    expect(coachPage).toContain('/api/coach/chat/stream')
    expect(coachPage).toContain("useCoachVoice")
    expect(app).toContain('lazy(() => import("@/pages/coach"))')
    expect(client).toContain("signal?: AbortSignal")
    expect(coachPage).toContain("streamAbortRef")
    expect(voiceHook).toContain("mountedRef")
    expect(voiceHook).toContain("prepare")
  })

  it("presents the coach as a live character instead of a WebGL demo", () => {
    expect(coachPage).toContain("AI Coach / Live")
    expect(coachPage).toContain("POWER COACH / LIVE")
    expect(coachPage).not.toContain("ROCK MODE")
    expect(coachPage).not.toContain("AI Coach / 3D")
  })

  it("offers explicit speech input and announces live state changes", () => {
    expect(coachPage).toContain("SpeechRecognition")
    expect(coachPage).toContain("webkitSpeechRecognition")
    expect(coachPage).toContain('aria-live="polite"')
    expect(coachPage).toContain('speech.listening ? "停止语音输入" : "开始语音输入"')
    expect(coachPage).toContain('bg-[#ff6a00] text-[#1d211f]')
    expect(coachPage).not.toContain('bg-[#ff6a00] text-white')
    expect(coachPage).toContain('text-[#a63d00]')
    expect(coachPage).toContain('text-[#626a65]')
    expect(coachPage).toContain('role="log"')
    expect(coachPage).toContain('aria-live="off"')
    expect(coachPage).toContain("announcement")
    expect(coachPage).toContain("transcriptFromSpeechResults")
  })
})
