import { describe, expect, it } from "vitest"
import {
  deriveWeeklyGoal,
  describeAdjustment,
  describeGenerationBasis,
  describeVolume,
  normalizeFocus,
  summarizeVolume,
} from "./plan-explanation"
import type { PlanExplanation, TrainingPlan } from "@/api/types"

function plan(overrides: Partial<TrainingPlan> = {}): TrainingPlan {
  return {
    id: 1,
    user_id: 1,
    week_start: "2026-03-16",
    difficulty_factor: 1.2,
    status: "active",
    weekly_plan: [
      {
        day: 1,
        focus: "push",
        estimated_duration: 40,
        is_rest_day: false,
        exercises: [
          { name: "卧推", sets: 3, reps: "8-12", weight_suggestion: "40%", tips: "", rest_seconds: 90 },
          { name: "肩推", sets: 2, reps: "10", weight_suggestion: "轻", tips: "", rest_seconds: 60 },
        ],
      },
      {
        day: 2,
        focus: "腿部",
        estimated_duration: 50,
        is_rest_day: false,
        exercises: [
          { name: "深蹲", sets: 4, reps: "8", weight_suggestion: "60%", tips: "", rest_seconds: 120 },
        ],
      },
      {
        day: 3,
        focus: "恢复",
        estimated_duration: 0,
        is_rest_day: true,
        exercises: [],
      },
    ],
    ...overrides,
  }
}

describe("summarizeVolume", () => {
  it("按训练日聚合动作数、组数、时长、重点次数与最重的一天", () => {
    const summary = summarizeVolume(plan())

    expect(summary.trainingDays).toBe(2)
    expect(summary.restDays).toBe(1)
    expect(summary.exerciseCount).toBe(3)
    expect(summary.totalSets).toBe(9)
    expect(summary.totalMinutes).toBe(90)
    expect(summary.heaviestDay).toMatchObject({ day: 1, label: "周一", totalSets: 5 })
    expect(summary.focusCounts).toEqual([
      { category: "上肢推", label: "上肢推", count: 1 },
      { category: "腿部", label: "腿部", count: 1 },
    ])
    expect(summary.isRecoveryWeek).toBe(false)
  })

  it("同一天同一分类只计一次（不按动作条目重复计）", () => {
    const summary = summarizeVolume(
      plan({
        weekly_plan: [
          {
            day: 1,
            focus: "胸",
            estimated_duration: 30,
            is_rest_day: false,
            exercises: [
              { name: "卧推", sets: 3, reps: "8", weight_suggestion: "", tips: "", rest_seconds: 60 },
              { name: "飞鸟", sets: 3, reps: "12", weight_suggestion: "", tips: "", rest_seconds: 60 },
            ],
          },
        ],
      }),
    )

    expect(summary.focusCounts).toEqual([{ category: "上肢推", label: "上肢推", count: 1 }])
  })

  it("空计划与全体息计划都输出恢复周，且不出现除零", () => {
    expect(summarizeVolume(null).isRecoveryWeek).toBe(true)
    expect(summarizeVolume(null).totalSets).toBe(0)
    expect(describeVolume(summarizeVolume(null))).toContain("0 个训练日")
    expect(describeVolume(summarizeVolume(null))).toContain("0 组")
    expect(describeVolume(summarizeVolume(null))).toContain("本周为恢复周")

    const allRest = summarizeVolume(
      plan({
        weekly_plan: [
          { day: 1, focus: "恢复", estimated_duration: 0, is_rest_day: true, exercises: [] },
        ],
      }),
    )
    expect(allRest.isRecoveryWeek).toBe(true)
    expect(allRest.restDays).toBe(1)
  })

  it("训练量文案包含关键数字与最重的一天", () => {
    const text = describeVolume(summarizeVolume(plan()))
    expect(text).toContain("2 个训练日")
    expect(text).toContain("9 组")
    expect(text).toContain("最重的一天：周一")
    expect(text).toContain("上肢推 1 次")
  })
})

describe("normalizeFocus", () => {
  it("英文分类键归一为中文标签与稳定分类", () => {
    expect(normalizeFocus("PUSH")).toEqual({ label: "上肢推", category: "上肢推" })
    expect(normalizeFocus("full_body")).toEqual({ label: "全身", category: "全身" })
    expect(normalizeFocus("recovery")).toEqual({ label: "恢复", category: "恢复" })
  })

  it("已知中文直接使用并归入稳定分类", () => {
    expect(normalizeFocus("胸背")).toEqual({ label: "胸背", category: "上肢推" })
    expect(normalizeFocus("核心稳定")).toEqual({ label: "核心稳定", category: "核心" })
    expect(normalizeFocus("腿部力量")).toEqual({ label: "腿部力量", category: "腿部" })
  })

  it("未知值原样保留且归入「其他」，空值不产生空白标签", () => {
    expect(normalizeFocus("瑜伽")).toEqual({ label: "瑜伽", category: "其他" })
    expect(normalizeFocus("")).toEqual({ label: "未标注重点", category: "其他" })
    expect(normalizeFocus(null).label).not.toBe("")
  })

  it("四种取值混在一起也各自归一，分类聚合不丢标签", () => {
    const summary = summarizeVolume(
      plan({
        weekly_plan: [
          {
            day: 1,
            focus: "push",
            estimated_duration: 30,
            is_rest_day: false,
            exercises: [{ name: "卧推", sets: 3, reps: "8", weight_suggestion: "", tips: "", rest_seconds: 60 }],
          },
          {
            day: 2,
            focus: "胸",
            estimated_duration: 30,
            is_rest_day: false,
            exercises: [{ name: "飞鸟", sets: 3, reps: "12", weight_suggestion: "", tips: "", rest_seconds: 60 }],
          },
          {
            day: 3,
            focus: "瑜伽",
            estimated_duration: 30,
            is_rest_day: false,
            exercises: [{ name: "拜日式", sets: 1, reps: "5", weight_suggestion: "", tips: "", rest_seconds: 30 }],
          },
          { day: 4, focus: "恢复", estimated_duration: 0, is_rest_day: true, exercises: [] },
        ],
      }),
    )

    expect(summary.focusCounts).toEqual([
      { category: "上肢推", label: "上肢推", count: 2 },
      { category: "其他", label: "其他", count: 1 },
    ])
    expect(summary.restDays).toBe(1)
  })
})

describe("deriveWeeklyGoal", () => {
  const explanation = (generation: PlanExplanation["generation"]): PlanExplanation => ({ generation })

  it("生成时档案目标优先", () => {
    const goal = deriveWeeklyGoal(explanation({ profile_goal: "增肌" }), "减脂")
    expect(goal).toEqual({ text: "本周目标：增肌", source: "generation" })
  })

  it("没有生成目标时用当前档案目标并标注推断", () => {
    const goal = deriveWeeklyGoal(explanation({}), "减脂")
    expect(goal.text).toBe("本周目标：减脂（按当前档案推断）")
    expect(goal.source).toBe("current")
  })

  it("再退一步用弱势肌群概括", () => {
    const goal = deriveWeeklyGoal(explanation({ weak_muscles: ["背部", "核心"] }), null)
    expect(goal.text).toBe("本周重点补强：背部、核心")
    expect(goal.source).toBe("weak_muscles")
  })

  it("全都没有时给出均衡发展", () => {
    expect(deriveWeeklyGoal(null, null)).toEqual({
      text: "本周以均衡发展为主",
      source: "balanced",
    })
  })
})

describe("解释字段的降级文案", () => {
  it("没有解释数据：说明生成于字段上线之前", () => {
    expect(describeGenerationBasis(null)).toContain("生成于解释字段上线之前")
    expect(describeAdjustment(null)).toContain("生成于解释字段上线之前")
  })

  it("有解释但本周没有调整：明确说没有调整记录", () => {
    const text = describeAdjustment({ generation: { body_type: "mesomorph" } })
    expect(text).toContain("本周还没有调整记录")
    expect(text).not.toContain("上线之前")
  })

  it("方向为 keep 时说保持原强度，并与前两档文案不同", () => {
    const text = describeAdjustment({
      generation: {},
      latest_adjustment: {
        direction: "keep",
        trigger: "completion_rate",
        completion_rate: 0.6,
        occurred_at: "2026-03-16T05:00:00Z",
        reason: "完成率 60%，保持当前难度",
      },
    })
    expect(text).toContain("本周保持原强度")
    expect(text).not.toContain("还没有调整记录")
  })

  it("加量/减量显示方向、理由与触发完成率", () => {
    const text = describeAdjustment({
      generation: {},
      latest_adjustment: {
        direction: "increase",
        trigger: "completion_rate",
        completion_rate: 0.85,
        occurred_at: "2026-03-16T05:00:00Z",
        reason: "完成率 85%，表现优秀",
      },
    })
    expect(text).toContain("上调强度")
    expect(text).toContain("完成率 85%")
  })
})
