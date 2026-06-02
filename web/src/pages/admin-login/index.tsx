/* 管理员登录页：独立管理后台入口 */
import { useState } from "react"
import { Link } from "react-router-dom"
import { ShieldCheck, Loader2, LockKeyhole, BarChart3 } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { useAuth } from "@/hooks/use-auth"

export default function AdminLoginPage() {
  const { loginAsAdmin, error } = useAuth()
  const [loading, setLoading] = useState(false)

  const handleAdminLogin = async () => {
    setLoading(true)
    try {
      await loginAsAdmin()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen bg-background">
      <div className="hidden lg:flex lg:w-[44%] flex-col justify-between border-r bg-muted/30 px-12 py-10">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary p-2">
            <ShieldCheck className="h-6 w-6 text-primary-foreground" />
          </div>
          <div>
            <p className="text-lg font-semibold">练了么</p>
            <p className="text-sm text-muted-foreground">管理后台</p>
          </div>
        </div>

        <div className="max-w-md space-y-6">
          <div className="space-y-3">
            <h1 className="text-4xl font-semibold tracking-tight">管理员登录</h1>
            <p className="text-base leading-7 text-muted-foreground">
              独立进入数据概览、用户管理与后台运营视图，不与用户训练体验混用。
            </p>
          </div>

          <div className="space-y-4 text-sm text-muted-foreground">
            <div className="flex items-start gap-3">
              <BarChart3 className="mt-0.5 h-4 w-4 text-primary" />
              <p>查看系统概览、活跃数据和训练执行情况</p>
            </div>
            <div className="flex items-start gap-3">
              <LockKeyhole className="mt-0.5 h-4 w-4 text-primary" />
              <p>使用单独的管理员身份进入，避免和用户端状态混淆</p>
            </div>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">Admin Surface · Development Access</p>
      </div>

      <div className="flex flex-1 items-center justify-center px-6 py-12 sm:px-10">
        <Card className="w-full max-w-sm">
          <CardHeader className="space-y-2 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <ShieldCheck className="h-6 w-6 text-primary" />
            </div>
            <CardTitle className="text-2xl">管理后台登录</CardTitle>
            <p className="text-sm text-muted-foreground">
              使用独立管理员入口进入后台
            </p>
          </CardHeader>
          <CardContent className="space-y-5">
            <Button
              onClick={handleAdminLogin}
              disabled={loading}
              className="h-11 w-full"
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ShieldCheck className="mr-2 h-4 w-4" />
              )}
              {loading ? "登录中..." : "进入管理后台"}
            </Button>

            {error && (
              <p className="text-center text-sm text-destructive">{error}</p>
            )}

            <Separator />

            <div className="text-center">
              <Link
                to="/login"
                className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
              >
                返回用户登录
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
