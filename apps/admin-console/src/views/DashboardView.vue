<template>
  <!-- dashboard landing view; combines KPI cards, trend chart and action hub in one high-fidelity canvas; verify with vite build -->
  <div v-if="model" class="dashboard-view">
    <section class="metric-grid">
      <article v-for="card in model.heroCards" :key="card.key" class="metric-card">
        <div class="metric-card__head">
          <span class="metric-card__icon">
            <AppIcon :name="card.icon" :size="16" />
          </span>
          <span class="metric-card__delta">{{ card.deltaLabel }}</span>
        </div>
        <span class="metric-card__label">{{ card.label }}</span>
        <strong class="metric-card__value">{{ card.value }}</strong>
      </article>
    </section>

    <section class="dashboard-grid">
      <article class="glass-card chart-card">
        <div class="section-title">
          <div>
            <h3>活跃趋势</h3>
            <p>注册增长与平均激活率对比</p>
          </div>
          <span class="section-chip">最近 6 个月</span>
        </div>
        <svg class="trend-chart" viewBox="0 0 560 280" role="img" aria-label="活跃趋势图">
          <defs>
            <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="rgba(242,17,98,0.28)" />
              <stop offset="100%" stop-color="rgba(242,17,98,0.04)" />
            </linearGradient>
          </defs>
          <path class="trend-chart__area" :d="areaPath" fill="url(#trendFill)" />
          <path class="trend-chart__line" :d="linePath" />
          <g v-for="point in chartPoints" :key="point.label">
            <circle :cx="point.x" :cy="point.y" r="5" class="trend-chart__dot" />
            <text :x="point.x" y="258" text-anchor="middle" class="trend-chart__label">
              {{ point.label }}
            </text>
          </g>
        </svg>
      </article>

      <article class="glass-card nutrition-card">
        <div class="section-title">
          <div>
            <h3>营养分配</h3>
            <p>平台平均用户热量摄入结构</p>
          </div>
        </div>
        <div class="nutrition-ring">
          <svg viewBox="0 0 160 160" role="img" aria-label="营养占比环图">
            <circle cx="80" cy="80" r="46" class="nutrition-ring__track" />
            <circle
              v-for="segment in ringSegments"
              :key="segment.label"
              cx="80"
              cy="80"
              r="46"
              class="nutrition-ring__segment"
              :style="{
                strokeDasharray: `${segment.length} ${circumference}`,
                strokeDashoffset: `${segment.offset}`,
                stroke: segment.color,
              }"
            />
          </svg>
          <div class="nutrition-ring__center">
            <strong>{{ model.nutrition.totalCaloriesLabel }}</strong>
            <span>平均卡千</span>
          </div>
        </div>
        <ul class="legend-list">
          <li v-for="segment in model.nutrition.segments" :key="segment.label" class="legend-list__item">
            <span class="legend-list__meta">
              <i :class="['legend-dot', `legend-dot--${segment.tone}`]" />
              {{ segment.label }}
            </span>
            <strong>{{ segment.value }}%</strong>
          </li>
        </ul>
      </article>
    </section>

    <section class="dashboard-grid dashboard-grid--bottom">
      <article class="glass-card">
        <div class="section-title">
          <div>
            <h3>最新用户</h3>
            <p>重点关注最近活跃与减脂目标进度</p>
          </div>
        </div>
        <table class="data-table data-table--compact">
          <thead>
            <tr>
              <th>用户</th>
              <th>状态</th>
              <th>当前体重</th>
              <th>目标</th>
              <th>最近活跃</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in filteredRecentUsers" :key="user.userId">
              <td>
                <div class="identity-cell">
                  <div class="identity-cell__avatar">{{ user.avatarLabel }}</div>
                  <div>
                    <strong>{{ user.nickname }}</strong>
                    <p>{{ user.email }}</p>
                  </div>
                </div>
              </td>
              <td><span class="pill" :class="statusToneClass(user.status)">{{ user.status }}</span></td>
              <td>{{ user.currentWeightKg }} kg</td>
              <td>{{ user.goalLabel }}</td>
              <td>{{ user.lastActiveLabel }}</td>
            </tr>
          </tbody>
        </table>
      </article>

      <div class="dashboard-stack">
        <article class="glass-card">
          <div class="section-title">
            <div>
              <h3>快捷入口</h3>
              <p>常用运营动作一键跳转</p>
            </div>
          </div>
          <div class="quick-action-list">
            <button
              v-for="action in filteredActions"
              :key="action.title"
              type="button"
              class="quick-action"
              @click="emit('navigate', action.target)"
            >
              <div>
                <strong>{{ action.title }}</strong>
                <p>{{ action.description }}</p>
              </div>
              <AppIcon name="chevronRight" :size="16" />
            </button>
          </div>
        </article>

        <article class="glass-card">
          <div class="section-title">
            <div>
              <h3>最新动态</h3>
              <p>跨模块的最近管理操作流</p>
            </div>
          </div>
          <div class="activity-list">
            <article v-for="item in filteredActivities" :key="item.id" class="activity-item">
              <span class="activity-item__dot" />
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.detail }}</p>
                <span>{{ item.module }} · {{ item.timeLabel }}</span>
              </div>
            </article>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { AdminModuleKey, DashboardViewModel } from '../types/admin'
import AppIcon from '../components/AppIcon.vue'

const props = defineProps<{
  model: DashboardViewModel | null
  search: string
}>()

const emit = defineEmits<{
  navigate: [module: AdminModuleKey]
}>()

const chartPoints = computed(() => {
  const source = props.model?.trend.points ?? []
  if (source.length === 0) {
    return []
  }

  const width = 520
  const height = 220
  const offsetX = 20
  const offsetY = 18
  const step = width / Math.max(1, source.length - 1)
  const maxValue = Math.max(...source.map((point) => point.value)) * 1.15

  return source.map((point, index) => ({
    ...point,
    x: offsetX + step * index,
    y: height - (point.value / maxValue) * 150 - offsetY,
  }))
})

const linePath = computed(() =>
  chartPoints.value.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' '),
)

const areaPath = computed(() => {
  if (chartPoints.value.length === 0) {
    return ''
  }
  const first = chartPoints.value[0]
  const last = chartPoints.value[chartPoints.value.length - 1]
  return `${linePath.value} L ${last.x} 230 L ${first.x} 230 Z`
})

const circumference = 2 * Math.PI * 46

const ringSegments = computed(() => {
  let consumed = 0
  return (props.model?.nutrition.segments ?? []).map((segment) => {
    const length = (segment.value / 100) * circumference
    const offset = circumference * 0.25 - consumed
    consumed += length
    return {
      ...segment,
      length,
      offset,
      color:
        segment.tone === 'brand' ? 'var(--brand-primary)' : segment.tone === 'accent' ? '#ff8fb1' : '#ffd1de',
    }
  })
})

const normalizedSearch = computed(() => props.search.trim().toLowerCase())

const filteredRecentUsers = computed(() => {
  const keyword = normalizedSearch.value
  const users = props.model?.recentUsers ?? []
  if (!keyword) {
    return users
  }
  return users.filter((user) => [user.nickname, user.email, user.goalLabel].join(' ').toLowerCase().includes(keyword))
})

const filteredActions = computed(() => {
  const keyword = normalizedSearch.value
  const actions = props.model?.quickActions ?? []
  if (!keyword) {
    return actions
  }
  return actions.filter((action) => [action.title, action.description].join(' ').toLowerCase().includes(keyword))
})

const filteredActivities = computed(() => {
  const keyword = normalizedSearch.value
  const activities = props.model?.recentActivities ?? []
  if (!keyword) {
    return activities
  }
  return activities.filter((activity) => [activity.title, activity.detail, activity.module].join(' ').toLowerCase().includes(keyword))
})

const statusToneClass = (status: string) => ({
  'pill--success': status === '活跃' || status === '高价值',
  'pill--warning': status === '观察',
  'pill--muted': status === '休眠',
})
</script>
