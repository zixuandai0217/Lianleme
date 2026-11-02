/* 管理端展示用的时间/数值格式化：纯函数，页面只负责摆放。 */

/** 按浏览器本地时间展示；缺失或非法值不伪装成日期。 */
export function formatAdminDateTime(value?: string | null): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("zh-CN", { hour12: false })
}

export function formatAdminDate(value?: string | null): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString("zh-CN")
}

/** 区分 0 与缺失：打卡 0 次是真实数据，不能显示成「—」。 */
export function formatAdminNumber(value?: number | null): string {
  if (value === null || value === undefined) return "—"
  return String(value)
}
