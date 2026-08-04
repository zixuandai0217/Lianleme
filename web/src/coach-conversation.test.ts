/* Behavioral coverage for browser speech transcripts and cancellable coach streams. */
import { afterEach, describe, expect, it, vi } from "vitest"
import { streamFetch } from "./api/client"
import {
  resolveCoachPresentationState,
  transcriptFromSpeechResults,
} from "./components/coach-conversation"

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("coach conversation helpers", () => {
  it("combines the complete cumulative speech-recognition result list", () => {
    const results = {
      0: { 0: { transcript: "开始" } },
      1: { 0: { transcript: "今天的训练" } },
      length: 2,
    }

    expect(transcriptFromSpeechResults(results)).toBe("开始今天的训练")
  })

  it("maps concurrent conversation activity to one deterministic coach state", () => {
    expect(resolveCoachPresentationState("idle", true, "playing")).toBe("listening")
    expect(resolveCoachPresentationState("thinking", false, "playing")).toBe("speaking")
    expect(resolveCoachPresentationState("idle", false, "loading")).toBe("thinking")
    expect(resolveCoachPresentationState("thinking", false, "idle")).toBe("thinking")
    expect(resolveCoachPresentationState("error", false, "idle")).toBe("error")
    expect(resolveCoachPresentationState("idle", false, "paused")).toBe("idle")
  })

  it("forwards an AbortSignal to the streamed request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("data: [DONE]\n\n"))
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("localStorage", { getItem: () => null })
    const controller = new AbortController()

    await streamFetch("/api/coach/chat/stream", {}, () => undefined, () => undefined, controller.signal)

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/coach/chat/stream",
      expect.objectContaining({ signal: controller.signal }),
    )
  })
})
