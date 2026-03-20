<template>
  <view class="camera-page">
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
            <text class="mode-card-title">{{ mode.title }}</text>
            <text class="mode-card-desc">{{ mode.desc }}</text>
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
import { computed, inject, ref } from 'vue'

import { apiPost } from '../../api/client'

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

const scanLabel = computed(() => {
  if (captureState.value === 'done') {
    return 'AI ANALYSIS READY'
  }

  if (captureState.value === 'submitting') {
    return 'AI SCANNING ACTIVE'
  }

  return 'AI CAMERA STANDBY'
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
    const payload = {
      user_id: 'u_demo',
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
</script>

<style scoped lang="scss">
/* build a high-fidelity camera-customize page that matches the workout family while staying demo-friendly without real camera capture; photo-customize page only; verify by opening the page from the workout tab and checking the viewport card, mode selector, and capture CTA render together. */
.camera-page,
.camera-page *,
.camera-page *::before,
.camera-page *::after {
  box-sizing: border-box;
}

.camera-page {
  display: block !important;
  width: 100%;
  min-height: 100vh;
  padding: 28px 16px 20px;
  background:
    radial-gradient(circle at top left, rgba(242, 17, 98, 0.14), transparent 34%),
    radial-gradient(circle at bottom right, rgba(126, 118, 244, 0.08), transparent 22%),
    linear-gradient(180deg, #2a2b35 0%, #313340 18%, #f8f4f1 18%, #f4f6fb 100%);
  font-family: 'MiSans', 'Source Han Sans CN', sans-serif;
}

.phone-shell {
  width: 100%;
  max-width: 390px;
  margin: 0 auto;
  padding: 18px 16px 24px;
  border-radius: 32px;
  background:
    radial-gradient(circle at top, rgba(255, 255, 255, 0.98), rgba(251, 248, 245, 0.98)),
    #ffffff;
  box-shadow:
    0 30px 72px rgba(34, 28, 25, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
}

.page-header,
.power-badge,
.capture-action,
.privacy-note {
  display: flex;
  align-items: center;
}

.page-header {
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
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: linear-gradient(180deg, #ffffff, #f5f6fb);
  box-shadow: 0 14px 28px rgba(34, 40, 58, 0.08);
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
  font-size: 18px;
  font-weight: 800;
  color: #22283a;
}

.header-spacer {
  width: 42px;
  height: 42px;
}

.hero-copy {
  margin-top: 24px;
}

.power-badge {
  gap: 10px;
  color: #f21162;
  font-size: 18px;
  font-weight: 800;
}

.power-icon {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(145deg, #f21162 0%, #ff4f73 100%);
  box-shadow: 0 16px 30px rgba(242, 17, 98, 0.2);
}

.power-icon::before,
.power-icon::after {
  content: '';
  position: absolute;
}

.power-icon::before {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid #ffffff;
}

.power-icon::after {
  width: 4px;
  height: 10px;
  background: #ffffff;
  border-radius: 999px;
  transform: rotate(35deg);
}

.hero-title {
  display: block;
  margin-top: 22px;
  font-size: 34px;
  line-height: 1.1;
  font-weight: 900;
  color: #22283a;
}

.hero-subtitle {
  display: block;
  margin-top: 14px;
  font-size: 16px;
  line-height: 1.65;
  color: #65708b;
}

.camera-stage {
  position: relative;
  overflow: hidden;
  min-height: 542px;
  margin-top: 28px;
  padding: 28px 24px 26px;
  border-radius: 40px;
  background:
    linear-gradient(180deg, rgba(214, 224, 239, 0.96), rgba(229, 236, 247, 0.88)),
    #d6dfec;
  border: 2px dashed rgba(242, 17, 98, 0.28);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.3),
    0 24px 50px rgba(77, 94, 132, 0.14);
}

.camera-glow {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.52);
  filter: blur(4px);
}

.camera-glow-a {
  top: 42px;
  left: 16px;
  width: 36px;
  height: 20px;
}

.camera-glow-b {
  top: 52px;
  right: 30px;
  width: 58px;
  height: 28px;
}

.camera-glow-c {
  top: 126px;
  left: 108px;
  width: 42px;
  height: 24px;
}

.scan-corner {
  position: absolute;
  width: 58px;
  height: 58px;
  border-color: #f21162;
  border-style: solid;
  border-width: 0;
}

.corner-top-left {
  top: 40px;
  left: 38px;
  border-top-width: 6px;
  border-left-width: 6px;
  border-radius: 28px 0 0 0;
}

.corner-top-right {
  top: 40px;
  right: 38px;
  border-top-width: 6px;
  border-right-width: 6px;
  border-radius: 0 28px 0 0;
}

.corner-bottom-left {
  bottom: 38px;
  left: 38px;
  border-bottom-width: 6px;
  border-left-width: 6px;
  border-radius: 0 0 0 28px;
}

.corner-bottom-right {
  bottom: 38px;
  right: 38px;
  border-bottom-width: 6px;
  border-right-width: 6px;
  border-radius: 0 0 28px 0;
}

.camera-core {
  position: relative;
  z-index: 1;
  padding-top: 140px;
  text-align: center;
}

.camera-icon-wrap {
  width: 96px;
  height: 96px;
  margin: 0 auto;
  border-radius: 50%;
  background: linear-gradient(145deg, #f21162 0%, #ff4771 100%);
  box-shadow: 0 24px 42px rgba(242, 17, 98, 0.22);
}

.camera-icon {
  position: relative;
  width: 40px;
  height: 32px;
  border-radius: 8px;
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
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 3px solid #f21162;
}

.camera-title {
  display: block;
  margin-top: 28px;
  font-size: 23px;
  font-weight: 900;
  color: #22283a;
}

.camera-note {
  display: block;
  margin-top: 12px;
  font-size: 16px;
  line-height: 1.55;
  color: #75819a;
}

.scan-pill {
  position: absolute;
  left: 50%;
  bottom: 28px;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 172px;
  padding: 14px 24px;
  border-radius: 999px;
  background: rgba(34, 40, 58, 0.64);
  color: #ffffff;
  font-size: 12px;
  letter-spacing: 1px;
  font-weight: 800;
}

.scan-pill.done {
  background: rgba(34, 40, 58, 0.84);
}

.scan-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f21162;
  box-shadow: 0 0 0 6px rgba(242, 17, 98, 0.14);
}

.scan-pill.submitting .scan-dot {
  animation: pulse-dot 900ms ease infinite;
}

.section-block {
  margin-top: 30px;
}

.section-title {
  display: block;
  font-size: 20px;
  font-weight: 900;
  color: #22283a;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.mode-card {
  position: relative;
  min-height: 158px;
  padding: 20px 18px 18px;
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 251, 254, 0.98));
  border: 2px solid rgba(232, 236, 244, 0.9);
  box-shadow:
    0 20px 36px rgba(34, 40, 58, 0.06),
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
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: linear-gradient(180deg, #f8d6de, #fff5f8);
}

.mode-card-title {
  display: block;
  margin-top: 22px;
  font-size: 18px;
  font-weight: 900;
  color: #22283a;
}

.mode-card-desc {
  display: block;
  margin-top: 10px;
  font-size: 15px;
  line-height: 1.55;
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
  top: 14px;
  left: 23px;
  border-radius: 50%;
  background: #f21162;
}

.icon-posture::after {
  top: 24px;
  left: 26px;
  width: 2px;
  height: 18px;
  background: #f21162;
  box-shadow:
    -8px 6px 0 0 #f21162,
    8px 6px 0 0 #f21162,
    -4px 18px 0 0 #f21162,
    4px 18px 0 0 #f21162;
}

.icon-equipment::before,
.icon-equipment::after {
  top: 25px;
  width: 20px;
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
  right: 14px;
  bottom: 14px;
  width: 68px;
  height: 68px;
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
}

.assistant-face {
  inset: 14px;
  background: linear-gradient(145deg, #f21162 0%, #ff4f73 100%);
}

.assistant-face::before,
.assistant-face::after {
  content: '';
  position: absolute;
}

.assistant-face::before {
  inset: 10px 8px auto;
  height: 10px;
  border-radius: 4px;
  background: #ffffff;
}

.assistant-face::after {
  left: 50%;
  bottom: 8px;
  width: 18px;
  height: 10px;
  border-radius: 8px 8px 10px 10px;
  background: #ffffff;
  transform: translateX(-50%);
}

.status-panel {
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 20px;
  background: rgba(242, 17, 98, 0.08);
  color: #7a4560;
  font-size: 13px;
  line-height: 1.6;
}

.capture-action {
  justify-content: center;
  gap: 12px;
  margin-top: 18px;
  min-height: 66px;
  border-radius: 999px;
  background: linear-gradient(145deg, #f21162 0%, #ff3d6c 100%);
  color: #ffffff;
  font-size: 18px;
  font-weight: 900;
  box-shadow: 0 20px 34px rgba(242, 17, 98, 0.24);
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
  margin-top: 18px;
  color: #a0a9bf;
  font-size: 14px;
}

.privacy-icon {
  position: relative;
  width: 14px;
  height: 16px;
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
    font-size: 30px;
  }

  .camera-stage {
    min-height: 500px;
    padding-left: 18px;
    padding-right: 18px;
  }

  .mode-grid {
    grid-template-columns: 1fr;
  }
}
</style>
