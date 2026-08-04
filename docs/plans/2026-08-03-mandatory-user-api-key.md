# Mandatory User API Key Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Require every user to configure a Qwen or OpenAI provider key before any AI generation uses provider services.

**Architecture:** Reuse the existing encrypted per-user key fields, add a backend enforcement dependency and remove authenticated-user fallback from the LLM factory. Add a frontend route gate and turn the profile key card into the required onboarding step. Pass Qwen users' own keys into coach TTS and never silently use the server key for a user request.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, React 19, React Router, TypeScript, Vitest, pytest.

---

### Task 1: Lock The Backend BYOK Policy

**Files:**
- Create: `backend/tests/test_user_api_keys.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/services/user/api_key_service.py`
- Modify: `backend/app/services/ai/llm_factory.py`

1. Write failing tests for supported providers, encrypted storage, missing-key errors, and authenticated-user no-fallback behavior.
2. Run `uv run pytest tests/test_user_api_keys.py -q` and confirm the expected failures.
3. Add a typed missing-key error, strict provider validation, and user-key-only resolution for calls with `user_id`.
4. Re-run the focused tests and confirm they pass.

### Task 2: Enforce The Policy At AI Boundaries

**Files:**
- Modify: `backend/app/core/security.py`
- Modify: `backend/app/api/coach.py`
- Modify: `backend/app/api/vision.py`
- Modify: `backend/app/api/plan.py`
- Test: `backend/tests/test_user_api_keys.py`

1. Write failing route tests expecting HTTP 428 from chat, analysis, and plan generation without a key.
2. Add one reusable authenticated-user API-key dependency with a stable error payload.
3. Apply it only to provider-consuming endpoints, leaving stored data endpoints readable.
4. Re-run focused route tests.

### Task 3: Use The User's Key For Coach Voice

**Files:**
- Modify: `backend/app/services/ai/tts_runtime.py`
- Modify: `backend/app/api/coach.py`
- Test: `backend/tests/test_coach_tts.py`

1. Write failing tests proving Qwen TTS receives the user's decrypted key and OpenAI users do not fall back to the system Qwen key.
2. Parameterize TTS configuration, client construction, synthesis, and cache identity with an explicit key.
3. Resolve the authenticated user's provider/key in coach voice routes and report unavailable for non-Qwen providers.
4. Run the complete coach TTS tests.

### Task 4: Add Registration Onboarding And Route Gates

**Files:**
- Create: `web/src/components/api-key-gate.tsx`
- Create: `web/src/api-key-access.test.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/pages/profile/index.tsx`
- Modify: `web/src/api/client.ts`

1. Write failing tests for protected routes, login redirect, required setup copy, provider links, and structured API errors.
2. Implement the shared route policy and API-key gate.
3. Redirect keyless authenticated users from login to the profile setup state.
4. Replace optional/fallback wording with required BYOK status, application links, safe storage messaging, and inline errors.
5. Run focused Vitest tests.

### Task 5: Verify The Complete Flow

**Files:**
- Modify: `TODO.md`

1. Run the full backend pytest suite.
2. Run frontend unit tests, TypeScript, ESLint, and production build.
3. Run `git diff --check`.
4. Verify `/profile`, keyless redirects from `/coach`, responsive layout, and console output in the browser.
5. Request an independent code review and address Critical or Important findings.
