/* 管理端页面共用的展示基元：分区卡片、加载 / 空态 / 错误态与时间格式化。
 *
 * 每个数据源（含用户详情页的七个分区）都必须是这三种状态里的一种，且互不影响，
 * 所以卡片组件只接收「分区当前状态」，自己不知道请求怎么发。 */
import type { ReactNode } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export type AdminSectionStatus = "loading" | "ready" | "error"

export interface AdminSectionCardProps {
  title: string
  description?: string
  status: AdminSectionStatus
  errorMessage?: string
  onRetry?: () => void
  empty?: boolean
  emptyText?: string
  children?: ReactNode
}

/** 分区卡片：加载中、失败（带重试）、空态、有数据四态只由 props 决定。 */
export function AdminSectionCard({
  title,
  description,
  status,
  errorMessage,
  onRetry,
  empty = false,
  emptyText,
  children,
}: AdminSectionCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        {status === "loading" ? (
          <div className="space-y-2" data-state="loading">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <p className="sr-only">加载中...</p>
          </div>
        ) : null}
        {status === "error" ? (
          <div className="space-y-3" data-state="error">
            <p role="alert" className="text-sm text-destructive">
              加载失败：{errorMessage || "请稍后重试"}
            </p>
            {onRetry ? (
              <Button variant="outline" size="sm" onClick={onRetry}>
                <RefreshCw className="h-3.5 w-3.5" />
                重试
              </Button>
            ) : null}
          </div>
        ) : null}
        {status === "ready" && empty ? (
          <p className="py-4 text-sm text-muted-foreground">{emptyText ?? "暂无数据"}</p>
        ) : null}
        {status === "ready" && !empty ? children : null}
      </CardContent>
    </Card>
  )
}

/** 整页级错误：列表这类「一页一个请求」的场景用得上。 */
export function AdminErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-destructive">
        <AlertTriangle className="h-4 w-4" />
        加载失败
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" />
          重试
        </Button>
      ) : null}
    </div>
  )
}
