/* Simplified profile page: personal hero + API key management. Fitness profile moved to /weight. */
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { CircleAlert, ExternalLink, Key, Loader2, Ruler, ShieldCheck, Trash2, Weight } from "lucide-react"
import { saveApiKey, deleteApiKey } from "@/api"
import { useAuth } from "@/hooks/use-auth"
import { cn } from "@/lib/utils"

const PROVIDERS = [
  {
    value: "qwen",
    label: "通义千问",
    applyUrl: "https://bailian.console.aliyun.com/?tab=model#/api-key",
    note: "支持对话、体型分析、训练计划和数字教练语音。",
  },
  {
    value: "openai",
    label: "OpenAI",
    applyUrl: "https://platform.openai.com/api-keys",
    note: "支持对话、体型分析和训练计划；数字教练语音当前需要通义千问 Key。",
  },
]

export default function ProfilePage() {
  const { userId, user, refreshUser } = useAuth()
  const [keyProvider, setKeyProvider] = useState("qwen")
  const [keyValue, setKeyValue] = useState("")
  const [keySaving, setKeySaving] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)

  const handleSaveKey = async () => {
    const normalizedKey = keyValue.trim()
    if (!userId || !normalizedKey) return
    setKeySaving(true)
    setKeyError(null)
    try {
      await saveApiKey(userId, keyProvider, normalizedKey)
      setKeyValue("")
      await refreshUser()
    } catch (error) {
      setKeyError(error instanceof Error ? error.message : "API Key 保存失败")
    } finally {
      setKeySaving(false)
    }
  }

  const handleDeleteKey = async () => {
    if (!userId) return
    setKeySaving(true)
    setKeyError(null)
    try {
      await deleteApiKey(userId)
      await refreshUser()
    } catch (error) {
      setKeyError(error instanceof Error ? error.message : "API Key 删除失败")
    } finally {
      setKeySaving(false)
    }
  }

  const { nickname, profile, api_key_status } = user || {}
  const userInitial = nickname?.charAt(0)?.toUpperCase() || "?"
  const hasApiKey = api_key_status?.has_key
  const selectedProvider = PROVIDERS.find((provider) => provider.value === keyProvider) || PROVIDERS[0]

  return (
    <div className="page-shell !max-w-3xl">
      <header className="page-header">
        <div>
          <span className="page-kicker">Profile & settings</span>
          <h1 className="page-title">个人资料</h1>
          <p className="page-description">管理你的账号和 AI 服务配置。</p>
        </div>
      </header>

      {/* ── Personal hero ── */}
      <section className="overflow-hidden rounded-lg bg-gradient-to-br from-brand-dark to-[#1f2e25] shadow-[0_8px_24px_rgba(23,26,23,0.12)]">
        <div className="flex items-center gap-5 px-6 py-7 sm:px-8">
          <span className="flex size-16 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-2xl font-bold text-primary shadow-inner">
            {userInitial}
          </span>
          <div className="min-w-0">
            <p className="text-lg font-semibold text-brand-light">{nickname || "My homie"}</p>
            <p className="mt-1 font-sans text-sm text-brand-light/55">
              {profile?.goal ? `${profile.goal} · ` : ""}{profile?.experience || "未设置训练经验"}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {profile?.height && (
                <span className="inline-flex items-center gap-1 rounded-md bg-white/8 px-2 py-1 font-sans text-[0.68rem] text-brand-light/70">
                  <Ruler className="size-3" />{profile.height} cm
                </span>
              )}
              {profile?.weight && (
                <span className="inline-flex items-center gap-1 rounded-md bg-white/8 px-2 py-1 font-sans text-[0.68rem] text-brand-light/70">
                  <Weight className="size-3" />{profile.weight} kg
                </span>
              )}
              {profile?.age && (
                <span className="inline-flex items-center gap-1 rounded-md bg-white/8 px-2 py-1 font-sans text-[0.68rem] text-brand-light/70">
                  {profile.age} 岁
                </span>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Provider credentials required by all AI generation routes. */}
      <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
        <div className="border-b border-border px-6 py-4">
          <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
            <Key className="size-4 text-primary" />
            AI 服务密钥
          </h2>
        </div>
        <div className="space-y-5 px-6 py-6">
          <div className={cn(
            "flex items-start gap-3 rounded-lg border px-4 py-3",
            hasApiKey ? "border-emerald-200 bg-emerald-50" : "border-primary/30 bg-primary/5",
          )}>
            {hasApiKey ? (
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-700" />
            ) : (
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-primary" />
            )}
            <div className="min-w-0">
              <p className="font-sans text-sm font-semibold text-foreground">
                {hasApiKey ? "AI 功能已启用" : "AI 功能尚未启用"}
              </p>
              <p className="mt-1 font-sans text-xs leading-5 text-muted-foreground">
                {hasApiKey
                  ? "当前请求将使用你的供应商账号，不会使用系统共享 Key。"
                  : "使用 AI 功能前，需要配置你自己申请的 API Key。本平台不会生成、发放或共享 API Key。"}
              </p>
            </div>
          </div>

          {hasApiKey && (
            <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3">
              <Badge variant="secondary" className="shrink-0">{api_key_status?.provider || "未知"}</Badge>
              <span className="min-w-0 truncate font-mono text-sm text-muted-foreground">{api_key_status?.masked_key}</span>
              <Button variant="ghost" size="icon-sm" className="ml-auto shrink-0 text-muted-foreground hover:text-destructive" aria-label="删除 API Key" onClick={handleDeleteKey} disabled={keySaving}>
                <Trash2 className="size-4" />
              </Button>
            </div>
          )}

          <div className="grid gap-5 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-end">
            <div className="space-y-1.5">
              <Label className="font-sans text-xs font-semibold text-muted-foreground">提供商</Label>
              <div className="flex gap-2">
                {PROVIDERS.map((p) => (
                  <Button key={p.value} type="button" variant={keyProvider === p.value ? "default" : "outline"} size="sm" onClick={() => setKeyProvider(p.value)} className={cn(keyProvider === p.value && "shadow-sm")}>
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="api-key" className="font-sans text-xs font-semibold text-muted-foreground">API Key</Label>
              <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
                <Input id="api-key" type="password" value={keyValue} onChange={(e) => setKeyValue(e.target.value)} placeholder="sk-..." autoComplete="off" spellCheck={false} className="min-w-0 flex-1 font-mono" />
                <Button onClick={handleSaveKey} disabled={keySaving || !keyValue.trim()} variant="outline" className="shrink-0">
                  {keySaving ? <Loader2 className="animate-spin" /> : <Key />}
                  保存
                </Button>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="font-sans text-xs leading-5 text-muted-foreground">{selectedProvider.note}</p>
              <p className="font-sans text-xs leading-5 text-muted-foreground">Key 使用 AES-256-GCM 加密保存，之后仅显示掩码。</p>
            </div>
            <a
              href={selectedProvider.applyUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex shrink-0 items-center gap-1.5 font-sans text-xs font-semibold text-primary hover:underline"
            >
              去官方平台申请 {selectedProvider.label} Key
              <ExternalLink className="size-3.5" />
            </a>
          </div>

          {keyError && (
            <p role="alert" className="font-sans text-xs font-medium text-destructive">
              {keyError}
            </p>
          )}
        </div>
      </section>
    </div>
  )
}
