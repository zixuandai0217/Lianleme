/* 今日三态的纯函数判定：页面只做展示，判定集中在可单测的一处。 */
import { describe, expect, it } from "vitest"
import { resolveTodayState } from "./today-workout"
import type { Exercise, TodayWorkout } from "@/api/types"

const squat: Exercise = {
  name: "深蹲",
  sets: 3,
  reps: "12",
  weight_suggestion: "自重",
  tips: "挺胸收腹",
  rest_seconds: 60,
}

describe("resolveTodayState", () => {
  it("按服务端 status 直接分叉", () => {
    expect(resolveTodayState({ status: "training_day", exercises: [squat] })).toBe("training")
    expect(resolveTodayState({ status: "rest_day", is_rest_day: true, message: "今日休息" })).toBe("rest")
    expect(resolveTodayState({ status: "no_plan", is_rest_day: false })).toBe("no_plan")
  })

  it("拿不到响应时是「不可用」，不谎称无计划也不谎称休息", () => {
    expect(resolveTodayState(null)).toBe("unavailable")
    expect(resolveTodayState(undefined)).toBe("unavailable")
  })

  it("旧服务端没有 status 时按旧字段推断，不把休息日误判成训练日", () => {
    const legacyRest: TodayWorkout = { is_rest_day: true, message: "今日休息，好好恢复" }
    const legacyTraining: TodayWorkout = { is_rest_day: false, exercises: [squat] }

    expect(resolveTodayState(legacyRest)).toBe("rest")
    expect(resolveTodayState(legacyTraining)).toBe("training")
  })

  it("旧响应里既没有休息标记也没有动作清单时归为不可用，而不是渲染空训练日", () => {
    expect(resolveTodayState({})).toBe("unavailable")
    expect(resolveTodayState({ is_rest_day: false, exercises: [] })).toBe("unavailable")
  })
})
