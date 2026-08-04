# Modern Athletic Workspace Design

## Direction

The approved direction is a modern athletic workspace: quiet enough for repeated daily use, energetic enough to feel like a fitness product, and more operational than editorial. The interface will use graphite, clean white, cool gray-green, forest green, and coral orange. Typography will be sans-forward so Chinese interface copy scans quickly; Poppins remains a restrained display face, while Geist becomes the default body face.

The memorable element is not a giant avatar. It is the relationship between a compact animated coach and one clear recommendation. Rive remains present as a living status signal, but no longer owns half the first viewport or forces its saturated purple background to dominate the product palette.

## Application Shell

Desktop uses a full-width top bar with the brand at left, three centered primary destinations, and a compact user/logout control at right. This keeps the content canvas wide and removes the visual weight of the permanent black rail. Mobile uses a simple top brand bar plus a fixed three-item bottom navigation, avoiding a hidden drawer for the application's most frequent destinations.

Detail routes such as analysis, plan, and coach remain registered. They are reached from contextual homepage actions, preserving the reduced global navigation without removing workflow depth.

## Dashboard Hierarchy

The dashboard begins with a compact greeting and date. The coach area is a charcoal/forest status band with three parts: a small Rive portrait, a concise state-dependent recommendation, and one primary command. The recommended command is derived from existing body-analysis, plan, rest-day, and workout state. The other three workflows appear as lower-emphasis quick actions, so every destination remains reachable without presenting four equal calls to action.

Below the coach band, consistency metrics become a single dense row rather than a second feature section. Today's workout and recent activity remain intact but use calmer white surfaces and tighter spacing. Existing check-in dialogs, API calls, loading states, and data behavior are unchanged.

## Responsive And Accessibility Rules

The content container remains stable from 375px through wide desktop. At mobile widths the coach portrait, recommendation, and primary action stack without occluding copy; fixed bottom navigation adds matching content padding. Click targets remain at least 44px, focus rings remain visible, Rive respects reduced motion, and the text fallback remains available when local Rive runtime files cannot load.

The redesign is successful when the first viewport communicates one next step, no saturated purple region dominates the page, all text remains readable without horizontal scrolling, and frequent navigation needs no menu opening.
