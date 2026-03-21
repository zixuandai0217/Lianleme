// apply shared design tokens from packages to runtime css variables; keep admin-console visually aligned with repo tokens; verify with vite build
import tokens from '../../../../packages/design-tokens/tokens.json'

const toKebab = (value: string) => value.replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`)

export const applyDesignTokens = () => {
  const root = document.documentElement

  Object.entries(tokens.color).forEach(([key, value]) => {
    root.style.setProperty(`--${toKebab(key)}`, value)
  })

  Object.entries(tokens.radius).forEach(([key, value]) => {
    root.style.setProperty(`--radius-${toKebab(key)}`, value)
  })

  Object.entries(tokens.shadow).forEach(([key, value]) => {
    root.style.setProperty(`--shadow-${toKebab(key)}`, value)
  })

  root.style.setProperty('--font-display', tokens.font.display)
  root.style.setProperty('--font-body', tokens.font.body)
}
