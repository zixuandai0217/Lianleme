# Coach Mouth Axis Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align every directional talking mouth with the original coach face perspective so speech no longer appears crooked.

**Architecture:** Keep the React renderer and shared 1254 x 1254 coordinate system unchanged. Measure the dark mouth axis directly from each rendered WebP, use the neutral X mouth as the identity reference, and correct the single rotation transform in the deterministic asset generator.

**Tech Stack:** Python 3, Pillow, OpenCV, NumPy, Vitest, React, Vite.

---

### Task 1: Lock The Perspective Contract

**Files:**
- Modify: `web/scripts/validate-coach-assets.py`
- Test: `web/public/coach/v2/face/mouth-A.webp` through `mouth-H.webp`

**Step 1:** Add a high-level helper that estimates the visual axis of dark mouth pixels inside the fixed facial crop.

**Step 2:** Require directional visemes A, B, C, D, G, and H to stay within five degrees of the neutral X mouth axis.

**Step 3:** Run `cd web && npm run validate:coach-assets` and confirm it fails because current directional mouths angle downward while X angles upward.

### Task 2: Correct The Generator

**Files:**
- Modify: `web/scripts/generate_coach_v2_assets.py`
- Regenerate: `web/public/coach/v2/face/mouth-*.webp`
- Regenerate: `web/public/coach/v2/manifest.json`

**Step 1:** Replace the incorrect clockwise mouth rotation with the measured counter-clockwise face angle.

**Step 2:** Run `cd web && python3 scripts/generate_coach_v2_assets.py`.

**Step 3:** Run `cd web && npm run validate:coach-assets` and confirm every directional viseme follows the neutral mouth axis.

### Task 3: Visual And Regression Verification

**Files:**
- Verify: `web/src/coach-v2-assets.test.ts`
- Verify: `web/src/digital-coach.behavior.test.tsx`

**Step 1:** Render an enlarged A-H/X face contact sheet and inspect lip direction, centering, skin seams, and jaw placement.

**Step 2:** Replay real coach audio in `/coach`, capture at least three non-X visemes, and inspect desktop and mobile screenshots.

**Step 3:** Run `npm run test:unit -- --run`, `npm run typecheck`, `npm run lint`, `npm run build`, `npm run validate:coach-assets`, Python compilation, and `git diff --check`.
