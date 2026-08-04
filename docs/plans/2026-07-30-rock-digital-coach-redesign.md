# Rock Digital Coach Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the awkward native-geometry coach with a polished, playful 2.5D cartoon action-star coach while preserving live AI, voice, and workout state.

**Architecture:** A generated transparent character asset becomes the visual anchor. A lightweight React component owns viewport parallax, analyser-driven speaking energy, state styling, reduced motion, and accessible fallback behavior; the coach page keeps all conversation and data responsibilities.

**Tech Stack:** React 19, TypeScript, CSS/Tailwind, generated PNG/WebP assets, Vitest, browser visual regression.

---

### Task 1: Lock the new character contract

**Files:**
- Modify: `web/src/three-digital-coach.test.ts`

**Steps:**
1. Replace native Three.js assertions with a generated-character asset contract.
2. Require live state, pointer parallax, analyser energy, reduced-motion support, and cleanup.
3. Run the focused test and confirm it fails against the old geometry renderer.

### Task 2: Generate the character asset

**Files:**
- Create: `web/public/coach/rock-coach.webp`

**Steps:**
1. Generate a front-facing cartoon Dwayne Johnson-inspired fitness coach on a flat chroma-key background.
2. Remove the chroma key locally, convert the transparent result to an optimized WebP, and validate alpha coverage, clean edges, and readable silhouette.
3. Keep only the final optimized asset inside the public project directory.

### Task 3: Build the 2.5D live coach

**Files:**
- Replace: `web/src/components/three-digital-coach.tsx`
- Modify: `web/src/pages/coach/index.tsx`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

**Steps:**
1. Replace WebGL geometry with the generated portrait, solid graphic layers, and responsive stage composition.
2. Add pointer parallax, idle breathing, listening/thinking/speaking/error state treatments, and analyser-driven speech energy.
3. Preserve the existing component API and accessible role/label contract.
4. Rename 3D-specific visible copy to live-character language and remove unused Three.js dependencies.

### Task 4: Verify and visually refine

**Files:**
- Modify only files already in scope if verification exposes a defect.

**Steps:**
1. Run focused and full unit tests, TypeScript, ESLint, and production build.
2. Inspect the coach at desktop and mobile viewports with browser screenshots.
3. Verify image loading, nonblank character pixels, pointer movement, reduced layout overflow, and browser logs.
4. Iterate once on framing or contrast if the first visual pass is not presentation-ready.
