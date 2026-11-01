/* Behavioral coverage for browser speech transcripts and coach presentation states. */
import { describe, expect, it } from "vitest"
import {
  resolveCoachPresentationState,
  transcriptFromSpeechResults,
} from "./components/coach-conversation"

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

})
