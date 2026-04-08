<template>
  <view class="camera-page">
    <view class="preview-marker">
      <view class="preview-marker-icon"></view>
      <text class="preview-marker-text">拍照定制</text>
    </view>

    <view class="phone-shell">
      <view class="page-header">
        <view class="back-button" @click="goBack">
          <view class="back-icon"></view>
        </view>
        <text class="page-title">拍照定制</text>
        <view class="header-spacer"></view>
      </view>

      <view class="hero-copy">
        <view class="power-badge">
          <view class="power-icon"></view>
          <text>AI POWER</text>
        </view>
        <text class="hero-title">AI 智能拍照定制</text>
        <text class="hero-subtitle">拍摄您的体态或健身器械，让 AI 为您生成专业方案</text>
      </view>

      <view class="camera-stage">
        <!-- rebuild the scan panel as a centered phone-card camera stage; photo customize hero only; verify by comparing the H5 preview against the reference screenshot. -->
        <view class="camera-glow camera-glow-a"></view>
        <view class="camera-glow camera-glow-b"></view>
        <view class="camera-glow camera-glow-c"></view>

        <view class="scan-corner corner-top-left"></view>
        <view class="scan-corner corner-top-right"></view>
        <view class="scan-corner corner-bottom-left"></view>
        <view class="scan-corner corner-bottom-right"></view>

        <view class="camera-core">
          <view class="camera-icon-wrap">
            <view class="camera-icon">
              <view class="camera-icon-lens"></view>
            </view>
          </view>
          <text class="camera-title">{{ stageTitle }}</text>
          <text class="camera-note">{{ stageNote }}</text>
        </view>

        <view class="scan-pill" :class="captureState">
          <view class="scan-dot"></view>
          <text>{{ scanLabel }}</text>
        </view>
      </view>

      <view class="section-block">
        <text class="section-title">选择拍摄模式</text>

        <!-- keep mode switching local so the camera page can demonstrate both analysis intents without requiring new backend schema; photo-customize mode selection only; verify by switching the cards and checking the stage/helper copy updates -->
        <view class="mode-grid">
          <view
            v-for="mode in captureModes"
            :key="mode.key"
            class="mode-card"
            :class="{ active: mode.key === activeMode }"
            @click="setActiveMode(mode.key)"
          >
            <view class="mode-card-icon" :class="mode.iconClass"></view>
            <view class="mode-card-copy">
              <text class="mode-card-title">{{ mode.title }}</text>
              <text class="mode-card-desc">{{ mode.desc }}</text>
            </view>
            <view v-if="mode.assistant" class="mode-assistant">
              <view class="assistant-ring"></view>
              <view class="assistant-face"></view>
            </view>
          </view>
        </view>
      </view>

      <view class="status-panel" v-if="resultMessage || errorMessage">
        <text v-if="resultMessage">{{ resultMessage }}</text>
        <text v-else>{{ errorMessage }}</text>
      </view>

      <view class="capture-action" :class="{ busy: isCapturing }" @click="capturePhoto">
        <view class="capture-action-icon"></view>
        <text>{{ actionLabel }}</text>
      </view>

      <view class="privacy-note">
        <view class="privacy-icon"></view>
        <text>您的照片仅用于 AI 分析，不会被公开分享</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'

import { apiPost } from '../../api/client'
import { loadMobileSession, requireMobileAuth } from '../../lib/authSession'

const previewShell = inject('previewShell', null)
const activeMode = ref('body_analysis')
const captureState = ref('idle')
const resultMessage = ref('')
const errorMessage = ref('')

const captureModes = [
  {
    key: 'body_analysis',
    title: '体态分析',
    desc: '识别体态问题或肌肉关注点',
    iconClass: 'icon-posture',
  },
  {
    key: 'equipment_detection',
    title: '器械识别',
    desc: '根据现有器械生成训练建议',
    iconClass: 'icon-equipment',
    assistant: true,
  },
]

const activeModeMeta = computed(() => {
  return captureModes.find((item) => item.key === activeMode.value) || captureModes[0]
})

const isCapturing = computed(() => {
  return captureState.value === 'submitting'
})

const stageTitle = computed(() => {
  return captureState.value === 'done' ? 'AI 已捕捉本次画面' : '对准目标区域'
})

const stageNote = computed(() => {
  if (captureState.value === 'done') {
    return activeMode.value === 'body_analysis'
      ? '演示任务已提交，接下来会生成体态分析建议'
      : '演示任务已提交，接下来会识别器械并生成方案'
  }

  if (captureState.value === 'submitting') {
    return '保持光线充足，AI 正在为这张画面生成演示任务'
  }

  return activeMode.value === 'body_analysis'
    ? '保持光线充足，拍摄更清晰'
    : '拍准器械主体，AI 更容易识别训练环境'
})

// align the idle scan pill copy with the reference camera badge; photo customize status text only; verify on the H5 preview and smoke test output.
const scanLabel = computed(() => {
  if (captureState.value === 'done') {
    return 'AI RESULT READY'
  }

  if (captureState.value === 'submitting') {
    return 'AI SCANNING ACTIVE'
  }

  return 'AI SCANNING ACTIVE'
})

const actionLabel = computed(() => {
  return captureState.value === 'submitting' ? 'AI 正在处理' : '点击拍照'
})

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
}

const setActiveMode = (modeKey) => {
  if (isCapturing.value) {
    return
  }

  activeMode.value = modeKey
  resultMessage.value = ''
  errorMessage.value = ''
  captureState.value = 'idle'
}

const goBack = () => {
  if (previewShell?.closePreviewPage) {
    previewShell.closePreviewPage()
    return
  }

  if (typeof uni !== 'undefined' && typeof uni.navigateBack === 'function') {
    uni.navigateBack({ delta: 1 })
    return
  }

  showToast('当前预览页无法返回')
}

// Why: keep the camera page demo closer to a real flow by submitting the existing photo-analyze task with a synthetic image URL while preserving a graceful local fallback; Scope: photo-customize capture CTA behavior only; Verify: clicking `点击拍照` updates the scan state and shows either a task result or a local demo message.
const capturePhoto = async () => {
  if (isCapturing.value) {
    return
  }

  captureState.value = 'submitting'
  resultMessage.value = ''
  errorMessage.value = ''

  try {
    const currentSession = loadMobileSession()
    const payload = {
      user_id: currentSession?.userId || 'u_demo',
      image_url: `demo://capture/${activeMode.value}/${Date.now()}`,
      mode: activeMode.value,
    }
    const response = await apiPost('/photo/analyze', payload)
    const status = response?.status || 'queued'
    const summary = response?.result_summary || (status === 'done' ? '本地演示模式：已生成拍照分析结果。' : '演示任务已提交，正在等待 AI 处理。')
    captureState.value = 'done'
    resultMessage.value = `任务 ${response?.task_id || 'demo'} · ${summary}`
    showToast(status === 'done' ? '演示分析已生成' : '演示分析已提交')
  } catch (error) {
    captureState.value = 'done'
    errorMessage.value = `已切换为本地演示反馈：${activeModeMeta.value.title} 结果将在下一步接入`
    showToast(error?.message ? `接口暂不可用：${error.message}` : '已切换到本地演示反馈')
  }
}

// guard the photo customize demo with the same login requirement as other business pages; photo customize entry only; verify by opening the route without login in mini-program preview.
onMounted(() => {
  requireMobileAuth()
})
</script>

<style scoped lang="scss">
/* rebuild the photo customize page as a centered mobile camera card close to the reference; H5 layout and styling only; verify with the photo smoke test and browser screenshot. */
/* keep the camera-page box-sizing reset mp-weixin-safe by targeting supported uni elements instead of scoped universal selectors; photo customize layout only; verify with `npm --workspace apps/mobile-client run build:mp-weixin && node tests/e2e/mobile_mp_style_contract.mjs`. */
.camera-page,
.camera-page view,
.camera-page text,
.camera-page button,
.camera-page input,
.camera-page textarea,
.camera-page image,
.camera-page navigator,
.camera-page scroll-view,
.camera-page swiper,
.camera-page swiper-item {
  box-sizing: border-box;
}

.camera-page {
  display: block !important;
  width: 100%;
  min-height: 100vh;
  padding: 18px 16px 28px;
  background:
    radial-gradient(circle at 18% 8%, rgba(248, 91, 142, 0.16), transparent 24%),
    radial-gradient(circle at 82% 18%, rgba(255, 255, 255, 0.05), transparent 18%),
    radial-gradient(rgba(255, 255, 255, 0.14) 1.05px, transparent 1.05px),
    linear-gradient(180deg, #1f2027 0%, #232532 100%);
  background-size: auto, auto, 14px 14px, auto;
  font-family: 'MiSans', 'Source Han Sans CN', sans-serif;
}

.preview-marker {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 360px;
  margin: 0 auto 12px;
  color: #ffffff;
}

.preview-marker-icon {
  position: relative;
  width: 22px;
  height: 18px;
  border-radius: 5px;
  border: 2px solid rgba(255, 255, 255, 0.88);
}

.preview-marker-icon::before,
.preview-marker-icon::after {
  content: '';
  position: absolute;
}

.preview-marker-icon::before {
  top: 4px;
  left: 4px;
  width: 6px;
  height: 6px;
  border-radius: 2px;
  border: 2px solid rgba(255, 255, 255, 0.88);
}

.preview-marker-icon::after {
  top: 3px;
  right: 3px;
  width: 5px;
  height: 10px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.88);
}

.preview-marker-text {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.hero-copy,
.section-block,
.status-panel {
  display: block !important;
}

.phone-shell {
  display: block !important;
  width: 100%;
  max-width: 360px;
  margin: 0 auto;
  padding: 16px 14px 16px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top, rgba(255, 255, 255, 0.98), rgba(250, 247, 244, 0.98)),
    #ffffff;
  box-shadow:
    0 26px 60px rgba(10, 12, 19, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
}

.page-header,
.power-badge,
.capture-action,
.privacy-note {
  display: flex;
  align-items: center;
}

.page-header {
  display: grid;
  grid-template-columns: 42px 1fr 42px;
  align-items: center;
  justify-content: space-between;
}

.back-button,
.power-icon,
.camera-icon-wrap,
.capture-action-icon,
.mode-card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.back-button {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(180deg, #ffffff, #f6f7fb);
  box-shadow: 0 12px 24px rgba(34, 40, 58, 0.08);
}

.back-icon {
  position: relative;
  width: 18px;
  height: 18px;
}

.back-icon::before,
.back-icon::after {
  content: '';
  position: absolute;
  background: #22283a;
  border-radius: 999px;
}

.back-icon::before {
  top: 8px;
  left: 1px;
  right: 1px;
  height: 2px;
}

.back-icon::after {
  top: 4px;
  left: 2px;
  width: 9px;
  height: 9px;
  border-left: 2px solid #22283a;
  border-bottom: 2px solid #22283a;
  background: transparent;
  transform: rotate(45deg);
}

.page-title {
  text-align: center;
  font-size: 17px;
  font-weight: 800;
  color: #22283a;
}

.header-spacer {
  width: 36px;
  height: 36px;
}

.hero-copy {
  margin-top: 18px;
}

.power-badge {
  gap: 8px;
  color: #f21162;
  font-size: 13px;
  letter-spacing: 0.4px;
  font-weight: 800;
}

.power-icon {
  position: relative;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(145deg, #f21162 0%, #ff4f73 100%);
  box-shadow: 0 10px 20px rgba(242, 17, 98, 0.2);
}

.power-icon::before,
.power-icon::after {
  content: '';
  position: absolute;
}

.power-icon::before {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 2px solid #ffffff;
}

.power-icon::after {
  width: 3px;
  height: 7px;
  background: #ffffff;
  border-radius: 999px;
  transform: rotate(35deg);
}

.hero-title {
  display: block;
  margin-top: 18px;
  font-size: 27px;
  line-height: 1.16;
  font-weight: 900;
  color: #22283a;
}

.hero-subtitle {
  display: block;
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.55;
  color: #65708b;
}

.camera-stage {
  position: relative;
  display: flex !important;
  flex-direction: column;
  overflow: hidden;
  min-height: 404px;
  margin-top: 24px;
  padding: 22px 16px 20px;
  border-radius: 42px;
  background:
    radial-gradient(circle at 50% 18%, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0) 24%),
    linear-gradient(180deg, rgba(220, 229, 241, 0.98), rgba(233, 238, 246, 0.96)),
    #dbe4f0;
  border: 2px dashed rgba(242, 17, 98, 0.26);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.3),
    0 20px 40px rgba(77, 94, 132, 0.14);
}

.camera-stage::before,
.camera-stage::after {
  content: '';
  position: absolute;
  inset: auto;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.42);
  filter: blur(10px);
}

.camera-stage::before {
  top: 86px;
  left: 44px;
  width: 72px;
  height: 30px;
}

.camera-stage::after {
  right: 34px;
  top: 118px;
  width: 48px;
  height: 22px;
}

.camera-glow {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.52);
  filter: blur(4px);
}

.camera-glow-a {
  top: 112px;
  left: 18px;
  width: 22px;
  height: 22px;
}

.camera-glow-b {
  top: 146px;
  left: 66px;
  width: 18px;
  height: 18px;
}

.camera-glow-c {
  top: 160px;
  right: 36px;
  width: 24px;
  height: 24px;
}

.scan-corner {
  position: absolute;
  width: 42px;
  height: 42px;
  border-color: #f21162;
  border-style: solid;
  border-width: 0;
}

.corner-top-left {
  top: 30px;
  left: 30px;
  border-top-width: 4px;
  border-left-width: 4px;
  border-radius: 24px 0 0 0;
}

.corner-top-right {
  top: 30px;
  right: 30px;
  border-top-width: 4px;
  border-right-width: 4px;
  border-radius: 0 24px 0 0;
}

.corner-bottom-left {
  bottom: 28px;
  left: 30px;
  border-bottom-width: 4px;
  border-left-width: 4px;
  border-radius: 0 0 0 24px;
}

.corner-bottom-right {
  bottom: 28px;
  right: 30px;
  border-bottom-width: 4px;
  border-right-width: 4px;
  border-radius: 0 0 24px 0;
}

.camera-core {
  position: relative;
  display: flex !important;
  flex: 1 1 auto;
  width: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 1;
  padding-top: 44px;
  padding-bottom: 18px;
  text-align: center;
}

.camera-icon-wrap {
  width: 76px;
  height: 76px;
  margin: 0 auto;
  border-radius: 50%;
  background: linear-gradient(145deg, #f21162 0%, #ff4771 100%);
  box-shadow: 0 18px 36px rgba(242, 17, 98, 0.24);
}

.camera-icon {
  position: relative;
  width: 34px;
  height: 26px;
  border-radius: 7px;
  background: #ffffff;
}

.camera-icon::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 8px;
  width: 14px;
  height: 8px;
  border-radius: 4px 4px 0 0;
  background: #ffffff;
}

.camera-icon-lens {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 3px solid #f21162;
}

.camera-title {
  display: block;
  margin-top: 22px;
  font-size: 18px;
  font-weight: 900;
  color: #22283a;
}

.camera-note {
  display: block;
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.55;
  color: #75819a;
}

.scan-pill {
  position: relative;
  display: inline-flex;
  align-self: center;
  align-items: center;
  gap: 8px;
  min-width: 160px;
  padding: 12px 18px;
  margin: 0 auto 2px;
  border-radius: 999px;
  background: rgba(54, 56, 66, 0.72);
  color: #ffffff;
  font-size: 11px;
  line-height: 1.2;
  letter-spacing: 1.1px;
  font-weight: 800;
}

.scan-pill.done {
  background: rgba(43, 45, 56, 0.88);
}

.scan-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f21162;
  box-shadow: 0 0 0 5px rgba(242, 17, 98, 0.12);
}

.scan-pill.submitting .scan-dot {
  animation: pulse-dot 900ms ease infinite;
}

.section-block {
  margin-top: 22px;
}

.section-title {
  display: block;
  font-size: 17px;
  font-weight: 900;
  color: #22283a;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 14px;
}

.mode-card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 132px;
  padding: 14px 14px 16px;
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 251, 254, 0.98));
  border: 1.5px solid rgba(232, 236, 244, 0.96);
  box-shadow:
    0 14px 28px rgba(34, 40, 58, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
}

.mode-card.active {
  border-color: rgba(242, 17, 98, 0.92);
  box-shadow:
    0 20px 36px rgba(242, 17, 98, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
}

.mode-card-icon {
  position: relative;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(180deg, #f8d6de, #fff5f8);
}

.mode-card-copy {
  display: block !important;
  margin-top: auto;
}

.mode-card-title {
  display: block;
  margin-top: 18px;
  font-size: 16px;
  font-weight: 900;
  color: #22283a;
}

.mode-card-desc {
  display: block;
  margin-top: 8px;
  padding-right: 8px;
  font-size: 12px;
  line-height: 1.42;
  color: #75819a;
}

.icon-posture::before,
.icon-posture::after,
.icon-equipment::before,
.icon-equipment::after {
  content: '';
  position: absolute;
}

.icon-posture::before {
  width: 8px;
  height: 8px;
  top: 9px;
  left: 18px;
  border-radius: 50%;
  background: #f21162;
}

.icon-posture::after {
  top: 18px;
  left: 21px;
  width: 2px;
  height: 13px;
  background: #f21162;
  box-shadow:
    -7px 4px 0 0 #f21162,
    7px 4px 0 0 #f21162,
    -4px 13px 0 0 #f21162,
    4px 13px 0 0 #f21162;
}

.icon-equipment::before,
.icon-equipment::after {
  top: 20px;
  width: 15px;
  height: 4px;
  border-radius: 999px;
  background: #9097aa;
}

.icon-equipment::before {
  left: 8px;
  transform: rotate(35deg);
}

.icon-equipment::after {
  right: 8px;
  transform: rotate(-35deg);
}

.mode-assistant {
  position: absolute;
  right: 10px;
  bottom: 10px;
  width: 54px;
  height: 54px;
}

.assistant-ring,
.assistant-face {
  position: absolute;
  border-radius: 50%;
}

.assistant-ring {
  inset: 0;
  background: linear-gradient(145deg, rgba(242, 17, 98, 0.16), rgba(255, 194, 212, 0.06));
  border: 3px solid rgba(242, 17, 98, 0.14);
  box-shadow: 0 10px 20px rgba(242, 17, 98, 0.08);
}

.assistant-face {
  inset: 12px;
  background: linear-gradient(145deg, #f21162 0%, #ff4f73 100%);
}

.assistant-face::before,
.assistant-face::after {
  content: '';
  position: absolute;
}

.assistant-face::before {
  inset: 8px 6px auto;
  height: 8px;
  border-radius: 4px;
  background: #ffffff;
}

.assistant-face::after {
  left: 50%;
  bottom: 7px;
  width: 16px;
  height: 8px;
  border-radius: 8px 8px 10px 10px;
  background: #ffffff;
  transform: translateX(-50%);
}

.assistant-ring::after {
  content: '';
  position: absolute;
  top: 8px;
  right: 6px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2ad26b;
  box-shadow: 0 0 0 3px #ffffff;
}

.status-panel {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(242, 17, 98, 0.08);
  color: #7a4560;
  font-size: 12px;
  line-height: 1.6;
}

.capture-action {
  justify-content: center;
  gap: 10px;
  margin-top: 14px;
  min-height: 48px;
  border-radius: 999px;
  background: linear-gradient(145deg, #f21162 0%, #f41461 100%);
  color: #ffffff;
  font-size: 18px;
  font-weight: 900;
  box-shadow: 0 16px 28px rgba(242, 17, 98, 0.24);
}

.capture-action.busy {
  opacity: 0.82;
}

.capture-action-icon {
  position: relative;
  width: 24px;
  height: 24px;
}

.capture-action-icon::before,
.capture-action-icon::after {
  content: '';
  position: absolute;
}

.capture-action-icon::before {
  inset: 2px;
  border-radius: 50%;
  border: 2px solid #ffffff;
}

.capture-action-icon::after {
  top: 6px;
  left: 11px;
  width: 2px;
  height: 10px;
  background: #ffffff;
  box-shadow:
    -5px -3px 0 0 #ffffff,
    5px -3px 0 0 #ffffff,
    0 8px 0 0 #ffffff;
}

.privacy-note {
  justify-content: center;
  gap: 10px;
  margin-top: 12px;
  color: #a0a9bf;
  font-size: 11px;
  line-height: 1.4;
}

.privacy-icon {
  position: relative;
  width: 12px;
  height: 14px;
  border-radius: 4px 4px 6px 6px;
  background: #a0a9bf;
}

.privacy-icon::before {
  content: '';
  position: absolute;
  left: 50%;
  top: -5px;
  width: 8px;
  height: 6px;
  border: 2px solid #a0a9bf;
  border-bottom: 0;
  border-radius: 999px 999px 0 0;
  transform: translateX(-50%);
}

@keyframes pulse-dot {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }

  50% {
    transform: scale(1.24);
    opacity: 0.7;
  }
}

@media (max-width: 375px) {
  .hero-title {
    font-size: 24px;
  }

  .camera-stage {
    min-height: 404px;
    padding-left: 14px;
    padding-right: 14px;
  }

  .mode-grid {
    grid-template-columns: 1fr;
  }
}
</style>
