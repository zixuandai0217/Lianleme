/*
 * 会话页的展示判定（工单 23）。
 *
 * 进度、当前动作、下一组序号都来自服务端视图，这里只做「把数字变成人话」的纯函数，
 * 以及休息倒计时的格式化。页面不做任何本地进度推算——刷新后必须与服务端一致。
 */
import type { SessionExercise, SessionProgressView, WorkoutSessionView } from "@/api/types"

/** 跳过的固定原因（必须选一个才能提交）。 */
export const SKIP_REASONS = ["器械被占", "太累做不动", "动作不会做", "时间不够"] as const

/** 组内进度文案，如「第 2/4 组」；动作已完成或跳过时返回 null。 */
export function setProgressLabel(exercise: SessionExercise | null | undefined): string | null {
  if (!exercise || exercise.status !== "pending") return null
  const target = exercise.target_set_number ?? exercise.completed_sets + 1
  return `第 ${target}/${exercise.sets} 组`
}

/** 整体进度文案，如「已练 2/7 组」。 */
export function overallProgressLabel(progress: SessionProgressView): string {
  return `已练 ${progress.completed_sets}/${progress.total_sets} 组`
}

/** 当前动作的「组数 × 次数」，如「4 组 × 8-12」。 */
export function exerciseVolumeLabel(exercise: SessionExercise): string {
  return `${exercise.sets} 组 × ${exercise.reps}`
}

/** 休息倒计时文案，如「休息 01:30」；秒数归一化为整秒且不为负。 */
export function restCountdownLabel(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(safe / 60)
  const rest = safe % 60
  return `休息 ${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
}

/** 下一个动作的提示；没有下一个动作时返回 null。 */
export function nextExerciseHint(view: WorkoutSessionView): string | null {
  if (!view.next_exercise) return null
  return `下一个动作：${view.next_exercise.name}`
}

/** 是否显示「完成一组」：还有当前动作、且没有在休息倒计时里。 */
export function canCompleteSet(view: WorkoutSessionView, resting: boolean): boolean {
  return view.current_exercise !== null && view.current_exercise !== undefined && !resting
}
