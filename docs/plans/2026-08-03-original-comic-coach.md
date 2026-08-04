# Original Comic Coach Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship an original comic fitness coach with visually integrated A-H/X speech animation while preserving the existing voice and conversation behavior.

**Architecture:** Keep the shared React/CSS `DigitalCoach` renderer and replace only its versioned visual asset bundle. Generate and approve a canonical character first, derive aligned facial layers from that identity, then switch asset URLs behind a manifest with the current character as a load fallback.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Vitest, Pillow asset tooling, WebP/PNG, Playwright browser QA.

---

### Task 1: Generate And Review The Character Concept

**Files:**
- Create: `web/public/coach/concepts/coach-comic-v1.png`
- Create: `docs/coach-comic-v2-assets.md`

**Step 1: Generate the non-destructive concept**

Use the image generation workflow with the approved stylized-concept prompt. Request a square waist-up three-quarter pose, an original face, restrained athletic proportions, a subtle closed-mouth smile, black/orange training clothing, no text, and no watermark.

**Step 2: Inspect the output**

Check identity originality, face quality, hand anatomy, crop, clothing details, and absence of exposed-teeth grin or copied tattoo. Reject the image if any of these fail.

**Step 3: Save the selected preview**

Copy the chosen output to `web/public/coach/concepts/coach-comic-v1.png` without modifying runtime references.

**Step 4: Record provenance**

Add the final prompt, generation method, date, and review notes to `docs/coach-comic-v2-assets.md`.

**Step 5: Review checkpoint**

Show the concept to the user and do not create production layers until the character identity is approved.

### Task 2: Add Asset Contract Tests

**Files:**
- Modify: `web/scripts/validate-coach-assets.py`
- Create: `web/src/coach-v2-assets.test.ts`

**Step 1: Write failing contract tests**

Require one canonical square body, A-H/X mouth layers, one blink layer, one thinking-brow layer, equal dimensions, alpha channels, transparent corners, valid non-empty alpha bounds, and a maximum total runtime bundle size.

**Step 2: Run the focused tests and confirm failure**

Run: `cd web && npm run test:unit -- src/coach-v2-assets.test.ts`

Expected: FAIL because the v2 manifest and layers do not exist.

**Step 3: Extend the validator contract**

Add a high-level validation function that loads the v2 manifest, verifies declared files, and checks image dimensions and alpha properties.

**Step 4: Run the validator and keep the expected failure**

Run: `cd web && npm run validate:coach-assets`

Expected: FAIL with a precise missing-v2-asset message.

### Task 3: Produce The Canonical Runtime Bundle

**Files:**
- Create: `web/public/coach/v2/coach-base.webp`
- Create: `web/public/coach/v2/face/mouth-A.webp`
- Create: `web/public/coach/v2/face/mouth-B.webp`
- Create: `web/public/coach/v2/face/mouth-C.webp`
- Create: `web/public/coach/v2/face/mouth-D.webp`
- Create: `web/public/coach/v2/face/mouth-E.webp`
- Create: `web/public/coach/v2/face/mouth-F.webp`
- Create: `web/public/coach/v2/face/mouth-G.webp`
- Create: `web/public/coach/v2/face/mouth-H.webp`
- Create: `web/public/coach/v2/face/mouth-X.webp`
- Create: `web/public/coach/v2/face/eyes-blink.webp`
- Create: `web/public/coach/v2/face/brow-thinking.webp`
- Create: `web/public/coach/v2/manifest.json`

**Step 1: Generate the canonical master**

Use the approved concept as an identity reference. Render on a flat removable chroma-key background with a stable square canvas and the neutral X mouth.

**Step 2: Generate the facial atlas**

Create A-H/X, closed eyelids, and thinking brows with the same perspective, lighting, and line weight. Do not include full-face skin tiles.

**Step 3: Remove chroma key and align layers**

Use the imagegen chroma-key helper and the project preparation script. Preserve a single shared canvas origin for every output.

**Step 4: Write the manifest**

Record canvas dimensions, file paths, alpha bounds, and byte sizes.

**Step 5: Run contract verification**

Run: `cd web && npm run validate:coach-assets && npm run test:unit -- src/coach-v2-assets.test.ts`

Expected: PASS.

### Task 4: Switch The Shared Renderer With Fallback

**Files:**
- Modify: `web/src/components/digital-coach.tsx`
- Modify: `web/src/digital-coach.behavior.test.tsx`
- Modify: `web/src/index.css`

**Step 1: Write failing renderer tests**

Assert that stage and portrait load v2 assets, speaking uses the requested A-H/X layer, facial failure retains the base face, and base failure exposes the previous coach fallback.

**Step 2: Run tests and confirm failure**

Run: `cd web && npm run test:unit -- src/digital-coach.behavior.test.tsx`

Expected: FAIL because the renderer still points to `/coach/rock-coach.webp`.

**Step 3: Implement the asset switch**

Move URLs into a typed v2 asset map, retain the current body as an image-load fallback, and keep existing viseme, blink, and reduced-motion state logic.

**Step 4: Refine restrained motion**

Keep stage breathing and speaking lift below a few pixels. Ensure the portrait has only breathing and no facial timers.

**Step 5: Run focused tests**

Run: `cd web && npm run test:unit -- src/digital-coach.behavior.test.tsx src/digital-coach.test.ts`

Expected: PASS.

### Task 5: Full Verification And Visual QA

**Files:**
- Modify only if a verified defect is found in `web/src/components/digital-coach.tsx` or `web/src/index.css`.

**Step 1: Run frontend verification**

Run: `cd web && npm run test:unit -- --run && npm run typecheck && npm run lint && npm run build`

Expected: all commands exit successfully.

**Step 2: Run asset verification**

Run: `cd web && npm run validate:coach-assets`

Expected: all v2 dimensions, alpha checks, and bundle limits pass.

**Step 3: Inspect the stage view**

Use browser screenshots for `/coach` at desktop and mobile sizes. Verify neutral, thinking, speaking, and error framing, with no seams or overflow.

**Step 4: Inspect the portrait view**

Use browser screenshots for `/` at desktop and mobile sizes. Verify the shared identity and intentional crop.

**Step 5: Check runtime health**

Confirm there are no console errors, failed coach assets, or non-transparent rectangles during mouth changes. Run `git diff --check` before reporting completion.
