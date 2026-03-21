<template>
  <!-- settings workspace; merges app config, theme, workout presets and AI coach preferences into one operator surface; verify with vite build -->
  <div v-if="settings" class="settings-view">
    <section class="settings-toolbar">
      <div class="settings-tabs">
        <button
          v-for="item in sectionItems"
          :key="item.key"
          class="settings-tab"
          :class="{ 'settings-tab--active': section === item.key }"
          type="button"
          @click="emit('open-section', item.key)"
        >
          {{ item.label }}
        </button>
      </div>
      <div class="settings-actions">
        <span v-if="saveFeedback" class="save-feedback">已保存 · {{ saveFeedback }}</span>
        <button class="ghost-button" type="button" :disabled="!dirty" @click="emit('reset')">重置修改</button>
        <button class="primary-button" type="button" @click="emit('save')">保存修改</button>
      </div>
    </section>

    <section v-if="section === 'general'" class="settings-stack">
      <article class="glass-card settings-card">
        <div class="section-title">
          <div>
            <h3>通用设置</h3>
            <p>管理应用名称、客服邮箱和品牌素材。</p>
          </div>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>应用名称</span>
            <input v-model="settings.general.appName" type="text" />
          </label>
          <label class="field">
            <span>支持邮箱</span>
            <input v-model="settings.general.supportEmail" type="email" />
          </label>
          <label class="field">
            <span>服务区域</span>
            <input v-model="settings.general.region" type="text" />
          </label>
          <article class="upload-panel">
            <div class="upload-panel__icon">
              <AppIcon name="upload" :size="18" />
            </div>
            <div>
              <strong>应用 Logo</strong>
              <p>{{ settings.general.logoHint }}</p>
            </div>
            <button class="ghost-button" type="button">更新 Logo</button>
          </article>
        </div>
      </article>
    </section>

    <section v-else-if="section === 'theme'" class="settings-stack">
      <article class="glass-card settings-card">
        <div class="section-title">
          <div>
            <h3>主题设置</h3>
            <p>统一控制后台色板、字体和表面风格。</p>
          </div>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>主品牌色</span>
            <div class="color-input">
              <span class="color-swatch" :style="{ background: settings.theme.brandHex }" />
              <input v-model="settings.theme.brandHex" type="text" />
            </div>
          </label>
          <label class="field">
            <span>强调色</span>
            <div class="color-input">
              <span class="color-swatch" :style="{ background: settings.theme.accentHex }" />
              <input v-model="settings.theme.accentHex" type="text" />
            </div>
          </label>
          <label class="field">
            <span>显示字体</span>
            <input v-model="settings.theme.displayFont" type="text" />
          </label>
          <label class="field">
            <span>表面风格</span>
            <select v-model="settings.theme.surfaceStyle">
              <option value="Soft Light">Soft Light</option>
              <option value="Cream Glass">Cream Glass</option>
              <option value="Editorial Glow">Editorial Glow</option>
            </select>
          </label>
        </div>
      </article>
    </section>

    <section v-else-if="section === 'templates'" class="settings-stack">
      <article class="glass-card settings-card">
        <div class="section-title">
          <div>
            <h3>训练模板</h3>
            <p>管理训练预设的难度层级与启用状态。</p>
          </div>
        </div>
        <div class="template-grid">
          <button
            v-for="item in filteredTemplates"
            :key="item.id"
            class="template-card"
            :class="{ 'template-card--active': item.active }"
            type="button"
            @click="activateTemplate(item.id)"
          >
            <div class="template-card__head">
              <strong>{{ item.name }}</strong>
              <span class="pill pill--soft">{{ item.levelLabel }}</span>
            </div>
            <p>{{ item.description }}</p>
          </button>
        </div>
      </article>
    </section>

    <section v-else class="settings-stack">
      <article class="glass-card settings-card">
        <div class="section-title">
          <div>
            <h3>AI 教练配置</h3>
            <p>控制模型、语气和安全策略。</p>
          </div>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>文本模型</span>
            <input v-model="settings.ai.textModel" type="text" />
          </label>
          <label class="field">
            <span>视觉模型</span>
            <input v-model="settings.ai.visionModel" type="text" />
          </label>
          <label class="field">
            <span>安全模式</span>
            <input v-model="settings.ai.safetyMode" type="text" />
          </label>
          <label class="field field--switch">
            <span>语音能力</span>
            <button class="toggle-switch" :class="{ 'toggle-switch--on': settings.ai.voiceEnabled }" type="button" @click="settings.ai.voiceEnabled = !settings.ai.voiceEnabled">
              <span />
            </button>
          </label>
        </div>

        <div class="mode-grid">
          <button
            v-for="mode in filteredModes"
            :key="mode.key"
            class="mode-card"
            :class="{ 'mode-card--active': mode.active }"
            type="button"
            @click="activateMode(mode.key)"
          >
            <strong>{{ mode.title }}</strong>
            <p>{{ mode.subtitle }}</p>
          </button>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '../components/AppIcon.vue'
import type { SettingsFormState } from '../types/admin'

const props = defineProps<{
  settings: SettingsFormState | null
  section: 'general' | 'theme' | 'templates' | 'ai'
  dirty: boolean
  saveFeedback: string
  search: string
}>()

const emit = defineEmits<{
  save: []
  reset: []
  'open-section': [section: 'general' | 'theme' | 'templates' | 'ai']
}>()

const sectionItems = [
  { key: 'general', label: '通用设置' },
  { key: 'theme', label: '主题设置' },
  { key: 'templates', label: '训练模板' },
  { key: 'ai', label: 'AI 配置' },
] as const

const normalizedSearch = computed(() => props.search.trim().toLowerCase())

const filteredTemplates = computed(() => {
  const items = props.settings?.templates.items ?? []
  if (!normalizedSearch.value) {
    return items
  }
  return items.filter((item) => [item.name, item.levelLabel, item.description].join(' ').toLowerCase().includes(normalizedSearch.value))
})

const filteredModes = computed(() => {
  const items = props.settings?.ai.modes ?? []
  if (!normalizedSearch.value) {
    return items
  }
  return items.filter((item) => [item.title, item.subtitle].join(' ').toLowerCase().includes(normalizedSearch.value))
})

const activateTemplate = (templateId: string) => {
  props.settings?.templates.items.forEach((item) => {
    item.active = item.id === templateId
  })
}

const activateMode = (modeKey: string) => {
  props.settings?.ai.modes.forEach((item) => {
    item.active = item.key === modeKey
  })
}
</script>
