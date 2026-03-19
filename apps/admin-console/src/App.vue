<template>
  <div class="layout">
    <aside class="sidebar">
      <h1>练了么后台</h1>
      <ul>
        <li v-for="item in menus" :key="item" :class="{ active: item === active }" @click="selectMenu(item)">{{ item }}</li>
      </ul>
    </aside>

    <main class="content">
      <header class="head">
        <div>
          <h2>{{ active }}</h2>
          <p>运营中台 V1</p>
        </div>
        <button class="refresh" :disabled="loading" @click="reloadActive">刷新</button>
      </header>

      <section v-if="loading" class="panel">正在加载 {{ active }} 数据...</section>
      <section v-else-if="error" class="panel error">
        <p>{{ error }}</p>
        <button class="retry" @click="reloadActive">重试</button>
      </section>

      <section class="cards" v-else-if="active === '数据看板' && dashboard">
        <article class="card" v-for="item in dashboardCards" :key="item.label">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </section>

      <section class="panel" v-else-if="active === '用户管理'">
        <table v-if="users.length" class="table">
          <thead>
            <tr>
              <th>用户ID</th>
              <th>昵称</th>
              <th>当前体重(kg)</th>
              <th>目标体重(kg)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.user_id">
              <td>{{ user.user_id }}</td>
              <td>{{ user.nickname }}</td>
              <td>{{ user.weight_kg }}</td>
              <td>{{ user.goal_weight_kg }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty">暂无用户数据</p>
      </section>

      <section class="panel" v-else-if="active === '菜谱管理'">
        <table v-if="recipes.length" class="table">
          <thead>
            <tr>
              <th>菜谱ID</th>
              <th>名称</th>
              <th>热量(kcal)</th>
              <th>标签</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="recipe in recipes" :key="recipe.recipe_id">
              <td>{{ recipe.recipe_id }}</td>
              <td>{{ recipe.name }}</td>
              <td>{{ recipe.calories }}</td>
              <td>{{ recipe.tag }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty">暂无菜谱数据</p>
      </section>

      <section class="panel" v-else-if="active === '训练模板'">
        <table v-if="workoutTemplates.length" class="table">
          <thead>
            <tr>
              <th>模板ID</th>
              <th>名称</th>
              <th>难度级别</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="tpl in workoutTemplates" :key="tpl.template_id">
              <td>{{ tpl.template_id }}</td>
              <td>{{ tpl.name }}</td>
              <td>{{ tpl.level }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty">暂无训练模板数据</p>
      </section>

      <section class="panel" v-else-if="active === 'AI配置'">
        <dl v-if="aiConfigEntries.length" class="kv">
          <template v-for="entry in aiConfigEntries" :key="entry.key">
            <dt>{{ entry.key }}</dt>
            <dd>{{ entry.value }}</dd>
          </template>
        </dl>
        <p v-else class="empty">暂无 AI 配置数据</p>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

type Menu = '数据看板' | '用户管理' | '菜谱管理' | '训练模板' | 'AI配置'

interface DashboardData {
  users_total: number
  daily_active: number
  workouts_total: number
  calories_burned_total: number
}

interface UserItem {
  user_id: string
  nickname: string
  weight_kg: number
  goal_weight_kg: number
}

interface RecipeItem {
  recipe_id: string
  name: string
  calories: number
  tag: string
}

interface WorkoutTemplateItem {
  template_id: string
  name: string
  level: string
}

interface ListPayload<T> {
  items: T[]
}

type AdminPayload = DashboardData | ListPayload<UserItem> | ListPayload<RecipeItem> | ListPayload<WorkoutTemplateItem> | Record<string, unknown> | null

const menus: Menu[] = ['数据看板', '用户管理', '菜谱管理', '训练模板', 'AI配置']
const active = ref<Menu>('数据看板')
const loading = ref(false)
const error = ref('')

const endpointMap: Record<Menu, string> = {
  数据看板: '/v1/admin/dashboard',
  用户管理: '/v1/admin/users',
  菜谱管理: '/v1/admin/recipes',
  训练模板: '/v1/admin/workout-templates',
  AI配置: '/v1/admin/ai-config',
}

const menuData = reactive<Record<Menu, AdminPayload>>({
  数据看板: null,
  用户管理: null,
  菜谱管理: null,
  训练模板: null,
  AI配置: null,
})

const dashboard = computed(() => menuData['数据看板'] as DashboardData | null)
const users = computed(() => (menuData['用户管理'] as ListPayload<UserItem> | null)?.items ?? [])
const recipes = computed(() => (menuData['菜谱管理'] as ListPayload<RecipeItem> | null)?.items ?? [])
const workoutTemplates = computed(() => (menuData['训练模板'] as ListPayload<WorkoutTemplateItem> | null)?.items ?? [])
const aiConfig = computed(() => (menuData['AI配置'] as Record<string, unknown> | null) ?? {})

const dashboardCards = computed(() => {
  if (!dashboard.value) {
    return []
  }

  return [
    { label: '总用户', value: dashboard.value.users_total.toLocaleString() },
    { label: '日活', value: dashboard.value.daily_active.toLocaleString() },
    { label: '训练完成', value: dashboard.value.workouts_total.toLocaleString() },
    { label: '总消耗(kcal)', value: dashboard.value.calories_burned_total.toLocaleString() },
  ]
})

const aiConfigEntries = computed(() => {
  return Object.entries(aiConfig.value).map(([key, value]) => ({
    key,
    value: typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value),
  }))
})

const fetchMenuData = async (menu: Menu, force = false) => {
  // Why: lazily fetch each admin module to reduce first paint latency and avoid stale placeholders.
  // Scope: all `/v1/admin/*` data loading for dashboard/users/recipes/templates/AI config.
  // Verify: switching each menu renders real gateway data with loading/error/empty states.
  if (!force && menuData[menu]) {
    return
  }

  loading.value = true
  error.value = ''

  try {
    const response = await fetch(endpointMap[menu])
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`)
    }
    menuData[menu] = await response.json()
  } catch (err) {
    error.value = `加载${menu}失败：${err instanceof Error ? err.message : 'unknown error'}`
  } finally {
    loading.value = false
  }
}

const selectMenu = (menu: Menu) => {
  active.value = menu
}

const reloadActive = async () => {
  await fetchMenuData(active.value, true)
}

watch(
  active,
  (menu) => {
    void fetchMenuData(menu)
  },
  { immediate: true },
)
</script>

<style scoped>
.layout {
  /* Why: avoid scoped `:root` selector rewrite (`[data-v-*]:root`) that breaks CSS variable resolution. */
  /* Scope: admin-console theme variables consumed by sidebar/header/cards/buttons in this component. */
  /* Verify: active menu and action buttons regain gradient + themed text colors in dev/build outputs. */
  --brand: #f21162;
  --brand2: #ff7a45;
  --bg: #f7f8fc;
  --ink: #1c2233;
  min-height: 100vh;
  display: grid;
  grid-template-columns: 260px 1fr;
  background: radial-gradient(circle at 20% 10%, #ffd6e6 0, var(--bg) 40%);
  font-family: 'DIN Alternate', 'Source Han Sans CN', sans-serif;
}

.sidebar {
  background: #fff;
  border-right: 1px solid #eceff6;
  padding: 24px;
}

.sidebar h1 {
  font-size: 24px;
  color: var(--ink);
}

.sidebar ul {
  list-style: none;
  padding: 0;
  margin: 24px 0 0;
  display: grid;
  gap: 10px;
}

.sidebar li {
  cursor: pointer;
  padding: 12px 14px;
  border-radius: 14px;
  color: #646b7d;
}

.sidebar li.active {
  color: #fff;
  background: linear-gradient(135deg, var(--brand), var(--brand2));
}

.content {
  padding: 28px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.head h2 {
  margin: 0;
  color: var(--ink);
}

.head p {
  margin-top: 6px;
  color: #778099;
}

.refresh,
.retry {
  border: none;
  background: linear-gradient(135deg, var(--brand), var(--brand2));
  color: #fff;
  border-radius: 999px;
  padding: 10px 16px;
  cursor: pointer;
}

.refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.cards {
  margin-top: 20px;
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 16px;
}

.card,
.panel {
  background: #fff;
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 10px 30px rgba(242, 17, 98, 0.08);
}

.card span {
  color: #778099;
  display: block;
}

.card strong {
  margin-top: 8px;
  display: block;
  font-size: 32px;
  color: var(--ink);
}

.error p {
  color: #d14343;
  margin-top: 0;
}

.empty {
  color: #778099;
  margin: 0;
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th,
.table td {
  text-align: left;
  border-bottom: 1px solid #eceff6;
  padding: 10px 8px;
}

.table th {
  color: #5b6379;
  font-weight: 700;
}

.kv {
  display: grid;
  grid-template-columns: 180px 1fr;
  margin: 0;
  row-gap: 12px;
}

.kv dt {
  color: #5b6379;
  font-weight: 700;
}

.kv dd {
  margin: 0;
  color: #1c2233;
}

@media (max-width: 1100px) {
  .cards {
    grid-template-columns: repeat(2, minmax(180px, 1fr));
  }
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .cards {
    grid-template-columns: 1fr;
  }

  .head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
