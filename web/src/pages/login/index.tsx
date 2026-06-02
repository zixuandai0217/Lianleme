/* 登录页：品牌展示 + 开发快速登录 + 微信登录预留 */
import { useState } from "react"
import { Link } from "react-router-dom"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Dumbbell, Loader2, Zap, ScanEye, CalendarDays, MessageSquare } from "lucide-react"
import { useAuth } from "@/hooks/use-auth"

const features = [
  { icon: ScanEye, title: "AI 体型分析", desc: "上传照片，智能评估体型和肌肉状态" },
  { icon: CalendarDays, title: "个性化计划", desc: "基于分析结果，定制专属训练方案" },
  { icon: MessageSquare, title: "AI 陪练教练", desc: "实时对话指导，陪你完成每一组训练" },
]

export default function LoginPage() {
  const { loginAsUser, error } = useAuth()
  const [loading, setLoading] = useState(false)

  const handleDevLogin = async () => {
    setLoading(true)
    try {
      await loginAsUser()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* 左侧品牌区 */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-gradient-to-br from-primary/10 via-primary/5 to-background p-12">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-primary p-2.5">
            <Dumbbell className="h-7 w-7 text-primary-foreground" />
          </div>
          <span className="text-2xl font-bold tracking-tight">练了么</span>
        </div>

        <div className="space-y-8 max-w-md">
          <div>
            <h1 className="text-4xl font-bold tracking-tight leading-tight">
              你的 AI 健身搭子
            </h1>
            <p className="mt-3 text-lg text-muted-foreground leading-relaxed">
              从体型分析到训练计划，从动作指导到打卡记录，AI 全程陪练，让每次训练都高效有趣。
            </p>
          </div>

          <div className="space-y-5">
            {features.map((f) => (
              <div key={f.title} className="flex items-start gap-4">
                <div className="rounded-lg bg-primary/10 p-2.5 shrink-0">
                  <f.icon className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="font-semibold">{f.title}</p>
                  <p className="text-sm text-muted-foreground">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs text-muted-foreground">
          练了么 v0.1.0 · AI-Powered Fitness Coach
        </p>
      </div>

      {/* 右侧登录区 */}
      <div className="flex flex-1 flex-col items-center justify-center p-6 sm:p-12">
        {/* 移动端 logo */}
        <div className="flex items-center gap-3 mb-10 lg:hidden">
          <div className="rounded-xl bg-primary p-2.5">
            <Dumbbell className="h-7 w-7 text-primary-foreground" />
          </div>
          <span className="text-2xl font-bold tracking-tight">练了么</span>
        </div>

        <Card className="w-full max-w-sm">
          <CardContent className="pt-8 pb-8 px-6 space-y-6">
            <div className="text-center space-y-2">
              <h2 className="text-xl font-semibold">登录你的账号</h2>
              <p className="text-sm text-muted-foreground">
                选择一种方式开始训练之旅
              </p>
            </div>

            {/* 微信登录（预留） */}
            <Button
              variant="outline"
              className="w-full h-11 relative"
              disabled
            >
              <svg className="mr-2 h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 0 1 .213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 0 0 .167-.054l1.903-1.114a.864.864 0 0 1 .717-.098 10.16 10.16 0 0 0 2.837.403c.276 0 .543-.027.811-.05a6.093 6.093 0 0 1-.247-1.728c0-3.572 3.259-6.47 7.277-6.47.145 0 .284.022.426.028C16.219 4.535 12.868 2.188 8.691 2.188zM5.785 7.11a.96.96 0 1 1 0-1.92.96.96 0 0 1 0 1.92zm5.813 0a.96.96 0 1 1 0-1.92.96.96 0 0 1 0 1.92zm4.434 7.202c0 3.07 2.867 5.56 6.402 5.56.67 0 1.312-.09 1.912-.263a.6.6 0 0 1 .497.068l1.32.772a.224.224 0 0 0 .116.037c.11 0 .2-.09.2-.204 0-.05-.02-.098-.033-.147l-.27-1.026a.408.408 0 0 1 .147-.46C24.893 17.47 24 15.9 24 14.312c0-3.07-2.867-5.56-6.402-5.56-3.535 0-5.566 2.49-5.566 5.56zM16.97 13a.72.72 0 1 1 0-1.44.72.72 0 0 1 0 1.44zm4.06 0a.72.72 0 1 1 0-1.44.72.72 0 0 1 0 1.44z" />
              </svg>
              微信登录
              <span className="absolute right-3 text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                即将上线
              </span>
            </Button>

            <div className="relative">
              <Separator />
              <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-3 text-xs text-muted-foreground">
                或
              </span>
            </div>

            {/* 开发模式快速登录 */}
            <Button
              onClick={handleDevLogin}
              disabled={loading}
              className="w-full h-11"
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Zap className="mr-2 h-4 w-4" />
              )}
              {loading ? "登录中..." : "快速体验登录"}
            </Button>

            {error && (
              <p className="text-sm text-destructive text-center">{error}</p>
            )}

            <p className="text-xs text-muted-foreground text-center leading-relaxed">
              快速登录使用开发账号，无需微信授权即可体验全部功能
            </p>

            <div className="text-center">
              <Link
                to="/admin/login"
                className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
              >
                管理员入口
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* 移动端功能预览 */}
        <div className="mt-10 space-y-4 lg:hidden max-w-sm w-full">
          {features.map((f) => (
            <div key={f.title} className="flex items-center gap-3 text-sm">
              <f.icon className="h-4 w-4 text-primary shrink-0" />
              <span className="text-muted-foreground">{f.title} — {f.desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
