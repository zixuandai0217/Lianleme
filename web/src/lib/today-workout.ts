/*
 * 今日三态的纯函数判定。
 *
 * 服务端的 `status` 是唯一权威入口；只有在拿不到 status（旧部署、混合版本）时
 * 才回落到旧字段推断。判定放在这里而不是组件里，是为了让「休息日 / 无计划 /
 * 不可用」这三种空态的产品判断可以被单独断言——它们必须给出不同的用户可见文案，
 * 尤其不能把「还没有计划」显示成「今天休息」。
 */
import type { TodayWorkout } from "@/api/types"

export type TodayState = "training" | "rest" | "no_plan" | "unavailable"

export function resolveTodayState(today: TodayWorkout | null | undefined): TodayState {
  if (!today) return "unavailable"

  switch (today.status) {
    case "training_day":
      return "training"
    case "rest_day":
      return "rest"
    case "no_plan":
      return "no_plan"
  }

  // 兼容没有 status 的旧响应：休息标记优先，其次看有没有动作清单。
  if (today.is_rest_day) return "rest"
  if (today.exercises && today.exercises.length > 0) return "training"
  return "unavailable"
}
