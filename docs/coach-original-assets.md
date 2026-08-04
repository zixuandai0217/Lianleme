# Original Coach Source Assets

## Source

- Generated on 2026-07-31 with ChatGPT Image through the user's existing Chrome session.
- The canonical character, body atlas, and facial atlas were generated in one conversation so later images could preserve the first image's identity.
- The built-in `image_gen` tool was not exposed in this workspace, so the user-approved Computer Use fallback was used.
- The character is original. Prompts explicitly exclude Dwayne Johnson, The Rock, other public figures, and existing fictional characters.
- Raw generations used a removable green background. Project layers were processed locally with the imagegen skill's `remove_chroma_key.py`, then sliced with `web/scripts/prepare-coach-assets.py`.

## Canonical Prompt

```text
Use case: stylized-concept

Create an original full-body 2D cartoon fitness coach character for an interactive talking avatar and Rive bone rig.
Identity: bald, very muscular adult male, humorous and confident expression, broad friendly face, warm medium skin tone, thick expressive eyebrows, clean-shaven.
Wardrobe: black training tank top with vivid bright-orange piping, charcoal training pants, black/orange trainers.
Distinctive original detail: a small geometric angular shoulder tattoo made only from simple triangles and parallel lines; it must not resemble any celebrity tattoo.
Pose and framing: straight-on neutral A-pose with arms slightly separated from torso, hands relaxed, feet planted at equal height, full body visible, stable front view, centered, generous padding around every limb.
Art style: polished 2D game-character key art, crisp shapes, clean cel shading, subtle dimensional highlights, energetic but not childish, suitable for a premium fitness app.
Rigging requirements: clear separations at neck, shoulders, elbows, wrists, hips, knees and ankles; symmetrical neutral silhouette; no motion blur; no extreme perspective.
Background: perfectly flat solid #00FF00 chroma-key background, one uniform color, no shadows, no gradients, no texture, no floor plane, no reflections.
Do not use #00FF00 anywhere in the character.
No text, no logo, no watermark, no props, no cast shadow.
The character must be wholly original. Do not resemble Dwayne Johnson, The Rock, any actor, athlete, public figure, or existing fictional character.
```

## Body Atlas Prompt

```text
Use case: identity-preserve

Create a clean 4 by 4 character-rig parts atlas for this exact same 2D fitness coach. Each cell contains exactly one isolated body part, fully visible with generous empty spacing and no overlap:
row 1: head with neck, torso from neck base to hips, left upper arm, right upper arm;
row 2: left forearm, right forearm, left hand, right hand;
row 3: pelvis, left thigh, right thigh, left lower leg;
row 4: right lower leg, left shoe, right shoe, neutral full-body reference miniature.

Every part must preserve the exact same cel-shaded rendering, clothing seams, orange piping, skin tone and geometric shoulder tattoo from the reference image. Limbs are shown in the same front-facing neutral pose and at consistent scale so they can be reassembled without style drift. Add subtle hidden overlap under joints for bone animation. No labels, no guides, no borders, no text.

Background: perfectly flat solid #00FF00 chroma-key background, one uniform color, no shadows, no gradients, no texture, no floor plane, no reflections. Do not use #00FF00 in any body part. Crisp edges, no cast shadows, no watermark. Do not alter the identity and do not resemble any public figure.
```

## Facial Atlas Prompt

The first facial result was rejected because it had five rows, extra composite face panels, and inconsistent coordinates. Only the facial atlas was regenerated.

```text
Use case: identity-preserve

STRICT LAYOUT: exactly 4 columns by exactly 4 rows, exactly 16 cells total. No fifth row. No extra items. Every cell must contain exactly one isolated facial layer centered at the same scale. Use the exact same original coach identity and clean cel-shaded line weight from the first character image.

Cell order, left to right:
Row 1: X closed relaxed lips; A compressed closed lips; B small teeth mouth; C medium open mouth.
Row 2: D wide open mouth; E rounded O mouth; F pursed lips; G lower lip touching upper teeth.
Row 3: H tongue consonant mouth; both eye whites only; both pupils only; both closed eyelids only.
Row 4: both squint eyelids only; both neutral eyebrows only; thinking eyebrows only; emphasis eyebrows only.

Mouth cells must contain mouths only. Eye cells must contain eyes only. Eyebrow cells must contain eyebrows only. Never include a full face, nose, forehead, skin bridge, duplicate eyes, composite expression panel, labels, grid lines, guides, text, or any seventeenth item.

Perfectly flat solid #00FF00 background with no gradient, texture, shadow or floor. Do not use green in the parts. Crisp antialiased edges, no watermark.
```

## Outputs

- `web/public/coach/rock-coach.webp`: approved square runtime character base.
- `web/public/coach/face/`: aligned transparent WebP mouth, eye, and brow layers.
- `web/public/coach/coach-original.webp`: original full-body source reference.
- `web/public/coach/layers/body/`: 16 transparent body layers plus manifest.
- `web/public/coach/layers/face/`: 16 coordinate-stable transparent facial layers plus manifest.

Run `python3 web/scripts/validate-coach-assets.py` after regenerating any coach asset.
