/* Login page for email/password authentication and local development access. */
import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  Dumbbell,
  Loader2,
  Zap,
  ScanEye,
  CalendarDays,
  MessageSquare,
  ChevronRight,
  Mail,
  Lock,
  User,
} from "lucide-react"
import { useAuth } from "@/hooks/use-auth"

const features = [
  { icon: ScanEye, title: "AI 体型分析", desc: "上传照片，智能评估体型和肌肉状态" },
  { icon: CalendarDays, title: "个性化计划", desc: "基于分析结果，定制专属训练方案" },
  { icon: MessageSquare, title: "AI 陪练教练", desc: "实时对话指导，陪你完成每一组训练" },
]

export default function LoginPage() {
  const { loginAsUser, loginWithEmail, register, error: authError } = useAuth()
  const [loading, setLoading] = useState(false)

  // Form mode: "login" | "register"
  const [mode, setMode] = useState<"login" | "register">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [nickname, setNickname] = useState("")
  const [formError, setFormError] = useState<string | null>(null)

  const error = formError || authError

  const resetForm = () => {
    setFormError(null)
    setEmail("")
    setPassword("")
    setNickname("")
  }

  const handleDevLogin = async () => {
    setLoading(true)
    try {
      await loginAsUser()
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)

    if (!email.trim()) {
      setFormError("请输入邮箱")
      return
    }
    if (password.length < 6) {
      setFormError("密码至少 6 位")
      return
    }

    setLoading(true)
    try {
      if (mode === "register") {
        await register(email.trim(), password, nickname.trim() || undefined)
      } else {
        await loginWithEmail(email.trim(), password)
      }
    } catch {
      setFormError("操作失败，请稍后重试")
    } finally {
      setLoading(false)
    }
  }

  const toggleMode = () => {
    setMode(mode === "login" ? "register" : "login")
    resetForm()
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* Desktop brand showcase */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-gradient-to-br from-brand-dark via-[#1b2a1f] to-brand-dark p-12 relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 opacity-[0.03]">
          <div className="grid h-full w-full grid-cols-12 gap-2 p-12">
            {Array.from({ length: 72 }).map((_, i) => (
              <div key={i} className="aspect-square rounded-sm bg-current" />
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3 relative z-10">
          <span className="flex size-11 items-center justify-center rounded-lg bg-primary/20 text-primary shadow-sm">
            <Dumbbell className="size-5" />
          </span>
          <span className="text-xl font-bold tracking-tight text-brand-light">练了么</span>
        </div>

        <div className="relative z-10 max-w-md space-y-8">
          <div>
            <span className="font-sans text-[0.65rem] font-semibold uppercase tracking-[0.15em] text-brand-light/40">
              AI-Powered Fitness Coach
            </span>
            <h1 className="mt-4 text-4xl font-bold leading-tight text-brand-light">
              你的 AI 健身搭子
            </h1>
            <p className="mt-4 text-base leading-relaxed text-brand-light/60">
              从体型分析到训练计划，从动作指导到打卡记录，AI 全程陪练，让每次训练都高效有趣。
            </p>
          </div>

          <div className="space-y-4">
            {features.map((f) => (
              <div key={f.title} className="flex items-start gap-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-white/5 text-brand-light/70">
                  <f.icon className="size-4" />
                </span>
                <div>
                  <p className="font-semibold text-brand-light">{f.title}</p>
                  <p className="mt-0.5 text-sm text-brand-light/50">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="relative z-10 text-xs text-brand-light/30">
          练了么 v0.1.0 · Move with intent
        </p>
      </div>

      {/* Login panel */}
      <div className="flex flex-1 flex-col items-center justify-center p-6 sm:p-12">
        {/* Mobile logo */}
        <div className="flex items-center gap-3 mb-10 lg:hidden">
          <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Dumbbell className="size-5" />
          </span>
          <span className="text-xl font-bold tracking-tight text-foreground">练了么</span>
        </div>

        <div className="w-full max-w-sm rounded-lg border border-border bg-card shadow-[0_8px_24px_rgba(23,26,23,0.06)]">
          <div className="px-6 pt-8 pb-6 space-y-5">
            <div className="text-center space-y-2">
              <h2 className="text-xl font-semibold">
                {mode === "login" ? "登录你的账号" : "创建新账号"}
              </h2>
              <p className="text-sm text-muted-foreground">
                {mode === "login" ? "输入邮箱和密码开始训练之旅" : "注册后即可享受 AI 全程陪练"}
              </p>
            </div>

            {/* Email/Password form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              {mode === "register" && (
                <div className="space-y-1.5">
                  <Label htmlFor="nickname" className="font-sans text-xs font-semibold text-muted-foreground">昵称</Label>
                  <div className="relative">
                    <User className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/40" />
                    <Input
                      id="nickname"
                      type="text"
                      value={nickname}
                      onChange={(e) => setNickname(e.target.value)}
                      placeholder="你的昵称（可选）"
                      className="pl-9"
                    />
                  </div>
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="email" className="font-sans text-xs font-semibold text-muted-foreground">邮箱</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/40" />
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="your@email.com"
                    className="pl-9"
                    autoComplete="email"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password" className="font-sans text-xs font-semibold text-muted-foreground">密码</Label>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/40" />
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="至少 6 位密码"
                    className="pl-9"
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                  />
                </div>
              </div>

              {error && (
                <p className="text-sm text-destructive text-center">{error}</p>
              )}

              <Button type="submit" disabled={loading} className="w-full h-11">
                {loading ? <Loader2 className="animate-spin" /> : null}
                {loading ? "处理中..." : mode === "login" ? "登录" : "注册并登录"}
              </Button>
            </form>

            <div className="relative">
              <Separator />
              <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-3 text-xs text-muted-foreground">
                {mode === "login" ? "没有账号？" : "已有账号？"}
              </span>
            </div>

            <Button
              type="button"
              variant="ghost"
              onClick={toggleMode}
              className="w-full text-sm text-muted-foreground hover:text-foreground"
            >
              {mode === "login" ? "注册新账号" : "使用已有账号登录"}
              <ChevronRight className="size-3.5" />
            </Button>

            {/* Dev quick login */}
            <div className="relative">
              <Separator />
              <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-3 text-xs text-muted-foreground">
                开发模式
              </span>
            </div>

            <Button
              onClick={handleDevLogin}
              disabled={loading}
              variant="outline"
              className="w-full h-11"
            >
              {loading ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Zap className="size-4" />
              )}
              {loading ? "登录中..." : "Let's GO! 🔥"}
            </Button>

            <p className="text-xs text-muted-foreground text-center leading-relaxed">
              Dev login — no strings attached. Get in, get swole. 💪
            </p>

            {/* Admin link */}
            <div className="text-center">
              <Link
                to="/admin/login"
                className="inline-flex items-center gap-1 text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground transition-colors"
              >
                管理员入口
                <ChevronRight className="size-3" />
              </Link>
            </div>
          </div>
        </div>

        {/* Mobile feature preview */}
        <div className="mt-10 space-y-4 lg:hidden max-w-sm w-full">
          {features.map((f) => (
            <div key={f.title} className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <f.icon className="size-4" />
              </span>
              <div>
                <p className="text-sm font-semibold">{f.title}</p>
                <p className="text-xs text-muted-foreground">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
