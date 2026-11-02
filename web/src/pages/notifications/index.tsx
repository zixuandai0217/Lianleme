/* 站内收件箱：未读筛选、单条已读、全部已读与跳转。 */
import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Bell, CheckCheck, Loader2 } from "lucide-react"

import { getNotifications, markAllNotificationsRead, markNotificationRead } from "@/api"
import type { NotificationItem } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/hooks/use-auth"
import { cn } from "@/lib/utils"

export default function NotificationsPage() {
  const { userId } = useAuth()
  const navigate = useNavigate()
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!userId) return
    try {
      const response = await getNotifications(userId, { unreadOnly })
      setItems(response.items)
      setUnreadCount(response.unread_count)
    } finally {
      setLoading(false)
    }
  }, [userId, unreadOnly])

  useEffect(() => {
    load()
  }, [load])

  const openNotification = async (item: NotificationItem) => {
    if (!item.is_read && userId) {
      try {
        const response = await markNotificationRead(userId, item.id)
        setUnreadCount(response.unread_count)
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id ? { ...entry, is_read: true, read_at: response.read_at } : entry,
          ),
        )
      } catch {
        // 已读失败不阻塞跳转：用户的目标是先看到内容。
      }
    }
    navigate(item.target_path || "/dashboard")
  }

  const readAll = async () => {
    if (!userId) return
    setBusy(true)
    try {
      const response = await markAllNotificationsRead(userId)
      setUnreadCount(response.unread_count)
      setItems((current) =>
        current.map((entry) => ({ ...entry, is_read: true, read_at: entry.read_at ?? new Date().toISOString() })),
      )
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="page-shell">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  const visibleItems = unreadOnly ? items.filter((item) => !item.is_read) : items

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <span className="page-kicker">Inbox</span>
          <h1 className="page-title">通知</h1>
          <p className="page-description">
            {unreadCount > 0 ? `有 ${unreadCount} 条未读提醒。` : "全部已读，保持这个节奏。"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={unreadOnly ? "default" : "outline"}
            onClick={() => setUnreadOnly((value) => !value)}
          >
            {unreadOnly ? "只看未读" : "全部"}
          </Button>
          <Button variant="outline" disabled={busy || unreadCount === 0} onClick={readAll}>
            {busy ? <Loader2 className="animate-spin" /> : <CheckCheck />}
            全部已读
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader className="border-b pb-5">
          <div className="flex items-center justify-between">
            <CardTitle className="text-xl">收件箱</CardTitle>
            <Badge variant={unreadCount > 0 ? "default" : "secondary"}>
              {unreadCount > 0 ? `${unreadCount} 条未读` : "无未读"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {visibleItems.length === 0 ? (
            <div className="flex min-h-52 flex-col items-center justify-center text-center">
              <span className="flex size-10 items-center justify-center rounded-sm bg-secondary text-brand-blue">
                <Bell className="size-4" />
              </span>
              <p className="mt-4 font-sans text-sm font-semibold">还没有通知</p>
              <p className="mt-1 max-w-56 text-sm leading-5 text-muted-foreground">
                训练提醒与召回消息会出现在这里。
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-border border-y border-border">
              {visibleItems.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => openNotification(item)}
                    className={cn(
                      "flex w-full items-start gap-3 px-1 py-4 text-left transition-colors hover:bg-secondary/40",
                      item.is_read && "opacity-70",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-1.5 size-2 shrink-0 rounded-full",
                        item.is_read ? "bg-border" : "bg-primary",
                      )}
                      aria-hidden
                    />
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-sans text-sm font-semibold">{item.title}</span>
                        {!item.is_read && <Badge variant="secondary">未读</Badge>}
                      </span>
                      <span className="mt-1 block font-sans text-sm text-muted-foreground">
                        {item.body}
                      </span>
                      <span className="mt-1 block font-sans text-xs text-muted-foreground">
                        {new Date(item.created_at).toLocaleString("zh-CN")}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
