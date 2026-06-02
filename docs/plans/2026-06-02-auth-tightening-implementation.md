# Auth Tightening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce token-based authentication and ownership/admin authorization across backend APIs so users can no longer read or mutate other users' resources by guessing `user_id`.

**Architecture:** Add a centralized security dependency that decodes JWT bearer tokens and resolves the current user from the database. Thread that dependency through user-owned routes and admin routes, then add focused backend tests proving owner-only access, admin-only access, and rejection of mismatched `user_id` request bodies.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, python-jose JWT, pytest, httpx/ASGI transport

---

### Task 1: Add centralized auth dependency

**Files:**
- Create: `backend/app/core/security.py`
- Modify: `backend/app/core/__init__.py` if needed
- Test: `backend/tests/test_auth_guards.py`

**Step 1: Write the failing test**

Add a test that calls a protected endpoint without `Authorization` and expects `401`.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest backend/tests/test_auth_guards.py -k missing_token -v`
Expected: FAIL because the endpoint does not currently enforce auth.

**Step 3: Write minimal implementation**

Create a reusable dependency that:
- reads `Authorization: Bearer <token>`
- decodes JWT with `SECRET_KEY`
- loads the user by `sub`
- raises `401` for missing/invalid tokens

**Step 4: Run test to verify it passes**

Run the same pytest command and expect PASS.

### Task 2: Enforce owner checks on user-owned routes

**Files:**
- Modify: `backend/app/api/user.py`
- Modify: `backend/app/api/vision.py`
- Modify: `backend/app/api/plan.py`
- Modify: `backend/app/api/coach.py`
- Modify: `backend/app/api/workout.py`
- Modify: `backend/app/api/weight.py`
- Test: `backend/tests/test_auth_guards.py`

**Step 1: Write the failing tests**

Add tests that:
- use user A token against `/api/user/{user_b_id}` and expect `403`
- post body `user_id=user_b_id` with user A token and expect `403`
- access own resources with matching token and expect success

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest backend/tests/test_auth_guards.py -k owner -v`
Expected: FAIL because current routes trust passed `user_id`.

**Step 3: Write minimal implementation**

For each protected route:
- inject current user dependency
- compare path/body/query `user_id` with current user id
- raise `403` on mismatch

**Step 4: Run tests to verify they pass**

Run the same owner-focused pytest command and expect PASS.

### Task 3: Enforce admin-only access on admin routes

**Files:**
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/core/security.py`
- Test: `backend/tests/test_auth_guards.py`

**Step 1: Write the failing tests**

Add tests that:
- call `/api/admin/stats` with normal user token and expect `403`
- call `/api/admin/stats` with admin user token and expect `200`

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest backend/tests/test_auth_guards.py -k admin -v`
Expected: FAIL because admin auth is currently only query-param based.

**Step 3: Write minimal implementation**

Add an admin dependency layered on top of current user resolution and use it in admin routes instead of trusting `user_id` query params alone.

**Step 4: Run tests to verify they pass**

Run the same admin-focused pytest command and expect PASS.

### Task 4: Align frontend auth bootstrap with server-owned identity

**Files:**
- Modify: `web/src/hooks/use-auth.ts`
- Modify: `web/src/api/index.ts`
- Modify: `web/src/api/types.ts` if needed
- Test: verification via app smoke flow

**Step 1: Write the failing test or verification target**

Since the frontend currently has no automated suite, define a manual verification target:
- login
- refresh page
- visit `/profile`
- ensure user data still loads through the authenticated request path

**Step 2: Verify current assumptions**

Run the app and confirm the frontend restores from token-backed user fetch rather than requiring unsafe trust in stale local ids for protected flows.

**Step 3: Write minimal implementation**

Reduce auth state reliance on locally trusted identity where possible:
- treat token as primary source of session
- keep `userId` only as a cached convenience derived from server-loaded user
- avoid mutating auth state from unverified local values when a token-backed fetch fails

**Step 4: Verify manually**

Open the app, log in, refresh, and confirm `/profile`, `/analysis`, `/weight`, and `/admin` still behave correctly.

### Task 5: Add regression coverage and run full verification

**Files:**
- Create: `backend/tests/conftest.py` if needed
- Create or modify: `backend/tests/test_auth_guards.py`

**Step 1: Run focused backend tests**

Run:
- `cd backend && uv run pytest backend/tests/test_auth_guards.py -v`

Expected:
- all new auth guard tests PASS

**Step 2: Run broader checks**

Run:
- `cd backend && uv run pytest -v`
- `cd web && npm run typecheck`
- `cd web && npm run lint`

Expected:
- backend tests PASS
- frontend typecheck PASS
- lint result recorded; if unrelated pre-existing failures remain, document them explicitly

**Step 3: Manual smoke verification**

Run the app and verify:
- unauthenticated access redirects to `/login`
- authenticated user can access own profile
- authenticated user cannot reach admin unless `is_admin`

**Step 4: Commit**

After verification, stage the touched backend/frontend files and commit with a message like:

`git commit -m "feat: enforce token-based auth guards"`

---

Plan saved for immediate execution in this session. The user already requested implementation, so proceed directly with Task 1 rather than pausing for execution-mode selection.
