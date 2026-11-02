/* 管理端：用户列表页。
 *
 * 搜索 / 筛选 / 排序 / 分页全部服务端完成，前端只把状态写进 URL（键名与接口参数一一
 * 对应），所以刷新、复制链接、浏览器后退都会还原同一份结果；从列表进详情再返回也
 * 只是回到原来的 URL。 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom"
import { ChevronLeft, ChevronRight, Download, Search, X } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { downloadAdminUsersExport, getAdminUsers } from "@/api"
import type { AdminUserFlag, AdminUserItem, PaginatedUsers } from "@/api/types"
import {
  ADMIN_FLAG_OPTIONS,
  ADMIN_SORT_OPTIONS,
  adminExportAvailability,
  adminFlagLabel,
  adminSortLabel,
  buildAdminUsersSearch,
  parseAdminUsersSearch,
  type AdminUsersRequest,
} from "@/lib/admin-query"
import { AdminErrorState } from "./display"
import { formatAdminDateTime } from "@/lib/admin-format"

/** 搜索防抖窗口：停顿约 300ms 才把词写进 URL，停顿期间不发请求。 */
const SEARCH_DEBOUNCE_MS = 300

const defaultRequest = () => parseAdminUsersSearch("")

export default function AdminUsersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()

  const request = useMemo(
    () => parseAdminUsersSearch(searchParams.toString()),
    [searchParams],
  )

  // 结果与失败都带「属于哪个请求」的 key：URL 一变，旧结果立即不算数，loading 由
  // 派生得出；effect 只负责发请求与接收结果，不在同步阶段 setState，也不让旧响应
  // 覆盖新筛选。
  const requestKey = useMemo(() => buildAdminUsersSearch(request), [request])
  const [result, setResult] = useState<{ key: string; data: PaginatedUsers } | null>(null)
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getAdminUsers(request)
      .then((data) => {
        if (!active) return
        setResult({ key: requestKey, data })
        setFailure(null)
      })
      .catch((e: unknown) => {
        if (!active) return
        setFailure({
          key: requestKey,
          message: e instanceof Error ? e.message : "加载失败",
        })
      })
    return () => {
      active = false
    }
  }, [request, requestKey, attempt])

  const data = result?.key === requestKey ? result.data : null
  const error = failure?.key === requestKey ? failure.message : null
  const loading = data === null && error === null

  const retry = useCallback(() => {
    setFailure(null)
    setAttempt((value) => value + 1)
  }, [])

  // 搜索词留在输入框（非受控），停顿 300ms 才写一次 URL：一次停顿只产生一个请求。
  // 外部来源（刷新、后退、清空）改动 q 时，用 effect 把输入框同步回 URL 的值。
  const searchRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<number | null>(null)
  const requestRef = useRef(request)
  useEffect(() => {
    requestRef.current = request
  }, [request])

  const committedQuery = request.q ?? ""
  useEffect(() => {
    const input = searchRef.current
    if (input && input.value !== committedQuery) input.value = committedQuery
  }, [committedQuery])

  useEffect(
    () => () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    },
    [],
  )

  const commitSearch = useCallback(
    (value: string) => {
      const current = requestRef.current
      setSearchParams(
        buildAdminUsersSearch({ ...current, q: value.trim() || undefined, page: 1 }),
      )
    },
    [setSearchParams],
  )

  const onSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value
    if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      debounceRef.current = null
      commitSearch(value)
    }, SEARCH_DEBOUNCE_MS)
  }

  /** 任何筛选 / 排序变化都回到第 1 页，避免停在空页。 */
  const applyFilters = useCallback(
    (patch: Partial<AdminUsersRequest>) => {
      const current = requestRef.current
      setSearchParams(buildAdminUsersSearch({ ...current, ...patch, page: 1 }))
    },
    [setSearchParams],
  )

  const goToPage = useCallback(
    (page: number) => {
      const current = requestRef.current
      setSearchParams(buildAdminUsersSearch({ ...current, page }))
    },
    [setSearchParams],
  )

  const clearFilters = useCallback(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
    setSearchParams(buildAdminUsersSearch(defaultRequest()))
  }, [setSearchParams])

  const total = data?.total ?? 0
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const availability = adminExportAvailability(total)
  const listFrom = `${location.pathname}${location.search}`

  const openUser = useCallback(
    (userId: number) => {
      navigate(`/admin/users/${userId}`, { state: { from: listFrom } })
    },
    [listFrom, navigate],
  )

  const runExport = useCallback(async () => {
    setExporting(true)
    setExportError(null)
    try {
      await downloadAdminUsersExport(request)
    } catch (e: unknown) {
      setExportError(e instanceof Error ? e.message : "导出失败，请稍后重试")
    } finally {
      setExporting(false)
    }
  }, [request])

  const selectedFlags = new Set(request.flag ?? [])
  const toggleFlag = (flag: AdminUserFlag) => {
    const next = new Set(selectedFlags)
    if (next.has(flag)) next.delete(flag)
    else next.add(flag)
    applyFilters({ flag: ADMIN_FLAG_OPTIONS.filter((option) => next.has(option.value)).map((o) => o.value) })
  }

  const items = data?.items ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">用户列表</h1>
        <p className="text-muted-foreground">
          搜索、筛选、排序与分页全部服务端完成，条件已写进地址栏，可分享、可刷新、可后退。
        </p>
      </div>

      {/* 工具栏：搜索 + 一键清空 + 导出 */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-64 flex-1">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                ref={searchRef}
                className="pl-8"
                placeholder="搜索昵称 / 邮箱 / 用户 ID / openid"
                aria-label="搜索用户"
                onChange={onSearchChange}
              />
            </div>
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              <X className="h-3.5 w-3.5" />
              清空筛选
            </Button>
            <Button
              size="sm"
              disabled={!availability.enabled || loading || exporting}
              onClick={runExport}
            >
              <Download className="h-3.5 w-3.5" />
              {exporting ? "导出中..." : "导出 CSV"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground" role="status">
            {availability.enabled
              ? `当前筛选结果共 ${total} 位用户，导出内容与列表一致。`
              : availability.reason}
          </p>
          {exportError ? (
            <p role="alert" className="text-sm text-destructive">
              {exportError}
            </p>
          ) : null}

          {/* 筛选面板 */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">是否有计划</span>
              <select
                aria-label="是否有计划"
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                value={request.has_plan === undefined ? "" : String(request.has_plan)}
                onChange={(event) =>
                  applyFilters({
                    has_plan:
                      event.target.value === ""
                        ? undefined
                        : event.target.value === "true",
                  })
                }
              >
                <option value="">全部</option>
                <option value="true">有计划</option>
                <option value="false">无计划</option>
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">是否管理员</span>
              <select
                aria-label="是否管理员"
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                value={request.is_admin === undefined ? "" : String(request.is_admin)}
                onChange={(event) =>
                  applyFilters({
                    is_admin:
                      event.target.value === ""
                        ? undefined
                        : event.target.value === "true",
                  })
                }
              >
                <option value="">全部</option>
                <option value="true">管理员</option>
                <option value="false">非管理员</option>
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">API Key</span>
              <select
                aria-label="是否已配置 API Key"
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                value={request.has_api_key === undefined ? "" : String(request.has_api_key)}
                onChange={(event) =>
                  applyFilters({
                    has_api_key:
                      event.target.value === ""
                        ? undefined
                        : event.target.value === "true",
                  })
                }
              >
                <option value="">全部</option>
                <option value="true">已配置</option>
                <option value="false">未配置</option>
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">排序</span>
              <select
                aria-label="排序"
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                value={request.sort}
                onChange={(event) =>
                  applyFilters({ sort: event.target.value as AdminUsersRequest["sort"] })
                }
              >
                {ADMIN_SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">注册起始</span>
              <Input
                type="date"
                aria-label="注册起始日期"
                value={request.registered_from ?? ""}
                onChange={(event) =>
                  applyFilters({ registered_from: event.target.value || undefined })
                }
              />
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">注册截止</span>
              <Input
                type="date"
                aria-label="注册截止日期"
                value={request.registered_to ?? ""}
                onChange={(event) =>
                  applyFilters({ registered_to: event.target.value || undefined })
                }
              />
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">累计打卡下限</span>
              <Input
                type="number"
                min={0}
                aria-label="累计打卡数下限"
                value={request.checkins_min ?? ""}
                onChange={(event) =>
                  applyFilters({
                    checkins_min: event.target.value ? Number(event.target.value) : undefined,
                  })
                }
              />
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">累计打卡上限</span>
              <Input
                type="number"
                min={0}
                aria-label="累计打卡数上限"
                value={request.checkins_max ?? ""}
                onChange={(event) =>
                  applyFilters({
                    checkins_max: event.target.value ? Number(event.target.value) : undefined,
                  })
                }
              />
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">最近活跃天数内</span>
              <Input
                type="number"
                min={0}
                aria-label="最近活跃天数内"
                value={request.active_within_days ?? ""}
                onChange={(event) =>
                  applyFilters({
                    active_within_days: event.target.value
                      ? Number(event.target.value)
                      : undefined,
                  })
                }
              />
            </label>
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm text-muted-foreground">需关注标记（可多选）</legend>
            <div className="flex flex-wrap gap-3">
              {ADMIN_FLAG_OPTIONS.map((option) => (
                <label key={option.value} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    aria-label={option.label}
                    checked={selectedFlags.has(option.value)}
                    onChange={() => toggleFlag(option.value)}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          </fieldset>
        </CardContent>
      </Card>

      {/* 结果表 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">查询结果</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((key) => (
                <Skeleton key={key} className="h-10" />
              ))}
            </div>
          ) : null}

          {!loading && error ? <AdminErrorState message={error} onRetry={retry} /> : null}

          {!loading && !error && items.length === 0 ? (
            <div className="space-y-3 py-8 text-center">
              <p className="text-muted-foreground">没有符合条件的用户</p>
              <div className="flex justify-center gap-2">
                <Button variant="outline" size="sm" onClick={clearFilters}>
                  清空筛选
                </Button>
                <Button variant="ghost" size="sm" onClick={retry}>
                  重试
                </Button>
              </div>
            </div>
          ) : null}

          {!loading && !error && items.length > 0 ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="pb-3 font-medium">ID</th>
                      <th className="pb-3 font-medium">昵称</th>
                      <th className="pb-3 font-medium">邮箱</th>
                      <th className="pb-3 font-medium">OpenID</th>
                      <th className="pb-3 font-medium">有计划</th>
                      <th className="pb-3 font-medium">累计打卡</th>
                      <th className="pb-3 font-medium">近 30 天</th>
                      <th className="pb-3 font-medium">最近活跃</th>
                      <th className="pb-3 font-medium">需关注</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item: AdminUserItem) => (
                      <tr
                        key={item.id}
                        className="cursor-pointer border-b last:border-0 hover:bg-accent/50"
                        onClick={() => openUser(item.id)}
                      >
                        <td className="py-3">{item.id}</td>
                        <td className="py-3">
                          <Link
                            to={`/admin/users/${item.id}`}
                            state={{ from: listFrom }}
                            className="text-primary hover:underline"
                            onClick={(event) => event.stopPropagation()}
                          >
                            {item.nickname || "未命名用户"}
                          </Link>
                        </td>
                        <td className="py-3">{item.email_masked || "—"}</td>
                        <td className="py-3">
                          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                            {item.openid}
                          </code>
                        </td>
                        <td className="py-3">
                          <Badge variant={item.has_plan ? "default" : "secondary"}>
                            {item.has_plan ? "是" : "否"}
                          </Badge>
                        </td>
                        <td className="py-3">{item.total_checkins}</td>
                        <td className="py-3">{item.checkins_30d}</td>
                        <td className="py-3 text-muted-foreground">
                          {formatAdminDateTime(item.last_active_at)}
                        </td>
                        <td className="py-3">
                          {item.flags.length > 0 ? (
                            <span className="flex flex-wrap gap-1">
                              {item.flags.map((flag) => (
                                <Badge key={flag} variant="outline">
                                  {adminFlagLabel(flag)}
                                </Badge>
                              ))}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-4 flex items-center justify-between border-t pt-4">
                <p className="text-sm text-muted-foreground">共 {total} 位用户</p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    aria-label="上一页"
                    disabled={request.page <= 1}
                    onClick={() => goToPage(request.page - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm">
                    {request.page} / {totalPages}（{adminSortLabel(request.sort)}）
                  </span>
                  <Button
                    variant="outline"
                    size="icon"
                    aria-label="下一页"
                    disabled={request.page >= totalPages}
                    onClick={() => goToPage(request.page + 1)}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
