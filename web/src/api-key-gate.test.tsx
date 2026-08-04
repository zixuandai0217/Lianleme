// @vitest-environment jsdom
/* Exercise BYOK route access with a real in-memory router and mocked auth state. */
import { act, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Outlet, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { UserResponse } from "@/api/types"
import ApiKeyGate from "@/components/api-key-gate"

const authState = vi.hoisted(() => ({
  user: null as UserResponse | null,
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ user: authState.user }),
}))

let container: HTMLDivElement
let root: Root | null

function LocationResult({ label }: { label: string }) {
  /** Expose the committed route and query for browser-navigation assertions. */
  const location = useLocation()
  return (
    <output data-route={label} data-path={location.pathname} data-search={location.search}>
      {label}
    </output>
  )
}

function ProtectedLayout({ children }: { children?: ReactNode }) {
  /** Apply the production BYOK gate while allowing nested route content in tests. */
  return <ApiKeyGate>{children || <Outlet />}</ApiKeyGate>
}

async function renderRoutes(initialPath: string): Promise<void> {
  /** Mount the representative user routes from the application shell. */
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/profile" element={<LocationResult label="profile" />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/coach" element={<LocationResult label="coach" />} />
            <Route path="/analysis" element={<LocationResult label="analysis" />} />
            <Route path="/plan" element={<LocationResult label="plan" />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
  })
}

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  authState.user = null
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
  vi.restoreAllMocks()
})

describe("ApiKeyGate route behavior", () => {
  it.each(["/coach", "/analysis", "/plan"])(
    "redirects a keyless user from %s to setup and preserves the destination",
    async (protectedPath) => {
      await renderRoutes(protectedPath)

      const result = container.querySelector<HTMLOutputElement>('[data-route="profile"]')
      const query = new URLSearchParams(result?.dataset.search)
      expect(result?.dataset.path).toBe("/profile")
      expect(query.get("setup")).toBe("api-key")
      expect(query.get("from")).toBe(protectedPath)
    },
  )

  it("renders the protected page for a user with their own key", async () => {
    authState.user = {
      id: 7,
      openid: "configured-user",
      api_key_status: { has_key: true, provider: "qwen", masked_key: "sk-...****1234" },
    }

    await renderRoutes("/coach")

    expect(container.querySelector('[data-route="coach"]')).not.toBeNull()
    expect(container.querySelector('[data-route="profile"]')).toBeNull()
  })

  it("keeps the profile setup route reachable without a key", async () => {
    await renderRoutes("/profile?setup=api-key")

    const result = container.querySelector<HTMLOutputElement>('[data-route="profile"]')
    expect(result?.dataset.path).toBe("/profile")
    expect(new URLSearchParams(result?.dataset.search).get("setup")).toBe("api-key")
  })
})
