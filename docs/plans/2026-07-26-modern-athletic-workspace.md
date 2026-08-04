# Modern Athletic Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the authenticated frontend as a polished modern athletic workspace with a lighter shell, one coach-led recommendation, and denser operational content.

**Architecture:** Keep routes, API calls, Rive runtime behavior, and check-in state unchanged. Replace the shared shell and design tokens, then recompose the dashboard from existing state into a recommendation-first layout; use source-level Vitest contracts and real-browser responsive checks to protect the intended hierarchy.

**Tech Stack:** React 19, TypeScript 6, Vite 8, Tailwind CSS 4, shadcn/Base UI, Lucide, Rive React Canvas, Vitest, Playwright.

---

### Task 1: Lock the approved visual contract

**Files:**
- Create: `web/src/athletic-workspace.test.ts`
- Modify: `web/src/design-system.test.ts`
- Test: `web/src/athletic-workspace.test.ts`

**Steps:**
1. Add assertions for Geist body typography, graphite/forest/coral tokens, desktop top navigation, mobile bottom navigation, a single recommended command, and compact coach sizing.
2. Update obsolete editorial/side-rail expectations in the existing design contract.
3. Run `npm run test:unit -- src/athletic-workspace.test.ts src/design-system.test.ts --run` and require a feature-missing failure against the current UI.

### Task 2: Rebuild the shared application shell

**Files:**
- Modify: `web/src/components/layout.tsx`
- Modify: `web/src/index.css`

**Steps:**
1. Replace the desktop side rail and mobile Sheet with a sticky desktop top navigation and fixed mobile bottom navigation.
2. Preserve the three primary routes and logout behavior.
3. Add stable main-content top/bottom spacing so neither navigation surface overlaps any page.
4. Run the focused workspace tests and typecheck.

### Task 3: Recompose the coach dashboard

**Files:**
- Modify: `web/src/pages/dashboard/index.tsx`
- Modify: `web/src/components/digital-coach.tsx`

**Steps:**
1. Resolve the recommended action from the existing coach state and separate the remaining three quick actions.
2. Build a compact coach status band with one primary command, a smaller Rive portrait, and concise state copy.
3. Compress metric, workout, and recent-activity spacing while retaining every API call, empty state, and check-in interaction.
4. Keep Rive local-WASM, timeout, error-fallback, and reduced-motion behavior unchanged.
5. Run focused and full unit tests.

### Task 4: Refine shared surfaces

**Files:**
- Modify: `web/src/index.css`
- Modify: `web/src/components/ui/card.tsx`
- Modify: `web/src/components/ui/button.tsx`

**Steps:**
1. Move body copy to Geist and apply the approved graphite/forest/coral palette.
2. Tighten page rhythm, card depth, button height, and focus/hover feedback without layout-shifting transforms.
3. Scan the remaining user pages for contrast, overflow, and inherited typography regressions.
4. Run typecheck, lint, all unit tests, production build, and `git diff --check`.

### Task 5: Review, browser-test, and deploy

**Files:**
- Verify: `web/src/**`
- Deploy: `web/dist/**` to `/var/www/lianleme/`

**Steps:**
1. Request an independent review focused on navigation, state preservation, and mobile containment; fix every Critical or Important issue.
2. Test at 375px, 768px, 1024px, and 1440px with canvas pixel checks, route clicks, reduced motion, focus visibility, and overflow detection.
3. Deploy only the verified `dist` output while preserving `.well-known/`.
4. Compare local and remote hashes, then verify production HTTPS, services, the three primary destinations, and contextual detail routes.
