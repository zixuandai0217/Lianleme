/* 个人资料页：信息编辑 + API Key 管理 */
import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { User, Key, Save, Trash2, Loader2, CheckCircle2 } from "lucide-react"
import { updateProfile, saveApiKey, deleteApiKey } from "@/api"
import { useAuth } from "@/hooks/use-auth"

export default function ProfilePage() {
  const { userId, user, refreshUser } = useAuth()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [syncedUserId, setSyncedUserId] = useState<number | null>(null)
  const [nickname, setNickname] = useState("")
  const [height, setHeight] = useState("")
  const [weight, setWeight] = useState("")
  const [age, setAge] = useState("")
  const [gender, setGender] = useState("")
  const [goal, setGoal] = useState("")
  const [experience, setExperience] = useState("")

  if (user && user.id !== syncedUserId) {
    setNickname(user.nickname || "")
    setHeight(String(user.profile?.height || ""))
    setWeight(String(user.profile?.weight || ""))
    setAge(String(user.profile?.age || ""))
    setGender(user.profile?.gender || "")
    setGoal(user.profile?.goal || "")
    setExperience(user.profile?.experience || "")
    setSyncedUserId(user.id)
  }

  const [keyProvider, setKeyProvider] = useState("qwen")
  const [keyValue, setKeyValue] = useState("")
  const [keySaving, setKeySaving] = useState(false)

  const handleSaveProfile = async () => {
    if (!userId) return
    setSaving(true)
    setSaved(false)
    try {
      await updateProfile(userId, {
        nickname: nickname || undefined,
        profile: {
          height: height ? Number(height) : undefined,
          weight: weight ? Number(weight) : undefined,
          age: age ? Number(age) : undefined,
          gender: gender || undefined,
          goal: goal || undefined,
          experience: experience || undefined,
        },
      })
      await refreshUser()
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  const handleSaveKey = async () => {
    if (!userId || !keyValue) return
    setKeySaving(true)
    try {
      await saveApiKey(userId, keyProvider, keyValue)
      setKeyValue("")
      await refreshUser()
    } finally {
      setKeySaving(false)
    }
  }

  const handleDeleteKey = async () => {
    if (!userId) return
    setKeySaving(true)
    try {
      await deleteApiKey(userId)
      await refreshUser()
    } finally {
      setKeySaving(false)
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">个人资料</h1>
        <p className="text-muted-foreground">管理你的健身档案和 API 密钥</p>
      </div>

      {/* Profile form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            健身档案
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="nickname">昵称</Label>
              <Input
                id="nickname"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="你的昵称"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="gender">性别</Label>
              <div className="flex gap-2">
                {["男", "女"].map((g) => (
                  <Button
                    key={g}
                    type="button"
                    variant={gender === g ? "default" : "outline"}
                    size="sm"
                    onClick={() => setGender(g)}
                  >
                    {g}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="height">身高 (cm)</Label>
              <Input
                id="height"
                type="number"
                value={height}
                onChange={(e) => setHeight(e.target.value)}
                placeholder="170"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="weight">体重 (kg)</Label>
              <Input
                id="weight"
                type="number"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                placeholder="70"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="age">年龄</Label>
              <Input
                id="age"
                type="number"
                value={age}
                onChange={(e) => setAge(e.target.value)}
                placeholder="25"
              />
            </div>
          </div>

          <Separator />

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>健身目标</Label>
              <div className="flex flex-wrap gap-2">
                {["减脂", "增肌", "塑形", "提升体能"].map((g) => (
                  <Button
                    key={g}
                    type="button"
                    variant={goal === g ? "default" : "outline"}
                    size="sm"
                    onClick={() => setGoal(g)}
                  >
                    {g}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label>训练经验</Label>
              <div className="flex flex-wrap gap-2">
                {["新手", "初级", "中级", "高级"].map((e) => (
                  <Button
                    key={e}
                    type="button"
                    variant={experience === e ? "default" : "outline"}
                    size="sm"
                    onClick={() => setExperience(e)}
                  >
                    {e}
                  </Button>
                ))}
              </div>
            </div>
          </div>

          <Button onClick={handleSaveProfile} disabled={saving} className="w-full">
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : saved ? (
              <CheckCircle2 className="mr-2 h-4 w-4" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            {saved ? "已保存" : "保存档案"}
          </Button>
        </CardContent>
      </Card>

      {/* API Key management */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            LLM API Key
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            配置自有 API Key 以获得更好的 AI 对话体验。留空则使用系统默认 Key。
          </p>

          {user?.api_key_status?.has_key && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50">
              <Badge>{user.api_key_status.provider}</Badge>
              <span className="text-sm font-mono">{user.api_key_status.masked_key}</span>
              <Button
                variant="ghost"
                size="icon"
                className="ml-auto"
                onClick={handleDeleteKey}
                disabled={keySaving}
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-[120px_1fr]">
            <div className="space-y-2">
              <Label>提供商</Label>
              <div className="flex gap-2">
                {["qwen", "openai"].map((p) => (
                  <Button
                    key={p}
                    variant={keyProvider === p ? "default" : "outline"}
                    size="sm"
                    onClick={() => setKeyProvider(p)}
                  >
                    {p}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="api-key">API Key</Label>
              <Input
                id="api-key"
                type="password"
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                placeholder="sk-..."
              />
            </div>
          </div>

          <Button onClick={handleSaveKey} disabled={keySaving || !keyValue} variant="outline" className="w-full">
            {keySaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Key className="mr-2 h-4 w-4" />}
            保存 API Key
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
