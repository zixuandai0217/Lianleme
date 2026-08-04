# Mandatory User API Key Design

## Product Rule

Every non-admin user must configure a provider API key obtained from Qwen or OpenAI before using AI generation. The application never creates a fake provider key, exposes the server key, or falls back to the server key for an authenticated user's request.

## Architecture

The existing `users.llm_provider` and encrypted `users.llm_api_key` columns remain the source of truth, so no schema migration is required. `ApiKeyService` validates provider names, encrypts new keys with a versioned AES-256-GCM envelope, retains read compatibility for legacy CBC rows, returns only a mask, and exposes decrypted values only to backend AI factories. Non-development startup rejects missing, public, or undersized encryption secrets. A reusable FastAPI dependency rejects AI generation requests with HTTP 428 and a stable `api_key_required` error when the authenticated user has no usable key.

`LLMClientFactory` uses the authenticated user's key whenever a `user_id` is supplied. System keys remain available only to explicit internal calls that do not carry a user identity. Chat history, previous plans, analysis history, weight data, and profile management remain readable without a provider key.

The Qwen coach voice runtime accepts an explicit user key. Qwen users can use the current custom voice and lip sync with their own key. OpenAI users retain chat, vision, and planning, but the Qwen-only custom voice reports unavailable instead of consuming the system key.

## Frontend Flow

After registration or login, a user without a configured key lands on `/profile?setup=api-key`. The `/coach`, `/analysis`, and `/plan` routes share an API-key gate; dashboard, weight history, and profile remain accessible. The profile card shows a required setup state, provider-specific application links, encrypted-storage messaging, save errors, and configured status. Deleting a key disables future AI generation immediately.

## Error Handling And Tests

Backend tests cover provider validation, encrypted storage, no system fallback, HTTP 428 gates, Qwen TTS key injection, and OpenAI voice unavailability. Frontend tests cover route policy, post-login redirect policy, required/configured profile states, and API error extraction. Full backend and frontend suites, typecheck, lint, production build, and browser checks complete the acceptance pass.
