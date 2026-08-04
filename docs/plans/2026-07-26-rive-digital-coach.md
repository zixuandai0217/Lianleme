# Rive Digital Coach Implementation Plan

**Goal:** Make the homepage a single digital-coach entry point that guides users into analysis, planning, coaching, and tracking while reducing global navigation complexity.

**Architecture:** Keep all existing routes and API behavior, but expose only three primary destinations in the application shell. Add a focused Rive component that derives its message and animation from the user's current training state, with a text-first fallback for loading errors and reduced-motion preferences.

**Tech Stack:** React 19, TypeScript 6, Vite 8, Tailwind CSS 4, Rive React Canvas, Vitest, Playwright-compatible browser QA.

---

### Task 1: Lock the product contract

- Require `@rive-app/react-canvas` and a locally served `.riv` file.
- Require exactly three primary navigation destinations: `/`, `/weight`, and `/profile`.
- Require homepage actions for `/analysis`, `/plan`, `/coach`, and `/weight`.
- Require an accessible text fallback plus reduced-motion behavior.

### Task 2: Build the digital coach

- Add the MIT-licensed Rive example avatar to `web/public/rive/` with attribution.
- Create a stable, responsive coach canvas with loading and error fallbacks.
- Select the avatar mood and coaching copy from body-analysis, plan, rest-day, and workout state.

### Task 3: Simplify the experience

- Replace the dashboard workflow tiles with one coach-led command area.
- Keep training metrics compact and retain the complete today-workout/check-in flow.
- Reduce desktop and mobile navigation to Digital Coach, Records, and Profile while keeping detail routes reachable through contextual actions.

### Task 4: Verify and deploy

- Run focused tests, typecheck, lint, all unit tests, production build, and diff checks.
- Review the change for preserved API calls and adjacent navigation regressions.
- Test canvas pixels, loading behavior, interaction, and layout at mobile, tablet, and desktop widths.
- Deploy the verified static build and compare local and remote file hashes.
