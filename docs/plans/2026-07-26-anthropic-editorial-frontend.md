# Anthropic Editorial Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rework the user-facing fitness workspace into a cohesive Anthropic-inspired editorial interface without changing its API contracts or core workflows.

**Architecture:** Centralize the visual language in CSS tokens and shared primitives, then compose the existing React pages from a small set of editorial page, metric, workflow, and content patterns. Preserve all existing state and API behavior while improving information hierarchy, responsive navigation, accessibility, and empty/loading states.

**Tech Stack:** React 19, TypeScript 6, Vite 8, Tailwind CSS 4, shadcn/Base UI primitives, Lucide icons, Vitest, Poppins/Lora/Geist variable fonts.

---

### Task 1: Lock the design contract

**Files:**
- Create: `web/src/design-system.test.ts`
- Modify: `web/src/index.css`

**Step 1:** Add a source-level Vitest contract that expects the official Anthropic dark, light, orange, blue, green, and gray colors; Poppins and Lora font imports; a card radius no larger than 8px; and a reduced-motion media query.

**Step 2:** Run `npm run test:unit -- src/design-system.test.ts` and require the assertions to fail against the current green theme.

**Step 3:** Replace the green theme with the confirmed editorial palette and typography, add a restrained page-enter motion, and disable that motion under `prefers-reduced-motion`.

**Step 4:** Run the focused test again and require it to pass.

### Task 2: Refine shared primitives

**Files:**
- Modify: `web/src/components/ui/card.tsx`
- Modify: `web/src/components/ui/button.tsx`
- Modify: `web/src/components/ui/input.tsx`
- Modify: `web/src/components/ui/badge.tsx`
- Modify: `web/src/components/ui/tabs.tsx`

**Step 1:** Reduce decorative rounding, strengthen visible focus states, and add stable hover/active feedback without layout-shifting transforms.

**Step 2:** Keep component APIs unchanged so all existing pages inherit the visual update without behavioral rewrites.

**Step 3:** Run typecheck and the focused design test.

### Task 3: Rebuild the application shell

**Files:**
- Modify: `web/src/components/layout.tsx`

**Step 1:** Build a charcoal desktop rail with a strong product signature, numbered navigation rhythm, visible active state, compact user footer, and a warm-light main canvas.

**Step 2:** Preserve the mobile Sheet workflow while adding a stable top bar, clear menu label, and content padding that cannot overlap navigation.

**Step 3:** Verify every navigation destination and logout action remains wired to the existing auth flow.

### Task 4: Redesign the core training workflows

**Files:**
- Modify: `web/src/pages/dashboard/index.tsx`
- Modify: `web/src/pages/plan/index.tsx`
- Modify: `web/src/pages/coach/index.tsx`

**Step 1:** Turn the dashboard into a compact training overview with an editorial header, a three-step analysis/plan/coach workflow, structured metrics, and a clear today-training action area.

**Step 2:** Turn the plan page into a week-oriented workspace with a useful empty state, explicit prerequisites, stable tabs, and scannable exercise rows.

**Step 3:** Restyle the coach as a focused conversation workspace while retaining the existing streaming parser, readable provider-error state, history loading, keyboard behavior, and suggested-action interactions.

**Step 4:** Run typecheck, unit tests, and lint.

### Task 5: Align the remaining user pages

**Files:**
- Modify: `web/src/pages/analysis/index.tsx`
- Modify: `web/src/pages/weight/index.tsx`
- Modify: `web/src/pages/profile/index.tsx`

**Step 1:** Apply the shared page header, width, section rhythm, and form hierarchy without changing analysis, weight, profile, or API-key behavior.

**Step 2:** Check empty, loading, error, populated, and narrow-screen states for coherent containment and readable text.

### Task 6: Verify, review, and deploy

**Files:**
- Verify: `web/src/**`
- Deploy: `web/dist/**` to `/var/www/lianleme/`

**Step 1:** Run `npm run typecheck`, `npm run lint`, `npm run test:unit -- --run`, `npm run build`, and `git diff --check`.

**Step 2:** Review the full diff for regressions, especially existing uncommitted dashboard/coach behavior and API calls.

**Step 3:** Start the local Vite server and visually test at 375px, 768px, 1024px, and 1440px. Require no horizontal overflow, no overlaps, visible focus states, and zero console errors.

**Step 4:** Deploy only the verified `dist` output, compare local and remote hashes, then verify production HTTPS, core routes, and browser rendering.
