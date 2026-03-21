// centralize the three mobile tabs and runtime native-tabbar hiding so H5 preview and mini-program stay visually aligned; mobile root navigation only; verify with H5 smoke and mini-program preview
export const mobileTabs = [
  { key: 'workout', label: '练了么', path: '/pages/workout/index' },
  { key: 'diet', label: '吃了么', path: '/pages/diet/index' },
  { key: 'progress', label: '瘦了么', path: '/pages/progress/index' },
]

export const hideNativeTabBar = () => {
  if (typeof uni === 'undefined' || typeof uni.hideTabBar !== 'function') {
    return
  }

  uni.hideTabBar({ animation: false })
}
