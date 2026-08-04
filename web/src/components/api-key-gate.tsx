/* Route guard that keeps provider-backed AI pages behind completed BYOK setup. */
import type { ReactNode } from "react"
import { Navigate, useLocation } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"

/** Redirect keyless users to profile setup while preserving their intended AI page. */
export default function ApiKeyGate({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user?.api_key_status?.has_key) {
    const query = new URLSearchParams({
      setup: "api-key",
      from: location.pathname,
    })
    return <Navigate to={`/profile?${query.toString()}`} replace />
  }

  return <>{children}</>
}
