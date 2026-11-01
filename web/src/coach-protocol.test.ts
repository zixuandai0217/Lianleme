/* Behavioral coverage for the React-free coach stream protocol layer. */
import { afterEach, describe, expect, it, vi } from "vitest"
import {
  abortCoachTurn,
  applyCoachEvents,
  applyCoachEvent,
  createCoachFrameDecoder,
  createCoachTurnState,
  EMPTY_COACH_REPLY,
  settleCoachTurn,
  startCoachTurn,
  streamCoachTurn,
  type CoachEvent,
  type CoachTurnState,
} from "./lib/coach-protocol"

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Encode one event the way the backend frames it. */
const frame = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`

const turnStarted = (turnId: string) => ({
  type: "turn_started",
  protocol: 1,
  turn_id: turnId,
  message_id: `message-${turnId}`,
})

/** Feed raw SSE text into a fresh decoder and collect every event. */
function decodeAll(chunks: string[]): CoachEvent[] {
  const decoder = createCoachFrameDecoder()
  const events: CoachEvent[] = []
  for (const chunk of chunks) events.push(...decoder.push(chunk))
  events.push(...decoder.end())
  return events
}

/** Reduce raw frames onto a fresh (or provided) turn, as the page does. */
function reduceBody(
  chunks: string[],
  state: CoachTurnState = startCoachTurn(),
): CoachTurnState {
  return applyCoachEvents(state, decodeAll(chunks))
}

const streamBody = [
  ": keep-alive\n\n",
  frame(turnStarted("turn-1")),
  frame({ type: "state", coach_state: "count" }),
  frame({ type: "message_chunk", text: "先开肩，homie。\n" }),
  frame({ type: "actions", actions: [{ label: "加一组", prompt: "再加一组卧推" }] }),
  frame({ type: "message_chunk", text: "然后上杠铃。" }),
  ": ping\n",
  frame({ type: "done", finish_reason: "complete" }),
].join("")

describe("coach frame decoder", () => {
  it("produces the same event sequence however the transport splits frames", () => {
    const expected = decodeAll([streamBody])

    expect(expected.map((event) => event.type)).toEqual([
      "turn_started",
      "state",
      "message_chunk",
      "actions",
      "message_chunk",
      "done",
    ])
    expect(decodeAll([streamBody])).toEqual(expected)

    // A frame may be cut at any byte position.
    for (let cut = 0; cut <= streamBody.length; cut += 1) {
      expect(decodeAll([streamBody.slice(0, cut), streamBody.slice(cut)])).toEqual(expected)
    }

    // One character per read, and several frames in one read, must agree too.
    expect(decodeAll(streamBody.split(""))).toEqual(expected)
    const sevenByteChunks: string[] = []
    for (let index = 0; index < streamBody.length; index += 7) {
      sevenByteChunks.push(streamBody.slice(index, index + 7))
    }
    expect(decodeAll(sevenByteChunks)).toEqual(expected)
  })

  it("ignores comments, unknown event types, and malformed frames", () => {
    const body = [
      ": heartbeat\n\n",
      frame({ type: "telemetry", value: 1 }),
      "data: not-json\n\n",
      'event: message\ndata: {"type":"message_chunk","text":"收到"}\n\n',
      frame({ type: "message_chunk", text: "收到", extra_field: true }),
      frame({ type: "done", finish_reason: "complete" }),
    ].join("")

    expect(decodeAll([body]).map((event) => event.type)).toEqual([
      "message_chunk",
      "message_chunk",
      "done",
    ])
  })

  it("degrades frames with missing fields instead of throwing", () => {
    const body = [
      frame({ type: "turn_started" }),
      frame({ type: "message_chunk" }),
      frame({ type: "state" }),
      frame({ type: "actions" }),
      frame({ type: "error" }),
      frame({ type: "done" }),
      "data: \n\n",
      "data: {}\n\n",
    ].join("")
    const events = decodeAll([body])

    expect(events.map((event) => event.type)).toEqual(["turn_started", "error", "done"])
    const [started, error, done] = events
    expect(started).toMatchObject({ type: "turn_started", turnId: "" })
    expect(error).toMatchObject({ type: "error", code: "internal" })
    expect(error.type === "error" && error.message.length).toBeGreaterThan(0)
    expect(done).toMatchObject({ type: "done", finishReason: "truncated" })
  })

  it("flushes a final frame that arrived without its trailing blank line", () => {
    const events = decodeAll([`data: {"type":"done","finish_reason":"complete"}`])
    expect(events).toEqual([{ type: "done", finishReason: "complete" }])
  })
})

describe("coach turn reducer", () => {
  it("reduces a full turn into body, coach state, quick actions, and finish reason", () => {
    const turn = reduceBody([streamBody])

    expect(turn.status).toBe("idle")
    expect(turn.body).toBe("先开肩，homie。\n然后上杠铃。")
    expect(turn.coachState).toBe("count")
    expect(turn.actions).toEqual([{ label: "加一组", prompt: "再加一组卧推" }])
    expect(turn.finishReason).toBe("complete")
    expect(turn.error).toBeNull()
    expect(turn.turnId).toBe("turn-1")
  })

  it("starts in thinking and switches to streaming on the opening frame", () => {
    const thinking = startCoachTurn(createCoachTurnState())
    expect(thinking.status).toBe("thinking")
    expect(thinking.body).toBe("")

    const streaming = applyCoachEvent(thinking, decodeAll([frame(turnStarted("turn-a"))])[0])
    expect(streaming.status).toBe("streaming")
    expect(streaming.turnId).toBe("turn-a")
  })

  it("keeps the last coach state and never lets a stale state win", () => {
    const turn = reduceBody([
      frame(turnStarted("turn-b")),
      frame({ type: "state", coach_state: "guide" }),
      frame({ type: "state", coach_state: "rest" }),
      frame({ type: "message_chunk", text: "喘口气" }),
      frame({ type: "done", finish_reason: "complete" }),
    ])

    expect(turn.coachState).toBe("rest")
  })

  it("keeps the error out of the bubble and settles through done", () => {
    const turn = reduceBody([
      frame(turnStarted("turn-c")),
      frame({ type: "message_chunk", text: "先来一组" }),
      frame({ type: "error", code: "provider_unavailable", message: "检查 Key" }),
      frame({ type: "message_chunk", text: "不该出现的正文" }),
      frame({ type: "done", finish_reason: "error" }),
    ])

    expect(turn.body).toBe("先来一组")
    expect(turn.status).toBe("error")
    expect(turn.error).toEqual({ code: "provider_unavailable", message: "检查 Key" })
    expect(turn.finishReason).toBe("error")
  })

  it("drops a late, non-current turn instead of polluting the bubble", () => {
    let state = reduceBody([
      frame(turnStarted("turn-current")),
      frame({ type: "message_chunk", text: "我在" }),
    ])
    expect(state.turnId).toBe("turn-current")

    state = reduceBody(
      [
        frame(turnStarted("turn-old")),
        frame({ type: "message_chunk", text: "旧作" }),
        frame({ type: "done", finish_reason: "complete" }),
      ],
      state,
    )
    expect(state.turnId).toBe("turn-current")
    expect(state.body).toBe("我在")
    expect(state.status).toBe("streaming")
    expect(state.finishReason).toBeNull()

    // The stale tail's done ends the ignore window; the current turn continues.
    state = reduceBody(
      [
        frame({ type: "message_chunk", text: "，接着说" }),
        frame({ type: "done", finish_reason: "complete" }),
      ],
      state,
    )
    expect(state.body).toBe("我在，接着说")
    expect(state.status).toBe("idle")
  })

  it("keeps the first terminal frame when done repeats or arrives out of order", () => {
    const turn = reduceBody([
      frame(turnStarted("turn-d")),
      frame({ type: "message_chunk", text: "收工" }),
      frame({ type: "done", finish_reason: "complete" }),
      frame({ type: "done", finish_reason: "error" }),
      frame({ type: "message_chunk", text: "迟到" }),
    ])

    expect(turn.status).toBe("idle")
    expect(turn.finishReason).toBe("complete")
    expect(turn.body).toBe("收工")
    expect(turn.error).toBeNull()
  })

  it("never leaves an empty bubble when a complete turn has no readable body", () => {
    const turn = reduceBody([
      frame(turnStarted("turn-e")),
      frame({ type: "done", finish_reason: "complete" }),
    ])

    expect(turn.status).toBe("idle")
    expect(turn.finishReason).toBe("complete")
    expect(turn.body).toBe(EMPTY_COACH_REPLY)
  })

  it("settles a stream that ends before done as truncated, keeping the body", () => {
    const partial = reduceBody([
      frame(turnStarted("turn-f")),
      frame({ type: "message_chunk", text: "半句话" }),
    ])

    const settled = settleCoachTurn(partial)
    expect(settled.status).toBe("idle")
    expect(settled.finishReason).toBe("truncated")
    expect(settled.body).toBe("半句话")
  })

  it("settles a broken stream that already reported an error as an error", () => {
    const partial = reduceBody([
      frame(turnStarted("turn-g")),
      frame({ type: "error", code: "upstream_timeout", message: "超时了" }),
    ])

    const settled = settleCoachTurn(partial)
    expect(settled.status).toBe("error")
    expect(settled.finishReason).toBe("error")
    expect(settled.error?.code).toBe("upstream_timeout")
  })

  it("marks a user abort without inventing an error or a reply", () => {
    const partial = reduceBody([
      frame(turnStarted("turn-h")),
      frame({ type: "message_chunk", text: "说到一半" }),
    ])

    const aborted = abortCoachTurn(partial)
    expect(aborted.status).toBe("aborted")
    expect(aborted.error).toBeNull()
    expect(aborted.body).toBe("说到一半")

    const later = applyCoachEvents(aborted, decodeAll([frame({ type: "done", finish_reason: "complete" })]))
    expect(later.status).toBe("aborted")
    expect(later.finishReason).toBeNull()
  })
})

describe("coach stream transport", () => {
  it("feeds raw bytes through the decoder and forwards the abort signal", async () => {
    const bytes = new TextEncoder().encode(streamBody)
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(bytes.slice(0, 33))
            controller.enqueue(bytes.slice(33))
            controller.close()
          },
        }),
        { status: 200 },
      ),
    )
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("localStorage", { getItem: () => null })
    const controller = new AbortController()
    const updates: CoachTurnState[] = []

    const final = await streamCoachTurn({
      url: "/api/coach/chat/stream",
      body: { message: "开始" },
      signal: controller.signal,
      onUpdate: (state) => updates.push(state),
    })

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/coach/chat/stream",
      expect.objectContaining({ method: "POST", signal: controller.signal }),
    )
    expect(final.status).toBe("idle")
    expect(final.body).toBe("先开肩，homie。\n然后上杠铃。")
    expect(updates.at(-1)?.status).toBe("idle")
  })

  it("surfaces a pre-stream HTTP failure instead of producing frames", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code: "api_key_required", message: "先配置你的 Key" } }),
          { status: 428 },
        ),
      ),
    )
    vi.stubGlobal("localStorage", { getItem: () => null })

    await expect(
      streamCoachTurn({ url: "/api/coach/chat/stream", body: { message: "开始" } }),
    ).rejects.toThrow("先配置你的 Key")
  })
})
