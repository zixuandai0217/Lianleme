<template>
  <!-- user management module; combines lifecycle overview, detailed table and full CRUD interactions for operator demos; verify with vite build -->
  <div class="module-view">
    <section class="mini-stat-row">
      <article v-for="item in summaryCards" :key="item.label" class="mini-stat">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>

    <section class="glass-card filters-card">
      <div class="filters-bar">
        <label class="inline-search">
          <AppIcon name="search" :size="16" />
          <input v-model="filters.keyword" type="text" placeholder="搜索用户昵称、邮箱或标签..." />
        </label>

        <div class="filters-bar__group">
          <label class="select-shell">
            <span>状态</span>
            <select v-model="filters.status">
              <option v-for="option in statusOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </label>
          <button class="ghost-button" type="button" @click="emit('open-create')">
            <AppIcon name="plus" :size="16" />
            新建用户
          </button>
        </div>
      </div>
    </section>

    <section class="glass-card">
      <div class="bulk-bar">
        <label class="table-check">
          <input :checked="allVisibleSelected" type="checkbox" @change="emit('toggle-select-all')" />
          <span>本页全选</span>
        </label>
        <button v-if="selectedIds.length" class="danger-text-button" type="button" @click="emit('delete-selected')">
          批量删除（{{ selectedIds.length }}）
        </button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th />
            <th>用户</th>
            <th>会员分层</th>
            <th>进度</th>
            <th>状态</th>
            <th>最近活跃</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in records" :key="user.userId">
            <td>
              <input :checked="selectedIds.includes(user.userId)" type="checkbox" @change="emit('toggle-select', user.userId)" />
            </td>
            <td>
              <div class="identity-cell">
                <div class="identity-cell__avatar">{{ user.avatarLabel }}</div>
                <div>
                  <strong>{{ user.nickname }}</strong>
                  <p>{{ user.email }}</p>
                </div>
              </div>
            </td>
            <td>
              <strong>{{ user.segment }}</strong>
              <div class="tag-list">
                <span v-for="tag in user.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
            </td>
            <td>
              <div class="progress-cell">
                <div class="progress-bar">
                  <span :style="{ width: `${user.progressPercent}%` }" />
                </div>
                <strong>{{ user.progressPercent }}%</strong>
              </div>
            </td>
            <td>
              <span class="pill" :class="statusToneClass(user.status)">{{ user.status }}</span>
            </td>
            <td>{{ user.lastActiveLabel }}</td>
            <td>
              <div class="table-actions">
                <button class="icon-button icon-button--soft" type="button" @click="emit('preview', user.userId)">
                  <AppIcon name="eye" :size="15" />
                </button>
                <button class="icon-button icon-button--soft" type="button" @click="emit('edit', user.userId)">
                  <AppIcon name="edit" :size="15" />
                </button>
                <button class="ghost-button ghost-button--compact" type="button" @click="emit('toggle-status', user.userId)">
                  切换状态
                </button>
                <button class="icon-button icon-button--soft" type="button" @click="emit('delete-one', user.userId)">
                  <AppIcon name="trash" :size="15" />
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="records.length === 0">
            <td colspan="7">
              <div class="empty-panel">
                <strong>没有匹配的用户</strong>
                <p>你可以清空搜索条件，或者直接创建一个新的演示用户。</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <footer class="table-footer">
        <span>当前显示第 {{ page }} / {{ pageCount }} 页，共 {{ totalCount }} 位用户（总库 {{ allCount }}）</span>
        <div class="pager">
          <button class="pager-button" type="button" :disabled="page === 1" @click="emit('page', page - 1)">
            <AppIcon name="chevronLeft" :size="16" />
          </button>
          <button
            v-for="pageNumber in pageNumbers"
            :key="pageNumber"
            class="pager-button"
            :class="{ 'pager-button--active': pageNumber === page }"
            type="button"
            @click="emit('page', pageNumber)"
          >
            {{ pageNumber }}
          </button>
          <button class="pager-button" type="button" :disabled="page === pageCount" @click="emit('page', page + 1)">
            <AppIcon name="chevronRight" :size="16" />
          </button>
        </div>
      </footer>
    </section>

    <BaseModal
      :open="modal.open"
      :title="modal.mode === 'create' ? '创建用户' : '编辑用户'"
      description="支持当前会话内的用户创建、修改和标签维护。"
      size="lg"
      @close="emit('close-modal')"
    >
      <div class="form-grid">
        <label class="field">
          <span>昵称</span>
          <input v-model="modal.draft.nickname" type="text" placeholder="例如：Sarah Jenkins" />
        </label>
        <label class="field">
          <span>邮箱</span>
          <input v-model="modal.draft.email" type="email" placeholder="name@fitflow.pro" />
        </label>
        <label class="field">
          <span>当前体重（kg）</span>
          <input v-model.number="modal.draft.currentWeightKg" type="number" min="30" />
        </label>
        <label class="field">
          <span>目标体重（kg）</span>
          <input v-model.number="modal.draft.goalWeightKg" type="number" min="30" />
        </label>
        <label class="field">
          <span>状态</span>
          <select v-model="modal.draft.status">
            <option value="活跃">活跃</option>
            <option value="观察">观察</option>
            <option value="高价值">高价值</option>
            <option value="休眠">休眠</option>
          </select>
        </label>
        <label class="field">
          <span>会员分层</span>
          <input v-model="modal.draft.segment" type="text" />
        </label>
        <label class="field">
          <span>教练归属</span>
          <input v-model="modal.draft.coachName" type="text" />
        </label>
        <label class="field">
          <span>每周训练次数</span>
          <input v-model.number="modal.draft.weeklyWorkouts" type="number" min="0" max="14" />
        </label>
        <label class="field field--full">
          <span>标签（逗号分隔）</span>
          <input v-model="modal.draft.tagsText" type="text" placeholder="高留存, 控卡中" />
        </label>
        <label class="field field--full">
          <span>用户备注</span>
          <textarea v-model="modal.draft.note" rows="4" />
        </label>
      </div>
      <p v-if="modal.error" class="form-error">{{ modal.error }}</p>
      <template #footer>
        <button class="ghost-button" type="button" @click="emit('close-modal')">取消</button>
        <button class="primary-button" type="button" @click="emit('save')">保存用户</button>
      </template>
    </BaseModal>

    <SideDrawer
      :open="Boolean(previewRecord)"
      :title="previewRecord?.nickname ?? '用户详情'"
      description="快速查看训练状态、标签和教练跟进信息。"
      @close="emit('close-preview')"
    >
      <template v-if="previewRecord">
        <div class="user-hero">
          <div class="user-hero__avatar">{{ previewRecord.avatarLabel }}</div>
          <div>
            <strong>{{ previewRecord.nickname }}</strong>
            <p>{{ previewRecord.email }}</p>
            <div class="tag-list">
              <span v-for="tag in previewRecord.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
          </div>
        </div>
        <div class="drawer-metric-list">
          <article class="drawer-metric">
            <span>当前体重</span>
            <strong>{{ previewRecord.currentWeightKg }} kg</strong>
          </article>
          <article class="drawer-metric">
            <span>目标体重</span>
            <strong>{{ previewRecord.goalWeightKg }} kg</strong>
          </article>
          <article class="drawer-metric">
            <span>每周训练</span>
            <strong>{{ previewRecord.weeklyWorkouts }} 次</strong>
          </article>
        </div>
        <section class="drawer-section">
          <h4>训练目标</h4>
          <p>{{ previewRecord.goalLabel }}</p>
        </section>
        <section class="drawer-section">
          <h4>最近活跃</h4>
          <p>{{ previewRecord.lastActiveLabel }} · {{ previewRecord.status }}</p>
        </section>
        <section class="drawer-section">
          <h4>教练备注</h4>
          <p>{{ previewRecord.note }}</p>
        </section>
      </template>
    </SideDrawer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '../components/AppIcon.vue'
import BaseModal from '../components/BaseModal.vue'
import SideDrawer from '../components/SideDrawer.vue'
import type { ModalState, UserDraft, UserFilters, UserRecord } from '../types/admin'

const props = defineProps<{
  summaryCards: Array<{ label: string; value: string }>
  filters: UserFilters
  statusOptions: string[]
  records: UserRecord[]
  totalCount: number
  allCount: number
  selectedIds: string[]
  allVisibleSelected: boolean
  page: number
  pageCount: number
  modal: ModalState<UserDraft>
  previewRecord: UserRecord | null
}>()

const emit = defineEmits<{
  'open-create': []
  edit: [userId: string]
  save: []
  preview: [userId: string]
  'close-preview': []
  'close-modal': []
  'delete-one': [userId: string]
  'delete-selected': []
  'toggle-select': [userId: string]
  'toggle-select-all': []
  'toggle-status': [userId: string]
  page: [page: number]
}>()

const pageNumbers = computed(() => Array.from({ length: props.pageCount }, (_, index) => index + 1))

const statusToneClass = (status: string) => ({
  'pill--success': status === '活跃' || status === '高价值',
  'pill--warning': status === '观察',
  'pill--muted': status === '休眠',
})
</script>
