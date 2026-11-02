import { describe, expect, it } from "vitest"
import {
  SKIP_REASONS,
  canCompleteSet,
  exerciseVolumeLabel,
  nextExerciseHint,
  overallProgressLabel,
  restCountdownLabel,
  setProgressLabel,
} from "./workout-session"
import type { SessionExercise, WorkoutSessionView } from "@/api/types"

function exercise(overrides: Partial<SessionExercise> = {}): SessionExercise {
  return {
    index: 0,
    order: 1,
    name: "卧推",
    sets: 4,
    reps: "8-12",
    weight_suggestion: "体重 40%",
    tips: "肩胛收紧",
    rest_seconds: 90,
    completed_sets: 1,
    skipped: false,
    skip_reason: null,
    status: "pending",
    target_set_number: 2,
    ...overrides,
  }
}

function view(overrides: Partial<WorkoutSessionView> = {}): WorkoutSessionView {
  return {
    session_id: "ws_1",
    user_id: 1,
    status: "in_progress",
    session_date: "2026-03-18",
    started_at: "2026-03-18T12:00:00Z",
    last_activity_at: "2026-03-18T12:05:00Z",
    progress: { completed_sets: 2, total_sets: 7, percent: 29 },
    exercises: [exercise()],
    current_exercise: exercise(),
    next_exercise: exercise({ index: 1, name: "划船" }),
    finished: false,
    can_checkin: false,
    ...overrides,
  }
}

describe("workout session view helpers", () => {
  it("组内进度按服务端给的下一组序号显示", () => {
    expect(setProgressLabel(exercise({ target_set_number: 2, sets: 4 }))).toBe("第 2/4 组")
    expect(setProgressLabel(exercise({ status: "completed", target_set_number: null }))).toBeNull()
    expect(setProgressLabel(exercise({ status: "skipped", skipped: true }))).toBeNull()
  })

  it("整体进度与动作规格文案", () => {
    expect(overallProgressLabel({ completed_sets: 2, total_sets: 7, percent: 29 })).toBe("已练 2/7 组")
    expect(exerciseVolumeLabel(exercise())).toBe("4 组 × 8-12")
  })

  it("休息倒计时格式化为两位秒数，且不为负", () => {
    expect(restCountdownLabel(90)).toBe("休息 01:30")
    expect(restCountdownLabel(5)).toBe("休息 00:05")
    expect(restCountdownLabel(-3)).toBe("休息 00:00")
  })

  it("下一个动作提示只看服务端视图", () => {
    expect(nextExerciseHint(view())).toBe("下一个动作：划船")
    expect(nextExerciseHint(view({ next_exercise: null }))).toBeNull()
  })

  it("休息中不显示完成一组，没有当前动作时也不显示", () => {
    expect(canCompleteSet(view(), false)).toBe(true)
    expect(canCompleteSet(view(), true)).toBe(false)
    expect(canCompleteSet(view({ current_exercise: null, finished: true }), false)).toBe(false)
  })

  it("跳过原因是固定、非空且不重复的文案集合", () => {
    expect(SKIP_REASONS.length).toBeGreaterThanOrEqual(3)
    for (const reason of SKIP_REASONS) {
      expect(reason.trim()).toBe(reason)
      expect(reason.length).toBeGreaterThan(1)
    }
    expect(new Set(SKIP_REASONS).size).toBe(SKIP_REASONS.length)
  })
})
