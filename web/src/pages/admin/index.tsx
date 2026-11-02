/* 管理后台：数据概览（系统统计）。列表与详情各自成页，路由见 pages/admin/routes.tsx。 */
import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Activity, Award, ClipboardList, Users } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { getAdminStats } from "@/api"
import type { AdminStats } from "@/api/types"
import { AdminErrorState } from "./display"

export default function AdminOverviewPage() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    getAdminStats()
      .then((result) => {
        if (!active) return
        setStats(result)
      })
      .catch((e: unknown) => {
        if (!active) return
        setStats(null)
        setError(e instanceof Error ? e.message : "加载失败")
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [attempt])

  const retry = useCallback(() => {
    setLoading(true)
    setError(null)
    setAttempt((value) => value + 1)
  }, [])

  const cards = [
    { label: "总用户数", value: stats?.total_users, icon: Users, tone: "text-blue-500" },
    { label: "训练计划", value: stats?.total_plans, icon: ClipboardList, tone: "text-green-500" },
    { label: "总打卡次数", value: stats?.total_workouts, icon: Award, tone: "text-yellow-500" },
    { label: "7日活跃", value: stats?.active_users_7d, icon: Activity, tone: "text-purple-500" },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">数据概览</h1>
          <p className="text-muted-foreground">系统整体运行数据</p>
        </div>
        <Button
          render={<Link to="/admin/users" />}
          nativeButton={false}
          variant="outline"
          size="sm"
        >
          查看用户列表
        </Button>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((key) => (
            <Skeleton key={key} className="h-28" />
          ))}
        </div>
      ) : null}

      {!loading && error ? <AdminErrorState message={error} onRetry={retry} /> : null}

      {!loading && !error ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {cards.map((card) => (
            <Card key={card.label}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">{card.label}</CardTitle>
                <card.icon className={`h-4 w-4 ${card.tone}`} />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{card.value ?? 0}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  )
}
