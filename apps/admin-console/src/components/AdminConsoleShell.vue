<template>
  <!-- mount the existing admin console only after authentication succeeds; authenticated admin shell only; verify with npm --workspace apps/admin-console run build -->
  <div class="app-frame">
    <section class="console-shell">
      <SidebarNav
        :modules="modules"
        :active-module="activeModule"
        :operator="props.operator"
        @navigate="setActiveModule"
        @logout="emit('logout')"
      />

      <main class="console-main">
        <TopBar
          v-model:search="activeSearch"
          :placeholder="searchPlaceholder"
          :operator="props.operator"
          :busy="currentStatus === 'loading'"
          :notice-count="3"
          @refresh="refreshActiveModule"
        />

        <div class="console-content">
          <!-- frame each admin module with a high-level command hero so the console feels intentional before operators reach the dense tables and forms; admin shell chrome only; verify with npm --workspace apps/admin-console run build and visual tests. -->
          <section class="console-hero">
            <div class="console-hero__copy">
              <span class="console-hero__eyebrow">{{ activeModule.toUpperCase() }}</span>
              <h1>{{ activeMeta.title }}</h1>
              <p>{{ activeMeta.subtitle }}</p>
            </div>

            <div class="console-hero__stats">
              <article class="console-hero__stat">
                <span>当前会话</span>
                <strong>{{ currentStatusLabel }}</strong>
              </article>
              <article class="console-hero__stat">
                <span>数据入口</span>
                <strong>/v1/admin/*</strong>
              </article>
              <article class="console-hero__stat">
                <span>操作身份</span>
                <strong>{{ props.operator.roleLabel }}</strong>
              </article>
            </div>
          </section>

          <section class="section-head">
            <div>
              <h1>模块工作台</h1>
              <p>围绕当前模块的主操作、筛选和反馈在这里完成。</p>
            </div>
            <button v-if="primaryActionLabel" class="primary-button" type="button" @click="handlePrimaryAction">
              <AppIcon name="plus" :size="16" />
              {{ primaryActionLabel }}
            </button>
          </section>

          <section v-if="currentStatus === 'loading'" class="state-panel state-panel--loading">
            <span class="spinner" />
            <div>
              <strong>正在同步 {{ activeMeta.title }}</strong>
              <p>从 `/v1/admin/*` 拉取最新数据，并重建当前会话视图。</p>
            </div>
          </section>

          <section v-else-if="currentStatus === 'error'" class="state-panel state-panel--error">
            <div>
              <strong>模块加载失败</strong>
              <p>{{ currentError }}</p>
            </div>
            <button class="ghost-button" type="button" @click="refreshActiveModule">重试加载</button>
          </section>

          <DashboardView
            v-else-if="activeModule === 'dashboard'"
            :model="dashboardModel"
            :search="dashboardSearch"
            @navigate="setActiveModule"
          />

          <RecipesView
            v-else-if="activeModule === 'recipes'"
            :summary-cards="recipeSummaryCards"
            :filters="recipeFilters"
            :category-options="recipeCategoryOptions"
            :difficulty-options="recipeDifficultyOptions"
            :records="paginatedRecipes"
            :total-count="filteredRecipesCount"
            :all-count="recipes.length"
            :selected-ids="selectedRecipeIds"
            :all-visible-selected="allVisibleRecipesSelected"
            :page="recipePage"
            :page-count="recipePageCount"
            :modal="recipeModal"
            :preview-record="previewRecipe"
            @open-create="openRecipeCreate"
            @edit="openRecipeEdit"
            @save="saveRecipe"
            @preview="openRecipePreview"
            @close-preview="previewRecipeId = null"
            @close-modal="closeRecipeModal"
            @delete-one="openDeleteRecipe"
            @delete-selected="openDeleteRecipes"
            @toggle-select="toggleRecipeSelection"
            @toggle-select-all="toggleSelectAllRecipes"
            @page="changeRecipePage"
          />

          <UsersView
            v-else-if="activeModule === 'users'"
            :summary-cards="userSummaryCards"
            :filters="userFilters"
            :status-options="userStatusOptions"
            :records="paginatedUsers"
            :total-count="filteredUsersCount"
            :all-count="users.length"
            :selected-ids="selectedUserIds"
            :all-visible-selected="allVisibleUsersSelected"
            :page="userPage"
            :page-count="userPageCount"
            :modal="userModal"
            :preview-record="previewUser"
            @open-create="openUserCreate"
            @edit="openUserEdit"
            @save="saveUser"
            @preview="openUserPreview"
            @close-preview="previewUserId = null"
            @close-modal="closeUserModal"
            @delete-one="openDeleteUser"
            @delete-selected="openDeleteUsers"
            @toggle-select="toggleUserSelection"
            @toggle-select-all="toggleSelectAllUsers"
            @toggle-status="toggleUserStatus"
            @page="changeUserPage"
          />

          <SettingsView
            v-else
            :settings="settingsState"
            :section="settingsSection"
            :dirty="settingsDirty"
            :save-feedback="saveFeedback"
            :search="settingsSearch"
            @save="saveSettings"
            @reset="resetSettings"
            @open-section="settingsSection = $event"
          />
        </div>
      </main>
    </section>

    <BaseModal
      :open="confirmDialog.open"
      :title="confirmDialog.title"
      :description="confirmDialog.description"
      @close="closeConfirmDialog"
    >
      <template #footer>
        <button class="ghost-button" type="button" @click="closeConfirmDialog">取消</button>
        <button class="primary-button primary-button--danger" type="button" @click="confirmDestructiveAction">
          {{ confirmDialog.actionLabel }}
        </button>
      </template>
    </BaseModal>

    <transition name="fade-up">
      <div v-if="toast.visible" class="floating-toast">
        <AppIcon name="sparkles" :size="16" />
        {{ toast.message }}
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { AdminSession } from '../types/admin'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'
import SidebarNav from './SidebarNav.vue'
import TopBar from './TopBar.vue'
import { useAdminConsole } from '../composables/useAdminConsole'
import DashboardView from '../views/DashboardView.vue'
import RecipesView from '../views/RecipesView.vue'
import SettingsView from '../views/SettingsView.vue'
import UsersView from '../views/UsersView.vue'

const props = defineProps<{
  operator: AdminSession
}>()

// keep logout handling at the auth gate while leaving module CRUD behavior unchanged; authenticated console shell events only; verify with npm --workspace apps/admin-console run build
const emit = defineEmits<{
  logout: []
}>()

const {
  modules,
  pageMeta,
  activeModule,
  activeSearch,
  searchPlaceholder,
  currentStatus,
  currentError,
  toast,
  confirmDialog,
  saveFeedback,
  dashboardSearch,
  dashboardModel,
  recipes,
  users,
  settingsSection,
  settingsState,
  settingsDirty,
  recipeFilters,
  userFilters,
  settingsSearch,
  recipeSummaryCards,
  userSummaryCards,
  recipeCategoryOptions,
  recipeDifficultyOptions,
  userStatusOptions,
  recipePage,
  userPage,
  recipePageCount,
  userPageCount,
  paginatedRecipes,
  paginatedUsers,
  selectedRecipeIds,
  selectedUserIds,
  allVisibleRecipesSelected,
  allVisibleUsersSelected,
  recipeModal,
  userModal,
  previewRecipeId,
  previewUserId,
  previewRecipe,
  previewUser,
  setActiveModule,
  refreshActiveModule,
  openRecipeCreate,
  openRecipeEdit,
  saveRecipe,
  openDeleteRecipe,
  openDeleteRecipes,
  openUserCreate,
  openUserEdit,
  saveUser,
  toggleUserStatus,
  openDeleteUser,
  openDeleteUsers,
  closeConfirmDialog,
  confirmDestructiveAction,
  toggleRecipeSelection,
  toggleUserSelection,
  toggleSelectAllRecipes,
  toggleSelectAllUsers,
  changeRecipePage,
  changeUserPage,
  saveSettings,
  resetSettings,
} = useAdminConsole()

const activeMeta = computed(() => pageMeta[activeModule.value])
const currentStatusLabel = computed(() => {
  if (currentStatus.value === 'loading') {
    return '同步中'
  }

  if (currentStatus.value === 'error') {
    return '需重试'
  }

  return '已就绪'
})
const filteredRecipesCount = computed(() => {
  const keyword = recipeFilters.keyword.trim().toLowerCase()
  return recipes.value.filter((record) => {
    const matchesKeyword =
      !keyword || [record.name, record.subtitle, record.scene, record.tags.join(' ')].join(' ').toLowerCase().includes(keyword)
    const matchesCategory = recipeFilters.category === '全部' || record.category === recipeFilters.category
    const matchesDifficulty = recipeFilters.difficulty === '全部' || record.difficulty === recipeFilters.difficulty
    return matchesKeyword && matchesCategory && matchesDifficulty
  }).length
})
const filteredUsersCount = computed(() => {
  const keyword = userFilters.keyword.trim().toLowerCase()
  return users.value.filter((record) => {
    const matchesKeyword =
      !keyword || [record.nickname, record.email, record.tags.join(' '), record.segment].join(' ').toLowerCase().includes(keyword)
    const matchesStatus = userFilters.status === '全部' || record.status === userFilters.status
    return matchesKeyword && matchesStatus
  }).length
})
const primaryActionLabel = computed(() => {
  if (activeModule.value === 'recipes') {
    return '添加新菜谱'
  }
  if (activeModule.value === 'users') {
    return '新增用户'
  }
  return ''
})

const handlePrimaryAction = () => {
  if (activeModule.value === 'recipes') {
    openRecipeCreate()
    return
  }
  if (activeModule.value === 'users') {
    openUserCreate()
  }
}

const closeRecipeModal = () => {
  recipeModal.open = false
  recipeModal.error = ''
}

const closeUserModal = () => {
  userModal.open = false
  userModal.error = ''
}

const openRecipePreview = (recipeId: string) => {
  previewRecipeId.value = recipeId
}

const openUserPreview = (userId: string) => {
  previewUserId.value = userId
}
</script>
