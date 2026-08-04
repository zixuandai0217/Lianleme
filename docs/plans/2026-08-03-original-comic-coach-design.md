# Original Comic Coach Design

## Goal

Replace the current uncanny celebrity-like coach with a polished original comic fitness coach that feels confident, humorous, and capable of synchronized speech without looking like separate facial stickers.

## Character Direction

The character borrows only broad performance cues associated with Dwayne Johnson: a bald athletic silhouette, confident posture, a playful raised eyebrow, and warm stage presence. The face shape, eyes, nose, jaw, clothing, emblem, and shoulder graphic remain original and must not reproduce his likeness or recognizable tattoos.

The coach is a believable muscular adult rather than an exaggerated bodybuilder. He wears a black training vest with vivid orange piping and an original lightning emblem. Rendering uses crisp commercial-comic outlines, three-step cel shading, natural warm skin, and restrained texture. The default expression is a subtle closed-mouth smile, not a broad exposed-teeth grin.

## Composition

The runtime illustration uses a stable square coordinate system and a waist-up three-quarter front pose. The torso is offset slightly from center, one hand is raised in a relaxed explanatory gesture, and the other arm rests naturally. The head and shoulders have enough negative space to avoid the cramped crop visible in the previous version.

Both stage and portrait variants share the same identity. The stage view shows the waist-up performance, while the dashboard portrait crops around the head and upper torso without changing artwork proportions.

## Facial Animation

The base illustration contains the complete natural face and a neutral X mouth. Speaking overlays replace only a compact mouth region using the existing A-H/X viseme contract. Every viseme matches the base face's perspective, outline weight, skin transition, and lighting. The renderer does not replace the full eyes or broad patches of face skin.

Blinking uses a small closed-eyelid overlay. Thinking uses a restrained eyebrow overlay. Speaking adds only subtle jaw lift and breathing; the character does not sway, track the pointer, or rotate as a whole. Reduced-motion mode keeps the neutral face and audio playback while freezing visual motion.

## Asset Workflow

1. Generate one standalone concept image and review character identity before any runtime replacement.
2. Generate a chroma-keyed canonical square master from the approved concept.
3. Generate an identity-preserving facial atlas for A-H/X, closed eyelids, and thinking brows.
4. Remove the chroma key, align all layers to the canonical canvas, and validate alpha bounds and visual seams.
5. Store new files in versioned `web/public/coach/v2/` paths. Keep the current assets available until browser QA passes.

## Runtime And Failure Handling

`DigitalCoach` remains the single React/CSS renderer. Existing state, viseme, blink, portrait, and reduced-motion behavior stays intact. Asset URLs move behind one versioned manifest so the character can be switched atomically.

If a facial overlay fails, the component keeps the neutral base face instead of hiding the character. If the new body asset fails, the current production coach remains the fallback during rollout.

## Acceptance Criteria

- The coach reads as an original product character, not a copy of a public figure.
- Neutral, speaking, and thinking states keep the same identity and facial proportions.
- Mouth changes have no rectangular skin patch, coordinate jump, or lighting seam.
- The character remains well framed on desktop and mobile without horizontal overflow.
- A-H/X timing, blink cleanup, portrait behavior, and reduced-motion behavior remain covered by tests.
