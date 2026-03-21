<template>
  <!-- recipe management module; combines searchable catalog, CRUD modal and preview drawer for prototype-grade operations; verify with vite build -->
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
          <input v-model="filters.keyword" type="text" placeholder="搜索菜谱名称、标签或食材..." />
        </label>

        <div class="filters-bar__group">
          <label class="select-shell">
            <span>分类</span>
            <select v-model="filters.category">
              <option v-for="option in categoryOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </label>
          <label class="select-shell">
            <span>难度</span>
            <select v-model="filters.difficulty">
              <option v-for="option in difficultyOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </label>
          <button class="ghost-button" type="button" @click="emit('open-create')">
            <AppIcon name="plus" :size="16" />
            添加新菜谱
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
            <th>菜谱名称</th>
            <th>热量</th>
            <th>难度</th>
            <th>准备时间</th>
            <th>分类</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="recipe in records" :key="recipe.recipeId">
            <td>
              <input
                :checked="selectedIds.includes(recipe.recipeId)"
                type="checkbox"
                @change="emit('toggle-select', recipe.recipeId)"
              />
            </td>
            <td>
              <div class="recipe-cell">
                <div class="recipe-thumb" :style="{ background: recipe.imageAccent }" />
                <div>
                  <strong>{{ recipe.name }}</strong>
                  <p>{{ recipe.subtitle }}</p>
                </div>
              </div>
            </td>
            <td>{{ recipe.calories }} kcal</td>
            <td><span class="pill pill--success">{{ recipe.difficulty }}</span></td>
            <td>{{ recipe.durationMinutes }} 分钟</td>
            <td>
              <div class="tag-list">
                <span v-for="tag in recipe.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
            </td>
            <td>
              <div class="table-actions">
                <button class="icon-button icon-button--soft" type="button" @click="emit('preview', recipe.recipeId)">
                  <AppIcon name="eye" :size="15" />
                </button>
                <button class="icon-button icon-button--soft" type="button" @click="emit('edit', recipe.recipeId)">
                  <AppIcon name="edit" :size="15" />
                </button>
                <button class="icon-button icon-button--soft" type="button" @click="emit('delete-one', recipe.recipeId)">
                  <AppIcon name="trash" :size="15" />
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="records.length === 0">
            <td colspan="7">
              <div class="empty-panel">
                <strong>暂无符合条件的菜谱</strong>
                <p>调整筛选条件，或直接创建一条新的健康菜谱记录。</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <footer class="table-footer">
        <span>当前显示第 {{ page }} / {{ pageCount }} 页，共 {{ totalCount }} 条记录（总库 {{ allCount }}）</span>
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
      :title="modal.mode === 'create' ? '创建菜谱' : '编辑菜谱'"
      description="支持当前会话内的新增、编辑和标签整理。"
      size="lg"
      @close="emit('close-modal')"
    >
      <div class="form-grid">
        <label class="field">
          <span>菜谱名称</span>
          <input v-model="modal.draft.name" type="text" placeholder="例如：手撕鸡胸肉" />
        </label>
        <label class="field">
          <span>副标题</span>
          <input v-model="modal.draft.subtitle" type="text" placeholder="一句话卖点" />
        </label>
        <label class="field">
          <span>热量（kcal）</span>
          <input v-model.number="modal.draft.calories" type="number" min="50" />
        </label>
        <label class="field">
          <span>准备时间（分钟）</span>
          <input v-model.number="modal.draft.durationMinutes" type="number" min="5" />
        </label>
        <label class="field">
          <span>分类</span>
          <input v-model="modal.draft.category" type="text" />
        </label>
        <label class="field">
          <span>难度</span>
          <select v-model="modal.draft.difficulty">
            <option value="简单">简单</option>
            <option value="中等">中等</option>
            <option value="挑战">挑战</option>
          </select>
        </label>
        <label class="field">
          <span>适用场景</span>
          <input v-model="modal.draft.scene" type="text" />
        </label>
        <label class="field">
          <span>渐变封面</span>
          <input v-model="modal.draft.imageAccent" type="text" placeholder="linear-gradient(...)" />
        </label>
        <label class="field field--full">
          <span>标签（逗号分隔）</span>
          <input v-model="modal.draft.tagsText" type="text" placeholder="高蛋白, 低油" />
        </label>
        <div class="nutrition-editor">
          <label class="field">
            <span>蛋白质</span>
            <input v-model.number="modal.draft.nutrition.protein" type="number" min="0" />
          </label>
          <label class="field">
            <span>碳水</span>
            <input v-model.number="modal.draft.nutrition.carbs" type="number" min="0" />
          </label>
          <label class="field">
            <span>脂肪</span>
            <input v-model.number="modal.draft.nutrition.fat" type="number" min="0" />
          </label>
        </div>
        <label class="field field--full">
          <span>制作步骤（每行一步）</span>
          <textarea v-model="modal.draft.stepsText" rows="5" />
        </label>
      </div>
      <p v-if="modal.error" class="form-error">{{ modal.error }}</p>
      <template #footer>
        <button class="ghost-button" type="button" @click="emit('close-modal')">取消</button>
        <button class="primary-button" type="button" @click="emit('save')">保存菜谱</button>
      </template>
    </BaseModal>

    <SideDrawer
      :open="Boolean(previewRecord)"
      :title="previewRecord?.name ?? '菜谱详情'"
      description="查看菜谱营养结构、步骤和适用场景。"
      @close="emit('close-preview')"
    >
      <template v-if="previewRecord">
        <div class="drawer-banner" :style="{ background: previewRecord.imageAccent }" />
        <div class="drawer-metric-list">
          <article class="drawer-metric">
            <span>分类</span>
            <strong>{{ previewRecord.category }}</strong>
          </article>
          <article class="drawer-metric">
            <span>准备时间</span>
            <strong>{{ previewRecord.durationMinutes }} 分钟</strong>
          </article>
          <article class="drawer-metric">
            <span>热量</span>
            <strong>{{ previewRecord.calories }} kcal</strong>
          </article>
        </div>
        <div class="tag-list">
          <span v-for="tag in previewRecord.tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
        <section class="drawer-section">
          <h4>营养组成</h4>
          <ul class="detail-list">
            <li>蛋白质：{{ previewRecord.nutrition.protein }} g</li>
            <li>碳水：{{ previewRecord.nutrition.carbs }} g</li>
            <li>脂肪：{{ previewRecord.nutrition.fat }} g</li>
          </ul>
        </section>
        <section class="drawer-section">
          <h4>适用场景</h4>
          <p>{{ previewRecord.scene }}</p>
        </section>
        <section class="drawer-section">
          <h4>制作步骤</h4>
          <ol class="step-list">
            <li v-for="step in previewRecord.steps" :key="step">{{ step }}</li>
          </ol>
        </section>
      </template>
    </SideDrawer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import BaseModal from '../components/BaseModal.vue'
import SideDrawer from '../components/SideDrawer.vue'
import AppIcon from '../components/AppIcon.vue'
import type { ModalState, RecipeDraft, RecipeFilters, RecipeRecord } from '../types/admin'

const props = defineProps<{
  summaryCards: Array<{ label: string; value: string }>
  filters: RecipeFilters
  categoryOptions: string[]
  difficultyOptions: string[]
  records: RecipeRecord[]
  totalCount: number
  allCount: number
  selectedIds: string[]
  allVisibleSelected: boolean
  page: number
  pageCount: number
  modal: ModalState<RecipeDraft>
  previewRecord: RecipeRecord | null
}>()

const emit = defineEmits<{
  'open-create': []
  edit: [recipeId: string]
  save: []
  preview: [recipeId: string]
  'close-preview': []
  'close-modal': []
  'delete-one': [recipeId: string]
  'delete-selected': []
  'toggle-select': [recipeId: string]
  'toggle-select-all': []
  page: [page: number]
}>()

const pageNumbers = computed(() => Array.from({ length: props.pageCount }, (_, index) => index + 1))
</script>
