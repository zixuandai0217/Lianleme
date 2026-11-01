import { describe, expect, it, vi } from "vitest"

import type { AnalyzeResultResponse, BodyAnalysisResult } from "@/api/types"
import {
  DEFAULT_POLL_INTERVAL_MS,
  MAX_POLL_ATTEMPTS,
  MAX_POLL_INTERVAL_MS,
  MIN_POLL_INTERVAL_MS,
  isTerminalTaskStatus,
  mapAnalysisTaskStatus,
  pollAnalysisTask,
  resolvePollIntervalMs,
} from "./task-status"

const analysisResult: BodyAnalysisResult = {
  body_type: "mesomorph",
  body_fat_range: "15-20%",
  weak_muscles: ["legs"],
  strengths: ["chest"],
  muscle_scores: { chest: 8 },
  summary: "保持训练。",
}

const taskResponse = (overrides: Partial<AnalyzeResultResponse>): AnalyzeResultResponse => ({
  task_id: "task-1",
  status: "pending",
  ...overrides,
})

const flushSleep = () => vi.fn(async () => undefined)

describe("mapAnalysisTaskStatus", () => {
  it("maps pending and processing to waiting copy with no user action", () => {
    for (const status of ["pending", "processing"] as const) {
      const view = mapAnalysisTaskStatus({ status })

      expect(view.status).toBe(status)
      expect(view.terminal).toBe(false)
      expect(view.keepPolling).toBe(true)
      expect(view.primaryAction).toBeNull()
      expect(view.secondaryAction).toBeNull()
      expect(view.title.length).toBeGreaterThan(0)
      expect(view.description.length).toBeGreaterThan(0)
    }
  })

  it("treats completed as terminal and points at the training plan", () => {
    const view = mapAnalysisTaskStatus({ status: "completed" })

    expect(view.terminal).toBe(true)
    expect(view.keepPolling).toBe(false)
    expect(view.primaryAction?.kind).toBe("generate-plan")
    expect(view.primaryAction?.label).toContain("训练计划")
  })

  it("stops polling on a retryable failure and offers a restart", () => {
    const view = mapAnalysisTaskStatus({
      status: "failed",
      error: { code: "provider_timeout", message: "AI 服务没有及时返回结果。", retryable: true },
    })

    expect(view.terminal).toBe(true)
    expect(view.keepPolling).toBe(false)
    expect(view.retryable).toBe(true)
    expect(view.primaryAction?.kind).toBe("restart")
    expect(view.description).toBe("AI 服务没有及时返回结果。")
  })

  it("does not auto-retry a non-retryable failure", () => {
    const view = mapAnalysisTaskStatus({
      status: "failed",
      error: { code: "image_invalid", message: "照片无法识别。", retryable: false },
    })

    expect(view.terminal).toBe(true)
    expect(view.retryable).toBe(false)
    expect(view.primaryAction).toBeNull()
  })

  it("offers a restart when execution retries are exhausted", () => {
    const view = mapAnalysisTaskStatus({
      status: "failed",
      error: { code: "retry_exhausted", message: "这次分析已经用尽重试次数。", retryable: false },
    })

    expect(view.terminal).toBe(true)
    expect(view.retryable).toBe(true)
    expect(view.primaryAction?.kind).toBe("restart")
  })

  it("treats expired as a terminal state that can be restarted", () => {
    const view = mapAnalysisTaskStatus({ status: "expired" })

    expect(view.terminal).toBe(true)
    expect(view.keepPolling).toBe(false)
    expect(view.retryable).toBe(true)
    expect(view.primaryAction?.kind).toBe("restart")
    expect(view.description).toContain("有效期")
  })

  it("sends key problems to configuration instead of retrying the same failure", () => {
    const view = mapAnalysisTaskStatus({
      status: "failed",
      error: { code: "provider_auth_failed", message: "鉴权失败。", retryable: false },
    })

    expect(view.primaryAction?.kind).toBe("configure-key")
    expect(view.primaryAction?.label).toContain("API Key")
  })

  it("never renders a stack trace or an oversized server message", () => {
    const view = mapAnalysisTaskStatus({
      status: "failed",
      error: {
        code: "internal_error",
        message: "Traceback (most recent call last):\n  File \"provider.py\", line 1",
        retryable: true,
      },
    })

    expect(view.description).not.toContain("Traceback")
    expect(view.description).not.toContain("provider.py")
    expect(view.description.length).toBeLessThan(200)
  })

  it("recognizes every terminal status", () => {
    expect(isTerminalTaskStatus("completed")).toBe(true)
    expect(isTerminalTaskStatus("failed")).toBe(true)
    expect(isTerminalTaskStatus("expired")).toBe(true)
    expect(isTerminalTaskStatus("pending")).toBe(false)
    expect(isTerminalTaskStatus("processing")).toBe(false)
  })
})

describe("resolvePollIntervalMs", () => {
  it("honors the server interval when it is usable", () => {
    expect(resolvePollIntervalMs(7500)).toBe(7500)
  })

  it("falls back to the existing interval when the server omits it", () => {
    expect(resolvePollIntervalMs(undefined)).toBe(DEFAULT_POLL_INTERVAL_MS)
    expect(resolvePollIntervalMs(undefined, 4000)).toBe(4000)
  })

  it("ignores invalid server values", () => {
    expect(resolvePollIntervalMs(0, 3000)).toBe(3000)
    expect(resolvePollIntervalMs(-100, 3000)).toBe(3000)
    expect(resolvePollIntervalMs(Number.NaN, 3000)).toBe(3000)
    expect(resolvePollIntervalMs(Number.POSITIVE_INFINITY, 3000)).toBe(3000)
  })

  it("clamps absurd values so polling neither hot-loops nor stalls for minutes", () => {
    expect(resolvePollIntervalMs(1)).toBe(MIN_POLL_INTERVAL_MS)
    expect(resolvePollIntervalMs(10 * 60 * 1000)).toBe(MAX_POLL_INTERVAL_MS)
  })
})

describe("pollAnalysisTask", () => {
  it("stops after a failed response without scheduling another request", async () => {
    const fetchStatus = vi.fn(async () =>
      taskResponse({
        status: "failed",
        error: { code: "provider_timeout", message: "AI 超时。", retryable: true },
      }),
    )
    const sleep = flushSleep()

    const outcome = await pollAnalysisTask({ taskId: "task-1", fetchStatus, sleep })

    expect(outcome.outcome).toBe("failed")
    expect(outcome.error?.code).toBe("provider_timeout")
    expect(fetchStatus).toHaveBeenCalledTimes(1)
    expect(sleep).not.toHaveBeenCalled()
  })

  it("stops after an expired response without scheduling another request", async () => {
    const fetchStatus = vi.fn(async () => taskResponse({ status: "expired" }))
    const sleep = flushSleep()

    const outcome = await pollAnalysisTask({ taskId: "task-1", fetchStatus, sleep })

    expect(outcome.outcome).toBe("expired")
    expect(fetchStatus).toHaveBeenCalledTimes(1)
    expect(sleep).not.toHaveBeenCalled()
  })

  it("returns the result and stops after completion", async () => {
    const fetchStatus = vi.fn(async () =>
      taskResponse({ status: "completed", result: analysisResult }),
    )
    const onUpdate = vi.fn()
    const sleep = flushSleep()

    const outcome = await pollAnalysisTask({ taskId: "task-1", fetchStatus, sleep, onUpdate })

    expect(outcome.outcome).toBe("completed")
    expect(outcome.result).toEqual(analysisResult)
    expect(fetchStatus).toHaveBeenCalledTimes(1)
    expect(sleep).not.toHaveBeenCalled()
    expect(onUpdate).toHaveBeenCalledTimes(1)
  })

  it("uses the server suggested interval instead of the default", async () => {
    const fetchStatus = vi
      .fn<(_taskId: string) => Promise<AnalyzeResultResponse>>()
      .mockResolvedValueOnce(taskResponse({ status: "pending" }))
      .mockResolvedValueOnce(taskResponse({ status: "completed", result: analysisResult }))
    const sleep = flushSleep()

    await pollAnalysisTask({ taskId: "task-1", fetchStatus, sleep, initialIntervalMs: 5000 })

    expect(fetchStatus).toHaveBeenCalledTimes(2)
    expect(sleep).toHaveBeenCalledTimes(1)
    expect(sleep).toHaveBeenCalledWith(5000)
  })

  it("keeps the initial server interval across subsequent waits", async () => {
    const fetchStatus = vi
      .fn<(_taskId: string) => Promise<AnalyzeResultResponse>>()
      .mockResolvedValueOnce(taskResponse({ status: "processing" }))
      .mockResolvedValueOnce(taskResponse({ status: "completed", result: analysisResult }))
    const sleep = flushSleep()

    await pollAnalysisTask({ taskId: "task-1", fetchStatus, sleep, initialIntervalMs: 6000 })

    expect(sleep).toHaveBeenCalledWith(6000)
  })

  it("keeps the attempt cap as a last resort when status never advances", async () => {
    const fetchStatus = vi.fn(async () => taskResponse({ status: "processing" }))
    const sleep = flushSleep()

    const outcome = await pollAnalysisTask({
      taskId: "task-1",
      fetchStatus,
      sleep,
      maxAttempts: 3,
    })

    expect(outcome.outcome).toBe("timeout")
    expect(fetchStatus).toHaveBeenCalledTimes(3)
    expect(sleep).toHaveBeenCalledTimes(2)
    expect(MAX_POLL_ATTEMPTS).toBeGreaterThan(3)
  })

  it("does not return a completed task without a result", async () => {
    const fetchStatus = vi.fn(async () => taskResponse({ status: "completed" }))
    const sleep = flushSleep()

    const outcome = await pollAnalysisTask({ taskId: "task-1", fetchStatus, sleep })

    expect(outcome.outcome).toBe("failed")
    expect(outcome.error?.retryable).toBe(true)
    expect(fetchStatus).toHaveBeenCalledTimes(1)
  })
})
