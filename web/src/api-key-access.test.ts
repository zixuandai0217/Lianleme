/* Verify the required BYOK onboarding, route gate, and profile copy contracts. */
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

// Read project source for cross-component product policy assertions.
const source = (relativePath: string) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8")

const app = source("./App.tsx")
const profile = source("./pages/profile/index.tsx")
const client = source("./api/client.ts")

describe("mandatory user API key access", () => {
  it("guards every AI generation page and redirects keyless logins to setup", () => {
    expect(app).toContain('import ApiKeyGate from "@/components/api-key-gate"')
    expect(app.match(/<ApiKeyGate>/g)).toHaveLength(3)
    expect(app).toContain('user?.api_key_status?.has_key ? "/" : "/profile?setup=api-key"')
  })

  it("presents BYOK as required and links to both provider consoles", () => {
    expect(profile).toContain("AI 功能尚未启用")
    expect(profile).toContain("使用 AI 功能前，需要配置你自己申请的 API Key")
    expect(profile).toContain("本平台不会生成、发放或共享 API Key")
    expect(profile).toContain("https://bailian.console.aliyun.com/")
    expect(profile).toContain("https://platform.openai.com/api-keys")
    expect(profile).toContain("加密保存")
    expect(profile).not.toContain("留空则使用系统默认 Key")
  })

  it("extracts readable messages from structured API errors", () => {
    expect(client).toContain('typeof detail === "string"')
    expect(client).toContain("detail?.message")
  })
})
