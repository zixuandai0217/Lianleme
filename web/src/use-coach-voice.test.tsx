// @vitest-environment jsdom
/* Exercise the coach voice Hook against browser-like audio and request lifecycles. */
import { act, useEffect } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fetchCoachAnimatedTTSPayload } from "@/api/client"
import type { CoachAnimatedTTSResponse } from "@/api/types"
import { useCoachVoice } from "@/hooks/use-coach-voice"

const apiMocks = vi.hoisted(() => ({
  fetchCoachAnimatedTTS: vi.fn(),
}))

vi.mock("@/api", () => apiMocks)

const ANIMATED_PAYLOAD: CoachAnimatedTTSResponse = {
  audio_base64: btoa("RIFF-test-wave"),
  mime_type: "audio/wav",
  duration_seconds: 1,
  mouth_cues: [
    { start: 0, end: 0.1, value: "X" },
    { start: 0.1, end: 0.9, value: "B" },
    { start: 0.9, end: 1, value: "X" },
  ],
  alignment: "rhubarb",
}

class FakeAnalyser {
  /** Supply the analyser surface used by waveform and energy fallback code. */
  fftSize = 256
  smoothingTimeConstant = 0
  frequencyBinCount = 128
  connect = vi.fn()
  getByteFrequencyData = vi.fn((values: Uint8Array<ArrayBuffer>) => values.fill(0))
}

class FakeAudioContext {
  /** Supply a running Web Audio graph without browser playback hardware. */
  state: AudioContextState = "running"
  destination = {}
  analyser = new FakeAnalyser()
  createAnalyser = vi.fn(() => this.analyser)
  createMediaElementSource = vi.fn(() => ({ connect: vi.fn() }))
  resume = vi.fn(async () => undefined)
  close = vi.fn(async () => undefined)
}

class FakeAudio extends EventTarget {
  /** Model the media state and events consumed by the voice Hook. */
  static instances: FakeAudio[] = []
  preload = ""
  src = ""
  currentTime = 0
  paused = true
  ended = false

  constructor() {
    super()
    FakeAudio.instances.push(this)
  }

  play = vi.fn(async () => {
    this.paused = false
    this.ended = false
  })

  pause = vi.fn(() => {
    if (this.paused) return
    this.paused = true
    this.dispatchEvent(new Event("pause"))
  })

  finish() {
    this.paused = true
    this.ended = true
    this.dispatchEvent(new Event("ended"))
  }

  fail() {
    this.paused = true
    this.dispatchEvent(new Event("error"))
  }
}

type CoachVoice = ReturnType<typeof useCoachVoice>

let root: Root | null
let latestVoice: CoachVoice | null
let nextFrame = 1
let frameCallbacks: Map<number, FrameRequestCallback>

function VoiceHarness({ publish }: { publish: (value: CoachVoice) => void }) {
  /** Publish committed Hook results without adding side effects to render. */
  const currentVoice = useCoachVoice()
  useEffect(() => publish(currentVoice), [currentVoice, publish])
  return null
}

function publishVoice(value: CoachVoice): void {
  /** Store the last committed Hook value for test actions and assertions. */
  latestVoice = value
}

function voice(): CoachVoice {
  if (!latestVoice) throw new Error("Voice Hook is not mounted")
  return latestVoice
}

async function mountVoice(): Promise<void> {
  /** Mount one isolated Hook instance and flush its initial effect. */
  const container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
  await act(async () => root?.render(<VoiceHarness publish={publishVoice} />))
}

function pendingRequestSignals(): AbortSignal[] {
  /** Record signals while keeping requests pending until the Hook aborts them. */
  const signals: AbortSignal[] = []
  apiMocks.fetchCoachAnimatedTTS.mockImplementation(
    (_text: string, signal?: AbortSignal) => new Promise((_resolve, reject) => {
      if (!signal) return
      signals.push(signal)
      signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })
    }),
  )
  return signals
}

function advanceVisemeFrame(audio: FakeAudio, currentTime: number): void {
  /** Advance the fake media clock and execute its next scheduled face frame. */
  audio.currentTime = currentTime
  const next = frameCallbacks.entries().next().value
  if (!next) throw new Error("No facial animation frame is scheduled")
  const [id, callback] = next
  frameCallbacks.delete(id)
  callback(0)
}

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  root = null
  latestVoice = null
  nextFrame = 1
  frameCallbacks = new Map()
  FakeAudio.instances = []
  apiMocks.fetchCoachAnimatedTTS.mockReset()
  vi.stubGlobal("Audio", FakeAudio)
  vi.stubGlobal("AudioContext", FakeAudioContext)
  vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
    const id = nextFrame++
    frameCallbacks.set(id, callback)
    return id
  }))
  vi.stubGlobal("cancelAnimationFrame", vi.fn((id: number) => frameCallbacks.delete(id)))
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })))
  vi.stubGlobal("localStorage", {
    getItem: vi.fn(() => null),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  })
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:coach-voice"),
  })
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  })
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("useCoachVoice request lifecycle", () => {
  it("aborts the active animated request when playback is paused", async () => {
    const signals = pendingRequestSignals()
    await mountVoice()

    act(() => void voice().play("message-1", "Keep moving"))
    await act(async () => undefined)

    expect(signals).toHaveLength(1)
    await act(async () => voice().pause())
    expect(signals[0].aborted).toBe(true)
    expect(voice().status).toBe("paused")
    expect(voice().viseme).toBe("X")
  })

  it("aborts the previous request when a different message is selected", async () => {
    const signals = pendingRequestSignals()
    await mountVoice()

    act(() => void voice().play("message-1", "First cue"))
    await act(async () => undefined)
    act(() => void voice().play("message-2", "Second cue"))
    await act(async () => undefined)

    expect(signals).toHaveLength(2)
    expect(signals[0].aborted).toBe(true)
    expect(signals[1].aborted).toBe(false)
  })

  it("aborts the active request when the Hook unmounts", async () => {
    const signals = pendingRequestSignals()
    await mountVoice()

    act(() => void voice().play("message-1", "Unmount cue"))
    await act(async () => undefined)
    expect(signals).toHaveLength(1)

    await act(async () => root?.unmount())
    root = null
    expect(signals[0].aborted).toBe(true)
  })
})

describe("useCoachVoice media lifecycle", () => {
  it("returns to rest when the media element pauses or fails", async () => {
    apiMocks.fetchCoachAnimatedTTS.mockResolvedValue(ANIMATED_PAYLOAD)
    await mountVoice()
    await act(async () => voice().play("message-1", "Speak now"))

    const audio = FakeAudio.instances[0]
    expect(voice().status).toBe("playing")
    expect(voice().viseme).toBe("X")
    await act(async () => advanceVisemeFrame(audio, 0.2))
    expect(voice().viseme).toBe("B")

    await act(async () => audio.pause())
    expect(voice().status).toBe("paused")
    expect(voice().viseme).toBe("X")

    await act(async () => voice().play("message-1", "Speak now"))
    await act(async () => advanceVisemeFrame(audio, 0.2))
    expect(voice().viseme).toBe("B")
    await act(async () => audio.fail())
    expect(voice().status).toBe("error")
    expect(voice().viseme).toBe("X")
  })

  it("returns to idle rest when playback ends", async () => {
    apiMocks.fetchCoachAnimatedTTS.mockResolvedValue(ANIMATED_PAYLOAD)
    await mountVoice()
    await act(async () => voice().play("message-1", "Finish cue"))

    await act(async () => FakeAudio.instances[0].finish())

    expect(voice().status).toBe("idle")
    expect(voice().activeId).toBeNull()
    expect(voice().viseme).toBe("X")
  })

  it("keeps the mouth at rest when reduced motion is preferred", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })))
    apiMocks.fetchCoachAnimatedTTS.mockResolvedValue(ANIMATED_PAYLOAD)
    await mountVoice()

    await act(async () => voice().play("message-1", "Reduced motion cue"))

    expect(voice().status).toBe("playing")
    expect(voice().viseme).toBe("X")
    expect(requestAnimationFrame).not.toHaveBeenCalled()
  })
})

describe("animated TTS client", () => {
  it("passes the caller AbortSignal to fetch", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(ANIMATED_PAYLOAD), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }))
    vi.stubGlobal("fetch", fetchMock)
    const controller = new AbortController()

    await fetchCoachAnimatedTTSPayload("Keep moving", controller.signal)

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/coach/tts/animated",
      expect.objectContaining({ signal: controller.signal }),
    )
  })
})
