# Original Comic Coach V2 Assets

## Concept Source

- Generated on 2026-08-03 with ChatGPT Image through the user's signed-in in-app browser session.
- Conversation title: `Premium Fitness Coach Concept`.
- Use case: `stylized-concept`.
- The concept intentionally borrows only broad performance qualities associated with Dwayne Johnson. It does not reproduce his facial likeness, clothing, or tattoos.

## Concept File

- Runtime-neutral preview: `web/public/coach/concepts/coach-comic-v1.png`
- Dimensions: `1254 x 1254`
- Format: RGB PNG without alpha
- Bytes: `1589520`
- SHA-256: `19c5a0c75c71a16adf2cccf195666e980260129921ee5ec34d2b2b2835dd2f5b`

## Final Prompt

```text
Create one square concept illustration for a premium mobile fitness app.

Use case: stylized-concept.
Subject: an original adult male comic fitness coach. Borrow only broad performance qualities associated with Dwayne Johnson: a bald athletic silhouette, warm confidence, playful single raised eyebrow, and humorous stage presence. Do NOT reproduce Dwayne Johnson's facial likeness, face shape, recognizable clothing, or tattoos. This must be a distinct original product mascot.

Appearance: believable muscular athlete proportions, broad but natural shoulders, an original friendly face, warm medium-brown skin, clean-shaven. A subtle closed-mouth half smile with no exposed row of teeth. Natural eyes seated correctly in the sockets.
Pose: waist-up, stable three-quarter front view. One hand raised naturally in a conversational coaching gesture, the other arm relaxed. Do not cross the arms. Keep the head, shoulders, raised hand, and torso fully inside frame with generous negative space.
Wardrobe: fitted black training vest with vivid bright-orange piping, a tiny original angular lightning emblem with no text, and a restrained original geometric shoulder motif made from simple lines that does not resemble any celebrity tattoo.
Art direction: polished commercial 2D comic illustration, crisp confident outlines, three-step cel shading, natural facial modeling, subtle print-grain texture, premium game-character key art, mature and energetic rather than childish or photorealistic.
Background: one clean flat deep charcoal-green field with no gradient, objects, scenery, or typography.
Animation readiness: the neutral closed mouth should be clean and compact for later lip-sync replacement. Facial lighting and jaw contour must remain clear at mobile size.

Avoid: celebrity portrait, photorealism, uncanny smile, broad exposed-teeth grin, pasted facial features, oversized head, exaggerated bodybuilder anatomy, giant foreground arms, malformed hands, extra fingers, text, letters, brand logo, watermark, props, cropped head, cropped hand, decorative background. Produce a single character, not a contact sheet.
```

## Runtime Master

- Generated in the same ChatGPT conversation by editing the approved concept, preserving its identity and composition.
- Runtime-master prompt:

```text
Use the exact coach image you just created as the edit target and preserve the character identity, face, expression, pose, anatomy, clothing, orange trim, lightning emblem, shoulder motif, crop, camera, linework, colors, shading, and proportions exactly. Change only the background: replace it with a perfectly flat solid #00FF00 chroma-key field for local background removal. The background must be one uniform color edge to edge with no gradient, vignette, texture, shadow, floor, reflection, halo, or ambient green spill. Do not use #00FF00 anywhere on the character. Keep crisp antialiased silhouette edges and the same square canvas. Do not add text, watermark, props, or new details. Return one image only.
```

## Runtime Sources

- Chroma-key master: `web/public/coach/v2/source/coach-base-chroma.png`
  - SHA-256: `0b9b8fca063b229360e657ddcb5c98716d75715b79b5450f4332f679dc52393f`
- Transparent master: `web/public/coach/v2/source/coach-base-transparent.png`
  - SHA-256: `0dabf9ef93dd53e7f26f840e96bc12bafb02dc73ddcdb1494fc0e8ab16087fed`
- Optimized runtime body: `web/public/coach/v2/coach-base.webp`
  - SHA-256: `2cbb25de2be25a0f9ca48846ea42115f4d47be61addae8e89bc7c7c45b9728b6`
- Runtime manifest: `web/public/coach/v2/manifest.json`
  - SHA-256: `07b3474e49c6de832c76325026ea213349dcf5db5b778bc55bef898a0e5e52e6`
- Runtime bundle size: `914272` bytes.
- Facial runtime layers are deterministically generated from the transparent master by `web/scripts/generate_coach_v2_assets.py` and validated by `web/scripts/validate-coach-assets.py`.

## Review Notes

- The face reads as an original identity and does not reproduce a public figure.
- The neutral closed-mouth half smile is suitable for a lip-sync base.
- The eyes, eyebrows, and jaw remain readable at compact sizes.
- The raised hand is anatomically plausible and supports a conversational pose.
- The shoulders and arms are muscular but do not dominate the full canvas.
- The black/orange wardrobe and geometric shoulder motif match the product theme.
- The approved concept now backs the versioned `web/public/coach/v2/` runtime bundle.
