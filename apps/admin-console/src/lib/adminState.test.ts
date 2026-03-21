import { describe, expect, it } from 'vitest'

import {
  buildDashboardViewModel,
  buildRecipeRecords,
  buildSettingsFormState,
  buildUserRecords,
} from './adminState'

describe('buildUserRecords', () => {
  it('enriches admin users into stable CRM-style records', () => {
    const records = buildUserRecords([
      { user_id: 'u_1001', nickname: 'Sarah', weight_kg: 64.2, goal_weight_kg: 58 },
      { user_id: 'u_1002', nickname: 'Marcus', weight_kg: 92.5, goal_weight_kg: 85 },
    ])

    expect(records).toHaveLength(2)
    expect(records[0]).toMatchObject({
      userId: 'u_1001',
      nickname: 'Sarah',
      status: '活跃',
      segment: '燃脂会员',
      progressPercent: 58,
      tags: ['高留存', '控卡中'],
    })
    expect(records[1].status).toBe('观察')
    expect(records[1].lastActiveLabel).toContain('昨天')
  })
})

describe('buildRecipeRecords', () => {
  it('maps recipes into rich catalog rows and preserves calories', () => {
    const records = buildRecipeRecords([
      { recipe_id: 'r1', name: '手撕鸡胸肉', calories: 210, tag: '高蛋白' },
      { recipe_id: 'r2', name: '黄瓜沙拉', calories: 85, tag: '低碳水' },
    ])

    expect(records[0]).toMatchObject({
      recipeId: 'r1',
      calories: 210,
      category: '燃脂午餐',
      difficulty: '简单',
      tags: ['高蛋白', '低油'],
    })
    expect(records[1].durationMinutes).toBeGreaterThan(0)
    expect(records[1].steps.length).toBeGreaterThan(2)
  })
})

describe('buildSettingsFormState', () => {
  it('combines template and ai config data into editable settings', () => {
    const state = buildSettingsFormState(
      [
        { template_id: 'w1', name: '减脂入门4周', level: 'beginner' },
        { template_id: 'w2', name: '燃脂间歇训练', level: 'intermediate' },
      ],
      {
        text_model: 'deepseek-v3.2',
        vision_model: 'qwen3-vl-flash',
        voice_enabled: false,
        safety_mode: 'health_management_only',
      },
    )

    expect(state.general.appName).toBe('练了么后台')
    expect(state.templates.items[0].levelLabel).toBe('新手友好')
    expect(state.ai.modes[0].active).toBe(true)
    expect(state.ai.voiceEnabled).toBe(false)
  })
})

describe('buildDashboardViewModel', () => {
  it('creates dashboard cards and nutrition rings from API seeds', () => {
    const users = buildUserRecords([
      { user_id: 'u_1001', nickname: 'Sarah', weight_kg: 64.2, goal_weight_kg: 58 },
      { user_id: 'u_1002', nickname: 'Marcus', weight_kg: 92.5, goal_weight_kg: 85 },
    ])
    const recipes = buildRecipeRecords([{ recipe_id: 'r1', name: '手撕鸡胸肉', calories: 210, tag: '高蛋白' }])
    const viewModel = buildDashboardViewModel(
      {
        users_total: 12840,
        daily_active: 1250,
        workouts_total: 45200,
        calories_burned_total: 1200000,
      },
      users,
      recipes,
    )

    expect(viewModel.heroCards[0].value).toBe('12,840')
    expect(viewModel.nutrition.totalCaloriesLabel).toBe('2,450')
    expect(viewModel.recentUsers[0].nickname).toBe('Sarah')
    expect(viewModel.trend.points).toHaveLength(6)
  })
})
