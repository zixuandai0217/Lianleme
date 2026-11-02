/**
 * 管理端用户列表的 URL 状态。
 *
 * URL 查询串与列表请求对象是同一份状态：键名与后端接口参数一一对应，前端不做方言
 * 映射；空值、默认排序、第 1 页与默认每页条数不写进 URL。页面刷新、复制链接与浏览器
 * 前进/后退都只依赖这一个纯函数往返，因此筛选结果可重现。
 *
 * 列出与导出的差异只在分页：导出永远不分页，所以用 buildAdminExportSearch 去掉
 * page / page_size，其余筛选与排序保持完全一致。
 */
import type { AdminUserFlag, AdminUserSort } from "@/api/types"

export const DEFAULT_ADMIN_PAGE = 1
export const DEFAULT_ADMIN_PAGE_SIZE = 20
export const MAX_ADMIN_PAGE_SIZE = 100
export const DEFAULT_ADMIN_SORT: AdminUserSort = "registered_desc"

/** 列表页的全部 URL 可表达状态；筛选为 undefined 表示「不筛选」。 */
export interface AdminUsersRequest {
  q?: string
  has_plan?: boolean
  is_admin?: boolean
  has_api_key?: boolean
  registered_from?: string
  registered_to?: string
  checkins_min?: number
  checkins_max?: number
  active_within_days?: number
  flag?: AdminUserFlag[]
  sort: AdminUserSort
  page: number
  page_size: number
}

export interface AdminSelectOption<T extends string> {
  value: T
  label: string
}

/** 需关注标记的固定枚举顺序：也决定 URL 里重复 flag 的排列顺序。 */
export const ADMIN_FLAG_OPTIONS: AdminSelectOption<AdminUserFlag>[] = [
  { value: "new_no_plan", label: "注册 7 天无计划" },
  { value: "planned_no_checkin", label: "有计划 7 天无打卡" },
  { value: "inactive_14d", label: "14 天无活跃" },
  { value: "never_analyzed", label: "注册 3 天未分析" },
  { value: "api_key_missing", label: "未配置 API Key" },
]

export const ADMIN_SORT_OPTIONS: AdminSelectOption<AdminUserSort>[] = [
  { value: "registered_desc", label: "注册时间（新→旧）" },
  { value: "registered_asc", label: "注册时间（旧→新）" },
  { value: "last_active_desc", label: "最近活跃（近→远）" },
  { value: "last_active_asc", label: "最近活跃（远→近）" },
]

const ADMIN_USER_FLAGS = new Set<string>(ADMIN_FLAG_OPTIONS.map((option) => option.value))
const ADMIN_USER_SORTS = new Set<string>(ADMIN_SORT_OPTIONS.map((option) => option.value))

function isAdminUserFlag(value: string): value is AdminUserFlag {
  return ADMIN_USER_FLAGS.has(value)
}

function isAdminUserSort(value: string): value is AdminUserSort {
  return ADMIN_USER_SORTS.has(value)
}

/** 展示文案：未知值原样回显，避免服务端新增枚举时页面空白。 */
export function adminFlagLabel(flag: AdminUserFlag): string {
  return ADMIN_FLAG_OPTIONS.find((option) => option.value === flag)?.label ?? flag
}

export function adminSortLabel(sort: AdminUserSort): string {
  return ADMIN_SORT_OPTIONS.find((option) => option.value === sort)?.label ?? sort
}

function normalizeSearch(search: string): URLSearchParams {
  return new URLSearchParams(search.startsWith("?") ? search.slice(1) : search)
}

function readString(params: URLSearchParams, key: string): string | undefined {
  const value = params.get(key)?.trim()
  return value ? value : undefined
}

function readBoolean(params: URLSearchParams, key: string): boolean | undefined {
  const value = params.get(key)
  if (value === "true") return true
  if (value === "false") return false
  return undefined
}

function readInteger(params: URLSearchParams, key: string, min: number, max?: number): number | undefined {
  const raw = readString(params, key)
  if (!raw || !/^-?\d+$/.test(raw)) return undefined
  const value = Number(raw)
  if (!Number.isSafeInteger(value) || value < min) return undefined
  if (max !== undefined && value > max) return undefined
  return value
}

/**
 * 查询串 → 请求对象。
 *
 * 非法的布尔 / 数字 / 枚举值一律退回默认（不把 422 参数带进页面）；空值按「不筛选」
 * 处理。flag 去重并按固定枚举顺序排列，保证同一组条件得到同一个 URL。
 */
export function parseAdminUsersSearch(search: string): AdminUsersRequest {
  const params = normalizeSearch(search)

  const rawFlags = params.getAll("flag")
  const flags = ADMIN_FLAG_OPTIONS.map((option) => option.value).filter(
    (flag) => rawFlags.includes(flag) && isAdminUserFlag(flag),
  )
  const rawSort = readString(params, "sort")
  const page = readInteger(params, "page", 1) ?? DEFAULT_ADMIN_PAGE
  const pageSize =
    readInteger(params, "page_size", 1, MAX_ADMIN_PAGE_SIZE) ?? DEFAULT_ADMIN_PAGE_SIZE

  const request: AdminUsersRequest = {
    sort: rawSort && isAdminUserSort(rawSort) ? rawSort : DEFAULT_ADMIN_SORT,
    page,
    page_size: pageSize,
  }

  const q = readString(params, "q")
  if (q) request.q = q

  const hasPlan = readBoolean(params, "has_plan")
  if (hasPlan !== undefined) request.has_plan = hasPlan

  const isAdmin = readBoolean(params, "is_admin")
  if (isAdmin !== undefined) request.is_admin = isAdmin

  const hasApiKey = readBoolean(params, "has_api_key")
  if (hasApiKey !== undefined) request.has_api_key = hasApiKey

  const registeredFrom = readString(params, "registered_from")
  if (registeredFrom) request.registered_from = registeredFrom

  const registeredTo = readString(params, "registered_to")
  if (registeredTo) request.registered_to = registeredTo

  const checkinsMin = readInteger(params, "checkins_min", 0)
  if (checkinsMin !== undefined) request.checkins_min = checkinsMin

  const checkinsMax = readInteger(params, "checkins_max", 0)
  if (checkinsMax !== undefined) request.checkins_max = checkinsMax

  const activeWithinDays = readInteger(params, "active_within_days", 0)
  if (activeWithinDays !== undefined) request.active_within_days = activeWithinDays

  if (flags.length > 0) request.flag = flags

  return request
}

/** 固定键序：筛选在前、排序与分页在后；也决定 URL 的稳定形态。 */
function serializeAdminUsersRequest(request: AdminUsersRequest, includePaging: boolean): string {
  const params = new URLSearchParams()

  if (request.q?.trim()) params.set("q", request.q.trim())
  if (request.has_plan !== undefined) params.set("has_plan", String(request.has_plan))
  if (request.is_admin !== undefined) params.set("is_admin", String(request.is_admin))
  if (request.has_api_key !== undefined) params.set("has_api_key", String(request.has_api_key))
  if (request.registered_from) params.set("registered_from", request.registered_from)
  if (request.registered_to) params.set("registered_to", request.registered_to)
  if (request.checkins_min !== undefined) params.set("checkins_min", String(request.checkins_min))
  if (request.checkins_max !== undefined) params.set("checkins_max", String(request.checkins_max))
  if (request.active_within_days !== undefined) {
    params.set("active_within_days", String(request.active_within_days))
  }

  const flags = request.flag ?? []
  for (const option of ADMIN_FLAG_OPTIONS) {
    if (flags.includes(option.value)) params.append("flag", option.value)
  }

  if (request.sort !== DEFAULT_ADMIN_SORT) params.set("sort", request.sort)

  if (includePaging) {
    if (request.page !== DEFAULT_ADMIN_PAGE) params.set("page", String(request.page))
    if (request.page_size !== DEFAULT_ADMIN_PAGE_SIZE) {
      params.set("page_size", String(request.page_size))
    }
  }

  return params.toString()
}

/** 请求对象 → 列表 URL 查询串（不含前导 `?`；默认状态返回空串）。 */
export function buildAdminUsersSearch(request: AdminUsersRequest): string {
  return serializeAdminUsersRequest(request, true)
}

/** 请求对象 → 导出 URL 查询串：筛选与排序和列表一致，但永不分页。 */
export function buildAdminExportSearch(request: AdminUsersRequest): string {
  return serializeAdminUsersRequest(request, false)
}

/** 导出按钮可用性：0 行时禁用并给出可读原因，避免导出空文件还以为成功。 */
export function adminExportAvailability(total: number): { enabled: boolean; reason?: string } {
  if (total > 0) return { enabled: true }
  return { enabled: false, reason: "当前筛选结果为空，暂无可导出的用户" }
}
