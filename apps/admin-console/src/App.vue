<template>
  <div class="layout">
    <aside class="sidebar">
      <h1>练了么后台</h1>
      <ul>
        <li v-for="item in menus" :key="item" :class="{ active: item === active }" @click="active = item">{{ item }}</li>
      </ul>
    </aside>

    <main class="content">
      <header>
        <h2>{{ active }}</h2>
        <p>运营中台 V1</p>
      </header>

      <section class="cards" v-if="active === '数据看板'">
        <article class="card"><span>总用户</span><strong>12,840</strong></article>
        <article class="card"><span>日活</span><strong>1,250</strong></article>
        <article class="card"><span>训练完成</span><strong>45,200</strong></article>
      </section>

      <section class="panel" v-else>
        <p>{{ active }} 模块已接入网关 `/v1/admin/*`，用于后续对接真实数据。</p>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

// Why: keep V1 admin scope aligned with approved modules only.
// Scope: dashboard, user, recipe, workout template, AI config navigation.
// Verify: page renders five modules and can switch active panel.
const menus = ['数据看板', '用户管理', '菜谱管理', '训练模板', 'AI配置']
const active = ref('数据看板')
</script>

<style scoped>
:root {
  --brand: #f21162;
  --brand2: #ff7a45;
  --bg: #f7f8fc;
  --ink: #1c2233;
}

.layout {
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

header h2 {
  margin: 0;
  color: var(--ink);
}

header p {
  margin-top: 6px;
  color: #778099;
}

.cards {
  margin-top: 20px;
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
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

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .cards {
    grid-template-columns: 1fr;
  }
}
</style>
