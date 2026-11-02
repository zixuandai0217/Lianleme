/* 管理端：用户详情页。
 *
 * 七个分区各发一次「只带该分区」的请求，所以每张卡片可以独立加载、单独失败：
 * 一个数据源挂了，其他分区照常渲染。缺计划、缺分析、缺体重的用户看到的是空态，
 * 不是报错。 */
import { useCallback, useEffect, useState } from "react"
import { useLocation, useNavigate, useParams } from "react-router-dom"
import { ArrowLeft } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { getAdminUserDetail } from "@/api"
import type { AdminUserDetailResponse, AdminUserDetailSection } from "@/api/types"
import { adminFlagLabel } from "@/lib/admin-query"
import { AdminSectionCard } from "./display"
import { formatAdminDate, formatAdminDateTime, formatAdminNumber } from "@/lib/admin-format"

interface SectionState {
  status: "loading" | "ready" | "error"
  data?: AdminUserDetailResponse | null
  message?: string
}

/** 单个分区的请求：失败只影响这一张卡片，重试也只重试这一张。 */
function useAdminUserSection(userId: number | null, section: AdminUserDetailSection) {
  const [loaded, setLoaded] = useState<{ key: string; state: SectionState } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const key = `${userId}:${section}:${attempt}`
  // 换用户/分区/重试时 key 变化，旧结果自动失效为 loading，不会短暂显示上一个用户的数据。
  const state: SectionState =
    loaded?.key === key ? loaded.state : { status: "loading" }

  useEffect(() => {
    if (userId === null) return
    let active = true
    getAdminUserDetail(userId, { sections: [section] })
      .then((result) => {
        if (!active) return
        setLoaded({ key, state: { status: "ready", data: result } })
      })
      .catch((e: unknown) => {
        if (!active) return
        setLoaded({
          key,
          state: {
            status: "error",
            message: e instanceof Error ? e.message : "请稍后重试",
          },
        })
      })
    return () => {
      active = false
    }
  }, [userId, section, key])

  const retry = useCallback(() => {
    setAttempt((value) => value + 1)
  }, [])
  return { state, retry }
}

const ADJUSTMENT_DIRECTION_LABEL: Record<string, string> = {
  increase: "提高强度",
  decrease: "降低强度",
  keep: "维持强度",
}

function ProfileCard({ state, onRetry }: { state: SectionState; onRetry: () => void }) {
  const profile = state.data?.profile
  return (
    <AdminSectionCard
      title="基础档案"
      description="账号状态与联系方式（接口层已脱敏）"
      status={state.status}
      onRetry={onRetry}
      errorMessage={state.message}
      empty={!profile}
      emptyText="没有该用户的档案"
    >
      {profile ? (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground">昵称</dt>
          <dd>{profile.nickname || "未命名用户"}</dd>
          <dt className="text-muted-foreground">用户 ID</dt>
          <dd>{profile.id}</dd>
          <dt className="text-muted-foreground">邮箱</dt>
          <dd>{profile.email_masked || "—"}</dd>
          <dt className="text-muted-foreground">OpenID</dt>
          <dd>{profile.openid}</dd>
          <dt className="text-muted-foreground">注册时间</dt>
          <dd>{formatAdminDateTime(profile.created_at)}</dd>
          <dt className="text-muted-foreground">管理员</dt>
          <dd>
            <Badge variant={profile.is_admin ? "default" : "secondary"}>
              {profile.is_admin ? "是" : "否"}
            </Badge>
          </dd>
          <dt className="text-muted-foreground">API Key</dt>
          <dd>
            {profile.has_api_key ? `已配置（${profile.llm_provider ?? "未知"}）` : "未配置"}
          </dd>
          <dt className="text-muted-foreground">需关注标记</dt>
          <dd>
            {profile.flags.length > 0 ? (
              <span className="flex flex-wrap gap-1">
                {profile.flags.map((flag) => (
                  <Badge key={flag} variant="outline">
                    {adminFlagLabel(flag)}
                  </Badge>
                ))}
              </span>
            ) : (
              "—"
            )}
          </dd>
        </dl>
      ) : null}
    </AdminSectionCard>
  )
}

function BodyAnalysisCard({ state, onRetry }: { state: SectionState; onRetry: () => void }) {
  const analysis = state.data?.body_analysis
  return (
    <AdminSectionCard
      title="体型分析"
      description="最近一次分析摘要"
      status={state.status}
      onRetry={onRetry}
      errorMessage={state.message}
      empty={!analysis}
      emptyText="暂无体型分析数据"
    >
      {analysis ? (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground">体型分类</dt>
          <dd>{analysis.body_type || "—"}</dd>
          <dt className="text-muted-foreground">体脂区间</dt>
          <dd>{analysis.body_fat_range || "—"}</dd>
          <dt className="text-muted-foreground">弱势肌群</dt>
          <dd>{analysis.weak_muscles?.join("、") || "—"}</dd>
          <dt className="text-muted-foreground">优势部位</dt>
          <dd>{analysis.strengths?.join("、") || "—"}</dd>
          <dt className="text-muted-foreground">分析时间</dt>
          <dd>{formatAdminDateTime(analysis.analyzed_at)}</dd>
          <dt className="text-muted-foreground">结论摘要</dt>
          <dd>{analysis.summary || "—"}</dd>
        </dl>
      ) : null}
    </AdminSectionCard>
  )
}

function PlanCard({ state, onRetry }: { state: SectionState; onRetry: () => void }) {
  const plan = state.data?.plan
  const adjustment = plan?.latest_adjustment
  return (
    <AdminSectionCard
      title="训练计划"
      description="当前计划结构与最近一次调整"
      status={state.status}
      onRetry={onRetry}
      errorMessage={state.message}
      empty={!plan}
      emptyText="当前没有训练计划"
    >
      {plan ? (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap gap-4">
            <span>周起始日：{formatAdminDate(plan.week_start)}</span>
            <span>难度系数：{formatAdminNumber(plan.difficulty_factor)}</span>
            <span>状态：{plan.status}</span>
          </div>
          {plan.week_structure.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="pb-2 font-medium">周几</th>
                    <th className="pb-2 font-medium">训练重点</th>
                    <th className="pb-2 font-medium">动作数</th>
                    <th className="pb-2 font-medium">总组数</th>
                    <th className="pb-2 font-medium">预计时长</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.week_structure.map((day) => (
                    <tr key={day.day} className="border-b last:border-0">
                      <td className="py-2">周{day.day}</td>
                      <td className="py-2">
                        {day.focus}
                        {day.is_rest_day ? "（休息日）" : ""}
                      </td>
                      <td className="py-2">{day.exercise_count}</td>
                      <td className="py-2">{day.total_sets}</td>
                      <td className="py-2">{day.estimated_duration} 分钟</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted-foreground">暂无周结构数据</p>
          )}
          <div className="rounded-md bg-muted/50 p-3">
            <p className="font-medium">最近一次调整</p>
            {adjustment ? (
              <p className="text-muted-foreground">
                {ADJUSTMENT_DIRECTION_LABEL[adjustment.direction] ?? adjustment.direction}，
                完成率 {Math.round(adjustment.completion_rate * 100)}%，
                {formatAdminDateTime(adjustment.occurred_at)}：{adjustment.reason}
              </p>
            ) : (
              <p className="text-muted-foreground">这份计划从未被调整过</p>
            )}
          </div>
        </div>
      ) : null}
    </AdminSectionCard>
  )
}

function CheckinsCard({ state, onRetry }: { state: SectionState; onRetry: () => void }) {
  const checkins = state.data?.checkins
  return (
    <AdminSectionCard
      title="打卡记录"
      description="近 90 天序列与连续性"
      status={state.status}
      onRetry={onRetry}
      errorMessage={state.message}
      empty={!checkins || checkins.series.length === 0}
      emptyText="近 90 天没有打卡记录"
    >
      {checkins && checkins.series.length > 0 ? (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-4">
            <span>连续打卡：{checkins.streak_days} 天</span>
            <span>累计打卡：{checkins.total_checkins} 次</span>
            <span>
              完成率分布：
              {Object.entries(checkins.completion_rate_distribution)
                .map(([bucket, count]) => `${bucket}% ${count} 次`)
                .join("，") || "—"}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-2 font-medium">训练日期</th>
                  <th className="pb-2 font-medium">完成率</th>
                  <th className="pb-2 font-medium">时长（分钟）</th>
                  <th className="pb-2 font-medium">难度自评</th>
                </tr>
              </thead>
              <tbody>
                {checkins.series.map((point) => (
                  <tr key={point.workout_date} className="border-b last:border-0">
                    <td className="py-2">{formatAdminDate(point.workout_date)}</td>
                    <td className="py-2">{Math.round(point.completion_rate * 100)}%</td>
                    <td className="py-2">{point.duration_minutes}</td>
                    <td className="py-2">{point.difficulty_rating ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </AdminSectionCard>
  )
}

function WeightsCard({ state, onRetry }: { state: SectionState; onRetry: () => void }) {
  const weights = state.data?.weights
  return (
    <AdminSectionCard
      title="体重记录"
      description="近 90 天序列与记录频率"
      status={state.status}
      onRetry={onRetry}
      errorMessage={state.message}
      empty={!weights || weights.series.length === 0}
      emptyText="近 90 天没有体重记录"
    >
      {weights && weights.series.length > 0 ? (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-4">
            <span>记录条数：{weights.record_count}</span>
            <span>平均每周：{weights.records_per_week} 条</span>
            <span>最近体重：{formatAdminNumber(weights.latest_weight)} kg</span>
            <span>最近记录：{formatAdminDate(weights.last_recorded_date)}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-2 font-medium">日期</th>
                  <th className="pb-2 font-medium">体重（kg）</th>
                </tr>
              </thead>
              <tbody>
                {weights.series.map((point) => (
                  <tr key={point.recorded_date} className="border-b last:border-0">
                    <td className="py-2">{formatAdminDate(point.recorded_date)}</td>
                    <td className="py-2">{point.weight}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </AdminSectionCard>
  )
}

const TIMELINE_EVENT_LABEL: Record<string, string> = {
  registered: "注册",
  first_body_analysis: "首次体型分析",
  latest_body_analysis: "最近一次体型分析",
  first_plan_generated: "首次生成计划",
  latest_plan_adjustment: "最近一次计划调整",
  first_checkin: "首次打卡",
  latest_checkin: "最近一次打卡",
  first_weight_record: "首次体重记录",
  latest_weight_record: "最近一次体重记录",
  latest_chat: "最近一次对话",
}

function TimelineCard({ state, onRetry }: { state: SectionState; onRetry: () => void }) {
  const timeline = state.data?.timeline
  return (
    <AdminSectionCard
      title="行为轨迹"
      description="由既有数据派生的关键节点"
      status={state.status}
      onRetry={onRetry}
      errorMessage={state.message}
      empty={!timeline || timeline.items.length === 0}
      emptyText="暂无行为轨迹"
    >
      {timeline && timeline.items.length > 0 ? (
        <ol className="space-y-3 text-sm">
          {timeline.items.map((event, index) => (
            <li key={`${event.type}-${index}`} className="flex gap-3">
              <span className="mt-0.5 text-muted-foreground">{formatAdminDateTime(event.occurred_at)}</span>
              <span>
                <span className="font-medium">
                  {TIMELINE_EVENT_LABEL[event.type] ?? event.type}
                </span>
                <span className="text-muted-foreground">：{event.message || event.summary}</span>
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </AdminSectionCard>
  )
}

function UsageCard({ state, onRetry }: { state: SectionState; onRetry: () => void }) {
  const usage = state.data?.usage
  return (
    <AdminSectionCard
      title="AI 使用情况"
      description="只暴露 Key 状态与对话计数，不含消息内容"
      status={state.status}
      onRetry={onRetry}
      errorMessage={state.message}
      empty={!usage}
      emptyText="暂无用量数据"
    >
      {usage ? (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground">API Key</dt>
          <dd>{usage.has_api_key ? `已配置（${usage.llm_provider ?? "未知"}）` : "未配置"}</dd>
          <dt className="text-muted-foreground">对话消息</dt>
          <dd>{usage.chat_message_count} 条</dd>
          <dt className="text-muted-foreground">用户 / AI</dt>
          <dd>
            {usage.user_message_count} / {usage.assistant_message_count}
          </dd>
          <dt className="text-muted-foreground">最近对话</dt>
          <dd>{formatAdminDateTime(usage.last_chat_at)}</dd>
        </dl>
      ) : null}
    </AdminSectionCard>
  )
}

export default function AdminUserDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const userId = Number(id)
  const validUserId = Number.isSafeInteger(userId) && userId > 0

  const profile = useAdminUserSection(validUserId ? userId : null, "profile")
  const bodyAnalysis = useAdminUserSection(validUserId ? userId : null, "body_analysis")
  const plan = useAdminUserSection(validUserId ? userId : null, "plan")
  const checkins = useAdminUserSection(validUserId ? userId : null, "checkins")
  const weights = useAdminUserSection(validUserId ? userId : null, "weights")
  const timeline = useAdminUserSection(validUserId ? userId : null, "timeline")
  const usage = useAdminUserSection(validUserId ? userId : null, "usage")

  const goBack = useCallback(() => {
    const from = (location.state as { from?: string } | null)?.from
    navigate(typeof from === "string" ? from : "/admin/users")
  }, [location.state, navigate])

  if (!validUserId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">用户详情</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p role="alert" className="text-sm text-destructive">
            加载失败：用户 ID 无效
          </p>
          <Button variant="outline" size="sm" onClick={goBack}>
            <ArrowLeft className="h-3.5 w-3.5" />
            返回用户列表
          </Button>
        </CardContent>
      </Card>
    )
  }

  const profileState = profile.state
  const nickname =
    profileState.status === "ready" ? profileState.data?.profile?.nickname : undefined

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">用户详情</h1>
          <p className="text-muted-foreground">
            用户 #{userId}
            {nickname ? ` · ${nickname}` : ""}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={goBack}>
          <ArrowLeft className="h-3.5 w-3.5" />
          返回用户列表
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ProfileCard state={profile.state} onRetry={profile.retry} />
        <BodyAnalysisCard state={bodyAnalysis.state} onRetry={bodyAnalysis.retry} />
        <div className="lg:col-span-2">
          <PlanCard state={plan.state} onRetry={plan.retry} />
        </div>
        <CheckinsCard state={checkins.state} onRetry={checkins.retry} />
        <WeightsCard state={weights.state} onRetry={weights.retry} />
        <TimelineCard state={timeline.state} onRetry={timeline.retry} />
        <UsageCard state={usage.state} onRetry={usage.retry} />
      </div>
    </div>
  )
}
