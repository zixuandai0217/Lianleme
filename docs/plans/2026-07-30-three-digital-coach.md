# 3D Digital Coach Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the static coach demo with a responsive Three.js digital coach that visibly listens, thinks, speaks with analyser-driven mouth motion, and participates in the existing AI conversation flow.

**Architecture:** A self-contained React/Three.js scene owns rendering, animation, resizing, pointer tracking, and WebGL fallback. The coach page owns conversation state and uses the existing history, workout, SSE, TTS, and authentication APIs; a small speech-recognition hook provides optional microphone input where supported.

**Tech Stack:** React 19, TypeScript, Three.js, Tailwind CSS, Vitest, browser Web Speech API, existing FastAPI SSE/TTS endpoints.

---

### Task 1: Lock the product contract with tests

**Files:**
- Create: `web/src/three-digital-coach.test.ts`
- Modify: `web/src/digital-coach.test.ts`
- Modify: `web/src/voice-waveform.test.ts`

**Steps:**
1. Add source-level assertions for the Three.js runtime, accessible canvas fallback, reduced motion, all five coach states, SSE/history/workout data, speech input, and TTS playback.
2. Add behavior assertions for analyser-to-mouth normalization and calm waveform baselines.
3. Run `npm run test:unit -- --run src/three-digital-coach.test.ts src/voice-waveform.test.ts src/digital-coach.test.ts` and confirm the new contract fails because the 3D implementation is absent.

### Task 2: Build the Three.js coach

**Files:**
- Create: `web/src/components/three-digital-coach.tsx`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

**Steps:**
1. Install `three` and `@types/three`.
2. Implement a stylized upper-body coach from native Three.js geometry with orange athletic clothing and charcoal details.
3. Implement idle breathing, blinking, pointer-following head movement, listening/thinking state motion, and analyser-driven mouth opening while speaking.
4. Add transparent responsive rendering, WebGL fallback, resize cleanup, high-DPI limits, reduced-motion handling, and stable canvas dimensions.
5. Run the focused tests and confirm the 3D contract passes.

### Task 3: Restore AI conversation and speech interaction

**Files:**
- Modify: `web/src/pages/coach/index.tsx`
- Modify: `web/src/digital-coach.test.ts`

**Steps:**
1. Load recent chat history and today's workout after authentication.
2. Send messages through `/api/coach/chat/stream`, render tokens as they arrive, and auto-speak the final response through the existing voice hook.
3. Map request, recognition, and playback state to `idle`, `listening`, `thinking`, `speaking`, and `error` scene states.
4. Add explicit microphone, send, replay, and stop controls with labels, tooltips, keyboard support, live announcements, empty/error states, and suggested prompts.
5. Keep the 3D scene full-bleed and unframed, with the transcript as a separate work surface on desktop and a responsive stacked layout on mobile.

### Task 4: Verify code and backend integration

**Files:**
- Modify only if verification exposes a regression in files already in scope.

**Steps:**
1. Run focused unit tests, then the complete frontend unit suite.
2. Run `npm run typecheck`, `npm run lint`, and `npm run build`.
3. Run the focused backend coach, TTS, stream, and persona tests.
4. Search the related coach paths for duplicate stale wiring or same-pattern regressions.

### Task 5: Visual and interaction QA

**Files:**
- Store temporary screenshots outside committed product source.

**Steps:**
1. Open `/coach` at desktop and mobile viewports.
2. Confirm canvas pixels are nonblank, the coach is framed correctly, and the canvas changes across frames and pointer movement.
3. Exercise text chat, streamed reply, TTS/lip motion, microphone availability, loading, error, and fallback states.
4. Confirm no overflow, overlap, console errors, or inaccessible unlabeled controls.
