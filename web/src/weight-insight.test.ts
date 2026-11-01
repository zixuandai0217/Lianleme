import { describe, expect, it } from "vitest"

import {
  buildWeightInsightView,
  type WeightInsightWindow,
  type WeightInsights,
  type WeightWeeklyComparison,
} from "@/lib/weight-insight"

function windowView(partial: Partial<WeightInsightWindow> = {}): WeightInsightWindow {
  return {
    days: 30,
    start_date: "2026-02-16",
    end_date: "2026-03-17",
    sample_count: 4,
    change: -1.4,
    direction: "down",
    min: { weight: 70.6, recorded_date: "2026-03-10" },
    max: { weight: 72.0, recorded_date: "2026-02-18" },
    insufficient: false,
    ...partial,
  }
}

function weekView(partial: Partial<WeightWeeklyComparison> = {}): WeightWeeklyComparison {
  return {
    week_start: "2026-02-23",
    week_end: "2026-03-01",
    sample_count: 2,
    weight_change: -0.5,
    training_days: 4,
    relation: "same",
    ...partial,
  }
}

function insightsView(partial: Partial<WeightInsights> = {}): WeightInsights {
  return {
    anchor_date: "2026-03-17",
    is_stale: false,
    stale_days: 1,
    windows: { d7: windowView({ days: 7, change: -0.5 }), d30: windowView() },
    weekly: [weekView()],
    training_data_available: true,
    goal: { mode: "none", verdict: "neutral", reason: "" },
    ...partial,
  }
}

describe("buildWeightInsightView", () => {
  it("renders both windows with signed one-decimal changes and direction words", () => {
    const view = buildWeightInsightView(insightsView())

    expect(view.visible).toBe(true)
    expect(view.windows.map((item) => item.label)).toEqual(["最近 7 天", "最近 30 天"])
    expect(view.windows[0].changeText).toBe("-0.5 kg")
    expect(view.windows[1].changeText).toBe("-1.4 kg")
    expect(view.windows.map((item) => item.directionWord)).toEqual(["下降", "下降"])
    expect(view.headline).toContain("下降")
    expect(view.windows[1].rangeText).toContain("70.6 kg")
    expect(view.windows[1].rangeText).toContain("3月10日")
  })

  it("keeps a flat window at zero without percentage jitter", () => {
    const view = buildWeightInsightView(
      insightsView({
        windows: {
          d7: windowView({ days: 7, change: 0, direction: "flat" }),
          d30: windowView({ change: 0, direction: "flat" }),
        },
      }),
    )

    expect(view.windows[0].changeText).toBe("0.0 kg")
    expect(view.windows[0].directionWord).toBe("持平")
    expect(view.headline).toContain("持平")
    expect(JSON.stringify(view)).not.toContain("NaN")
  })

  it("shows 数据不足 for a short window while the longer window still reports", () => {
    const view = buildWeightInsightView(
      insightsView({
        windows: {
          d7: windowView({ days: 7, sample_count: 1, change: null, direction: "insufficient", insufficient: true }),
          d30: windowView(),
        },
      }),
    )

    expect(view.windows[0].insufficient).toBe(true)
    expect(view.windows[0].changeText).toBeNull()
    expect(view.windows[0].directionWord).toBe("数据不足")
    expect(view.windows[1].changeText).toBe("-1.4 kg")
    expect(view.headline).toContain("30 天")
  })

  it("asks for one more record instead of inventing a direction for a single sample", () => {
    const single = windowView({
      sample_count: 1,
      change: null,
      direction: "insufficient",
      insufficient: true,
      min: { weight: 70.0, recorded_date: "2026-03-15" },
      max: { weight: 70.0, recorded_date: "2026-03-15" },
    })
    const view = buildWeightInsightView(
      insightsView({
        windows: { d7: { ...single, days: 7 }, d30: single },
        weekly: [],
      }),
    )

    expect(view.singleRecordHint).not.toBeNull()
    expect(view.singleRecordHint).toContain("再记一次")
    expect(view.windows.every((item) => item.changeText === null)).toBe(true)
    expect(view.headline).toContain("数据不足")
  })

  it("renders nothing when the user has no record at all", () => {
    const view = buildWeightInsightView(
      insightsView({
        anchor_date: null,
        stale_days: 0,
        windows: {
          d7: windowView({ days: 7, sample_count: 0, change: null, direction: "insufficient", insufficient: true, min: null, max: null }),
          d30: windowView({ sample_count: 0, change: null, direction: "insufficient", insufficient: true, min: null, max: null }),
        },
        weekly: [],
        training_data_available: false,
      }),
    )

    expect(view.visible).toBe(false)
    expect(view.windows).toEqual([])
  })

  it("flags stale data and keeps the conclusion with an anchor caption", () => {
    const view = buildWeightInsightView(
      insightsView({ is_stale: true, stale_days: 12 }),
    )

    expect(view.staleNotice).not.toBeNull()
    expect(view.staleNotice).toContain("12")
    expect(view.caption).toContain("基于最近一次记录")
    expect(view.caption).toContain("3月17日")
    expect(view.windows[1].changeText).toBe("-1.4 kg")
  })

  it("leaves the range text empty when a window has no extreme", () => {
    const view = buildWeightInsightView(
      insightsView({
        windows: {
          d7: windowView({ days: 7, sample_count: 0, change: null, direction: "insufficient", insufficient: true, min: null, max: null }),
          d30: windowView(),
        },
      }),
    )

    expect(view.windows[0].rangeText).toBeNull()
    expect(view.windows[1].rangeText).not.toBeNull()
  })

  it("renders four training weeks as parallel facts only", () => {
    const weeks = [
      weekView({ week_start: "2026-02-23", week_end: "2026-03-01", weight_change: -0.5, training_days: 2, relation: "same" }),
      weekView({ week_start: "2026-03-02", week_end: "2026-03-08", weight_change: 0.4, training_days: 1, relation: "reverse" }),
      weekView({ week_start: "2026-03-09", week_end: "2026-03-15", weight_change: 0, training_days: 0, relation: "flat" }),
      weekView({ week_start: "2026-03-16", week_end: "2026-03-22", weight_change: -0.2, training_days: 2, relation: "same" }),
    ]
    const view = buildWeightInsightView(insightsView({ weekly: weeks }))

    expect(view.weeklyVisible).toBe(true)
    expect(view.weeklyRows).toHaveLength(4)
    expect(view.weeklyRows[0].label).toBe("2月23日–3月1日")
    expect(view.weeklyRows[0].factText).toContain("同期训练 2 天")
    expect(view.weeklyRows[0].factText).toContain("同向")
    expect(view.weeklyRows[1].factText).toContain("反向")
    expect(view.weeklyRows[2].factText).toContain("无明显关系")
    expect(JSON.stringify(view.weeklyRows)).not.toContain("因为")
  })

  it("hides the weekly block when training data is unavailable", () => {
    const view = buildWeightInsightView(
      insightsView({ training_data_available: false, weekly: [] }),
    )

    expect(view.weeklyVisible).toBe(false)
    expect(view.weeklyRows).toEqual([])
    expect(view.windows[1].changeText).toBe("-1.4 kg")
  })

  it("keeps the windows neutral when no goal is configured", () => {
    const view = buildWeightInsightView(insightsView())

    expect(view.goal).toBeNull()
    expect(view.windows.map((item) => item.directionWord)).toEqual(["下降", "下降"])
  })

  it("still reports the 7-day window when the newest record is a few days old", () => {
    const view = buildWeightInsightView(
      insightsView({ anchor_date: "2026-03-15", stale_days: 3 }),
    )

    expect(view.caption).toBeNull()
    expect(view.staleNotice).toBeNull()
    expect(view.windows[0].changeText).toBe("-0.5 kg")
  })

  it("formats the change to a single decimal even for noisy input", () => {
    const view = buildWeightInsightView(
      insightsView({
        windows: {
          d7: windowView({ days: 7, change: -1.44 }),
          d30: windowView({ change: 2.06 }),
        },
      }),
    )

    expect(view.windows[0].changeText).toBe("-1.4 kg")
    expect(view.windows[1].changeText).toBe("+2.1 kg")
  })

  it.each([
    {
      name: "numeric on track",
      goal: { mode: "numeric", verdict: "on_track", reason: "change_matches_target", gap: 4, target_weight: 68, expected_direction: "down" },
      d30: { change: -1.4, direction: "down" },
      headline: "朝目标前进",
      tone: "positive",
      note: "距目标 4.0 kg（目标 68.0 kg） · 最近 30 天下降 1.4 kg",
    },
    {
      name: "numeric off track",
      goal: { mode: "numeric", verdict: "off_track", reason: "change_against_target", gap: 4, target_weight: 68, expected_direction: "down" },
      d30: { change: 1.4, direction: "up" },
      headline: "偏离目标",
      tone: "warning",
      note: "距目标 4.0 kg（目标 68.0 kg） · 最近 30 天上升 1.4 kg",
    },
    {
      name: "numeric steady",
      goal: { mode: "numeric", verdict: "steady", reason: "change_within_flat_band", gap: 4, target_weight: 68, expected_direction: "down" },
      d30: { change: 0, direction: "flat" },
      headline: "基本持平",
      tone: "neutral",
      note: "距目标 4.0 kg（目标 68.0 kg） · 最近 30 天持平 0.0 kg",
    },
    {
      name: "numeric insufficient",
      goal: { mode: "numeric", verdict: "insufficient", reason: "insufficient_samples", gap: 4, target_weight: 68, expected_direction: "down" },
      d30: { change: null, direction: "insufficient", insufficient: true },
      headline: "数据不足，暂不判断",
      tone: "neutral",
      note: "距目标 4.0 kg（目标 68.0 kg） · 最近 30 天数据不足",
    },
  ])("maps $name to the goal view model", ({ goal, d30, headline, tone, note }) => {
    const view = buildWeightInsightView(
      insightsView({
        goal,
        windows: { d7: windowView({ days: 7 }), d30: windowView(d30) },
      }),
    )

    expect(view.goal?.headline).toBe(headline)
    expect(view.goal?.note).toBe(note)
    expect(view.goal?.tone).toBe(tone)
  })

  it("keeps the window cards neutral instead of reusing the 30-day verdict tone", () => {
    const view = buildWeightInsightView(
      insightsView({
        goal: { mode: "numeric", verdict: "off_track", reason: "change_against_target", gap: 4, target_weight: 68, expected_direction: "down" },
        windows: { d7: windowView({ days: 7, change: -0.4, direction: "down" }), d30: windowView({ change: 1.4, direction: "up" }) },
      }),
    )

    expect(view.goal?.tone).toBe("warning")
    expect(view.windows[0].changeText).toBe("-0.4 kg")
    expect(JSON.stringify(view.windows)).not.toContain("tone")
  })

  it("uses a reached-target headline", () => {
    const view = buildWeightInsightView(
      insightsView({
        goal: { mode: "numeric", verdict: "on_track", reason: "target_reached", gap: 0, target_weight: 72 },
      }),
    )
    expect(view.goal?.headline).toBe("已达目标体重")
    expect(view.goal?.note).toContain("已到目标体重（目标 72.0 kg）")
  })

  it("treats direction goals according to their expected direction", () => {
    const gaining = buildWeightInsightView(
      insightsView({
        goal: { mode: "direction", verdict: "on_track", reason: "change_matches_goal_direction", goal_label: "增肌", expected_direction: "up" },
        windows: { d7: windowView({ days: 7, change: 0.2, direction: "up" }), d30: windowView({ change: 1.2, direction: "up" }) },
      }),
    )
    expect(gaining.goal?.tone).toBe("positive")
    expect(gaining.goal?.headline).toBe("朝目标前进（按目标方向推断）")
    expect(gaining.goal?.note).toBe("增肌期望上升 · 最近 30 天上升 1.2 kg")

    const losing = buildWeightInsightView(
      insightsView({
        goal: { mode: "direction", verdict: "off_track", reason: "change_against_goal_direction", goal_label: "减脂", expected_direction: "down" },
        windows: { d7: windowView({ days: 7, change: 0.2, direction: "up" }), d30: windowView({ change: 1.2, direction: "up" }) },
      }),
    )
    expect(losing.goal?.tone).toBe("warning")
    expect(losing.goal?.headline).toBe("偏离目标（按目标方向推断）")
  })

  it("keeps 塑形 within its flat band neutral and steady", () => {
    const view = buildWeightInsightView(
      insightsView({
        goal: { mode: "direction", verdict: "steady", reason: "hold_within_band", goal_label: "塑形", expected_direction: "hold" },
        windows: { d7: windowView({ days: 7, change: 0.1, direction: "up" }), d30: windowView({ change: 0.2, direction: "up" }) },
      }),
    )
    expect(view.goal?.headline).toBe("基本持平（按目标方向推断）")
    expect(view.goal?.tone).toBe("neutral")
    expect(view.goal?.note).toContain("塑形期望维持")
  })

  it("treats 提升体能 like 塑形 but warns when the change drifts outside the band", () => {
    const view = buildWeightInsightView(
      insightsView({
        goal: { mode: "direction", verdict: "off_track", reason: "drift_outside_band", goal_label: "提升体能", expected_direction: "hold" },
        windows: { d7: windowView({ days: 7, change: -0.6, direction: "down" }), d30: windowView({ change: -1.2, direction: "down" }) },
      }),
    )

    expect(view.goal?.headline).toBe("偏离目标（按目标方向推断）")
    expect(view.goal?.tone).toBe("warning")
    expect(view.goal?.note).toContain("提升体能期望维持")
    expect(view.goal?.note).toContain("最近 30 天下降 1.2 kg")
  })

  it("never renders an empty goal block for an unknown verdict", () => {
    const view = buildWeightInsightView(
      insightsView({
        goal: { mode: "numeric", verdict: "unknown_code", reason: "future_reason", gap: 3, target_weight: 68 },
      }),
    )
    expect(view.goal).toBeNull()
  })
})

describe("weekly rows for incomplete weeks", () => {
  it("describes the missing change instead of showing a number", () => {
    const view = buildWeightInsightView(
      insightsView({
        weekly: [
          weekView({
            sample_count: 1,
            weight_change: null,
            training_days: 3,
            relation: "insufficient",
          }),
        ],
      }),
    )

    expect(view.weeklyRows[0].factText).toContain("记录不足")
    expect(view.weeklyRows[0].factText).toContain("同期训练 3 天")
    expect(view.weeklyRows[0].factText).not.toMatch(/[+-]\d\.\d kg/)
  })
})
