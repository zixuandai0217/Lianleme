/* 管理后台：系统概览 + 用户列表 */
import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Users, ClipboardList, Award, Activity, ChevronLeft, ChevronRight } from "lucide-react"
import { getAdminStats, getAdminUsers } from "@/api"
import type { AdminStats, PaginatedUsers } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"

export default function AdminPage() {
  const { userId } = useAuth()
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [users, setUsers] = useState<PaginatedUsers | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!userId) return
    const load = async () => {
      setLoading(true)
      try {
        const [s, u] = await Promise.all([
          getAdminStats(userId).catch(() => null),
          getAdminUsers(userId, page).catch(() => null),
        ])
        setStats(s)
        setUsers(u)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [userId, page])

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <Skeleton className="h-64" />
      </div>
    )
  }

  const totalPages = users ? Math.ceil(users.total / users.page_size) : 1

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">管理后台</h1>
        <p className="text-muted-foreground">系统数据概览与用户管理</p>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">总用户数</CardTitle>
            <Users className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.total_users ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">训练计划</CardTitle>
            <ClipboardList className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.total_plans ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">总打卡次数</CardTitle>
            <Award className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.total_workouts ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">7日活跃</CardTitle>
            <Activity className="h-4 w-4 text-purple-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.active_users_7d ?? 0}</div>
          </CardContent>
        </Card>
      </div>

      {/* User table */}
      <Card>
        <CardHeader>
          <CardTitle>用户列表</CardTitle>
        </CardHeader>
        <CardContent>
          {users && users.items.length > 0 ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="pb-3 font-medium">ID</th>
                      <th className="pb-3 font-medium">昵称</th>
                      <th className="pb-3 font-medium">OpenID</th>
                      <th className="pb-3 font-medium">有计划</th>
                      <th className="pb-3 font-medium">打卡数</th>
                      <th className="pb-3 font-medium">注册时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.items.map((u) => (
                      <tr key={u.id} className="border-b last:border-0">
                        <td className="py-3">{u.id}</td>
                        <td className="py-3">{u.nickname || "-"}</td>
                        <td className="py-3">
                          <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                            {u.openid.length > 12
                              ? `${u.openid.slice(0, 6)}...${u.openid.slice(-4)}`
                              : u.openid}
                          </code>
                        </td>
                        <td className="py-3">
                          <Badge variant={u.has_plan ? "default" : "secondary"}>
                            {u.has_plan ? "是" : "否"}
                          </Badge>
                        </td>
                        <td className="py-3">{u.total_checkins}</td>
                        <td className="py-3 text-muted-foreground">
                          {u.created_at ? new Date(u.created_at).toLocaleDateString() : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between mt-4 pt-4 border-t">
                <p className="text-sm text-muted-foreground">
                  共 {users.total} 位用户
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm">
                    {page} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-8 text-muted-foreground">暂无用户数据</div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
