# Analysis Closed-Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn body analysis from a standalone result page into a guided flow that carries the user from upload to analysis to plan generation to training entry.

**Architecture:** Keep the existing backend analysis and plan-generation APIs. Add a small frontend flow-state helper with unit tests, then update the analysis page to show explicit journey stages, inline next-step actions, and direct handoff into training-plan and coach surfaces.

**Tech Stack:** React, TypeScript, Vite, Vitest, existing API client

---

### Task 1: Add testable flow-state helper

**Files:**
- Create: `web/src/pages/analysis/flow.ts`
- Create: `web/src/pages/analysis/flow.test.ts`
- Modify: `web/package.json`
- Modify: `web/vite.config.ts`

**Step 1: Write the failing tests**

Cover:
- empty state shows upload as active and later steps pending
- analysis-complete state prompts plan generation
- plan-ready state unlocks training entry CTAs

**Step 2: Run test to verify it fails**

Run: `cd web && npm run test:unit -- --run web/src/pages/analysis/flow.test.ts`
Expected: FAIL because the helper and test script do not exist yet.

**Step 3: Write minimal implementation**

Add a pure helper that derives stage statuses and CTA copy from a few booleans.

**Step 4: Run test to verify it passes**

Run: `cd web && npm run test:unit -- --run web/src/pages/analysis/flow.test.ts`
Expected: PASS

### Task 2: Implement the closed-loop analysis page

**Files:**
- Modify: `web/src/pages/analysis/index.tsx`
- Modify: `web/src/api/index.ts`

**Step 1: Add journey states to the page**

Track:
- image selected
- analysis running / complete
- plan generating / available

**Step 2: Add inline plan generation**

Use the existing `generatePlan()` API directly from the analysis page so the user can continue without navigating away.

**Step 3: Add next-step CTA surface**

Show a dedicated card after analysis results with:
- primary action to generate or refresh a plan
- follow-up action to view the plan
- training entry to AI coach once a plan exists

**Step 4: Improve stage communication**

Replace the current generic progress feeling with explicit step labels so the user understands where they are in the funnel.

### Task 3: Verify end-to-end behavior

**Files:**
- No code changes required

**Step 1: Run frontend verification**

Run:
- `cd web && npm run test:unit -- --run web/src/pages/analysis/flow.test.ts`
- `cd web && npm run typecheck`
- `cd web && npm run build`

**Step 2: Verify in browser**

Check that:
- the analysis page renders the staged journey
- the user sees clear next actions after analysis
- plan generation can be initiated from the analysis page
- the page offers direct handoff to plan/coach after a plan exists
