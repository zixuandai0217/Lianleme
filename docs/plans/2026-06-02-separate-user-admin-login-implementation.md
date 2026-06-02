# Separate User/Admin Login Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the user-facing product and admin system into separate login surfaces with role-aware redirects and distinct development login identities.

**Architecture:** Keep a single auth context and JWT model, but add separate development login endpoints for normal users and admins. On the frontend, add dedicated `/login` and `/admin/login` pages plus route guards that redirect users and admins into their own surfaces.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, React, React Router, TypeScript, Vite

---

### Task 1: Add backend regression tests for split dev logins

**Files:**
- Modify: `backend/tests/test_auth_guards.py`
- Test: `backend/tests/test_auth_guards.py`

**Step 1: Write the failing tests**

Add tests that prove:
- `POST /api/user/dev-login` creates or returns a non-admin user
- `POST /api/user/dev-login/admin` creates or returns an admin user

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_guards.py -v`
Expected: FAIL because the admin login route does not exist and the default dev login still returns an admin user.

**Step 3: Write minimal implementation**

Update user service and user API routes to expose separate dev login flows and identity defaults.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_auth_guards.py -v`
Expected: PASS for the new split-login behavior.

### Task 2: Split frontend login surfaces

**Files:**
- Modify: `web/src/api/index.ts`
- Modify: `web/src/hooks/use-auth.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/pages/login/index.tsx`
- Create: `web/src/pages/admin-login/index.tsx`
- Modify: `web/src/components/admin-layout.tsx`

**Step 1: Wire API methods**

Add a dedicated admin development login API helper while preserving the existing user development login path.

**Step 2: Update auth context**

Expose separate login actions for user/admin entry points while keeping current-user hydration via `/api/user/me`.

**Step 3: Split routes and guards**

Add:
- `UserGate`: redirects admins away from the user app
- `AdminGate`: redirects non-admins away from admin routes
- `LoginRedirect`: sends authenticated users to `/` or `/admin`
- `AdminLoginRedirect`: sends authenticated users to `/admin` or `/`

**Step 4: Add dedicated admin login page**

Build a distinct admin login screen with its own entry copy and CTA. Keep the user login page focused on the product experience and link to the admin login page with a lightweight secondary affordance.

**Step 5: Verify the frontend compiles**

Run:
- `cd web && npm run typecheck`
- `cd web && npm run build`

Expected: both commands succeed.

### Task 3: Verify the split in the running app

**Files:**
- No code changes required

**Step 1: Verify browser behavior**

Check:
- `/login` shows the user login page
- `/admin/login` shows the admin login page
- admin login lands on `/admin`
- user login lands on `/`
- users cannot stay on `/admin`
- admins cannot stay inside the user route tree

**Step 2: Report residual risk**

Call out that this is still one auth system with two entry surfaces; true production-grade separation would later add dedicated admin auth policy and audited admin user provisioning.
