---
name: drawio-skill
description: Use when the user requests editable draw.io/diagrams.net diagrams, technical architecture diagrams, flowcharts, ER/UML/sequence diagrams, network topology, ML/DL or research figures, mind maps, codebase visualizations, reference-image redraws, high-fidelity figure replication, local preview screenshots, or PNG/SVG/PDF/JPG exports from .drawio XML.
---

# Draw.io Diagram Skill

## Overview

Produce editable `.drawio` XML as the primary artifact, then validate and preview it before handoff. Use draw.io primitives, explicit geometry, official shape styles, and screenshot feedback so diagrams remain editable and reviewable instead of becoming embedded raster screenshots.

This skill merges two workflows:

- broad diagram generation with shape search, AI-brand icons, style presets, code importers, Graphviz autolayout, native draw.io desktop export, and PNG repair
- research-figure and reference-image replication with local short-URL preview, XML validation, required planning artifacts, and screenshot-based iteration

## Routing

Use a simpler format instead when it is clearly better:

| User need | Prefer |
|---|---|
| Diagrams-as-code in Markdown or docs | Mermaid |
| Strict UML source text checked into git | PlantUML |
| Casual freehand whiteboard sketch | Excalidraw or tldraw |
| Editable, styled, shape-rich, exportable, or high-fidelity diagram | This skill |

## Bundled Resources

Resolve paths relative to this skill directory. Load only the files needed for the request.

| Resource | Use when |
|---|---|
| `references/diagram-types.md` | User names ERD, UML class, sequence, architecture, ML/DL, flowchart, or another known diagram type |
| `references/drawio-workflow.md` | Need the full prompt/paper/code/reference-image to editable draw.io workflow |
| `references/xml-authoring.md` | Writing or repairing XML shapes, geometry, edges, text layout, icons, and styles |
| `references/reference-replication-protocol.md` | User supplies a reference image and asks to redraw, copy, reproduce, replicate, or closely match it |
| `references/shapes.md` and `scripts/shapesearch.py` | Need exact built-in draw.io shapes for AWS, Azure, GCP, Cisco, Kubernetes, UML, BPMN, ER, electrical, P&ID, network, or other palettes |
| `scripts/aiicons.py` | Need AI/LLM brand logos such as OpenAI, Claude, Gemini, Mistral, Llama, Hugging Face, Ollama, or LangChain |
| `references/autolayout.md`, `scripts/autolayout.py`, and `scripts/ensure_graphviz.py` | Diagram is large or graph-like, especially dependency graphs, call graphs, code structure, or more than about 15 nodes; install Graphviz automatically if `dot` is missing |
| `scripts/pyimports.py`, `jsimports.py`, `goimports.py`, `rustimports.py` | User asks to visualize project imports for Python, JS/TS, Go, or Rust |
| `scripts/pyclasses.py` | User asks for a Python class hierarchy or class diagram |
| `references/style-presets.md` and `references/style-extraction.md` | User asks to learn, apply, list, set default, delete, or manage a style preset |
| `scripts/validate.py` | Need structural lint for dangling edges, duplicate IDs, reserved IDs, broken parents, or overlaps |
| `scripts/validate_drawio.py` | Need basic XML integrity checks, page/cell counts, and embedded-raster detection |
| `scripts/make_drawio_preview.py` | Need a local preview HTML that avoids huge diagrams.net URLs |
| `scripts/serve_drawio_preview.py` | Need to generate preview HTML and serve it on `127.0.0.1` |
| `scripts/validate_replication_artifacts.py` | Need to enforce reference-image replication planning and screenshot-review artifacts |
| `scripts/encode_drawio_url.py` | Native CLI is unavailable and a browser fallback URL is acceptable |
| `scripts/repair_png.py` | After every final PNG export with embedded XML (`-e`) |
| `references/troubleshooting.md` | Export, preview, vision, sandbox, URL, PNG, WSL, or rendering failures |

## Standard Workflow

1. **Classify the task.**
   Identify whether this is prompt-to-diagram, paper-to-diagram, codebase-to-diagram, reference-image replication, export/repair, or iterative polish. Ask only for missing information that affects output: diagram type, fidelity, required labels/assets, output path, and output format.

2. **Resolve style and shape sources.**
   If a user preset is named, apply `references/style-presets.md`. If no preset is active, use restrained default colors and `Comic Sans MS` as the default font. For non-trivial vendor or domain shapes, run `scripts/shapesearch.py "<keywords>"` instead of guessing `shape=mxgraph.*`. For AI logos, use `scripts/aiicons.py`.

3. **Plan the diagram before XML.**
   Select layout grammar: left-to-right pipeline, top-down process, swimlanes, layered architecture, hierarchy/tree, graph, feedback loop, or page-per-view. For high-fidelity or dense work, write a coordinate plan with canvas size, margins, regions, key x/y baselines, repeated component sizes, and connector routes.

4. **Use the reference replication protocol when required.**
   If the user supplied a reference image and asked for redraw/reproduction/copy/replica/high fidelity, read `references/reference-replication-protocol.md` before drawing. Create `visual-spec.md`, `layout-grid.md`, `asset-ledger.md`, and `defect-log.md` next to the working `.drawio` file, then run:

   ```bash
   python3 <skill-dir>/scripts/validate_replication_artifacts.py <workdir>
   ```

5. **Author `.drawio` XML as the source of truth.**
   Use one `mxfile` with one or more `diagram` pages. Include root cells `id="0"` and `id="1"`. Use stable human-readable IDs for high-fidelity work. Use explicit `mxGeometry` positions and sizes. Keep text bounded unless standalone labels intentionally overflow. Every edge must include `<mxGeometry relative="1" as="geometry" />`.

6. **Choose the layout engine.**
   Hand-place small or high-fidelity diagrams. For large graph-like diagrams, generate graph JSON and run `scripts/autolayout.py`, or first run the matching import extractor for Python, JS/TS, Go, Rust, or Python classes.

7. **Validate.**
   Run both checks when applicable:

   ```bash
   python3 <skill-dir>/scripts/validate.py <file>.drawio
   python3 <skill-dir>/scripts/validate_drawio.py <file>.drawio
   ```

   Use `--allow-raster` only when the user explicitly approved embedded raster images.

8. **Preview with the most reliable available path.**
   Prefer the local iframe preview because it avoids Windows and browser long-URL failures:

   ```bash
   python3 <skill-dir>/scripts/serve_drawio_preview.py <file>.drawio --port 8765
   ```

   Then open `http://127.0.0.1:8765/drawio-preview.html?rev=1`, wait 3-5 seconds for diagrams.net to load, and take a screenshot with available browser automation. If this path is unavailable but the native draw.io CLI works, export a draft PNG without `-e`.

9. **Iterate from evidence.**
   Inspect the latest screenshot. Fix concrete visible issues in small batches: text overflow, clipped labels, wrong arrowheads, connector crossings, bad z-order, missing icons, color mismatch, spacing drift, or unintended wrapping. Regenerate preview HTML after XML edits; it does not read the `.drawio` file live.

10. **Export final formats when requested.**
   Resolve the draw.io CLI binary name first: `drawio`, `draw.io`, `/Applications/draw.io.app/Contents/MacOS/draw.io`, or the Windows executable path. Preview PNGs must not use `-e`; final PNG/SVG/PDF may use `-e` to embed editability.

   ```bash
   drawio -x -f png --width 2000 -o diagram.png diagram.drawio
   drawio -x -f png -e -s 2 -o diagram.drawio.png diagram.drawio
   python3 <skill-dir>/scripts/repair_png.py diagram.drawio.png
   drawio -x -f svg -e -o diagram.svg diagram.drawio
   drawio -x -f pdf -e -o diagram.pdf diagram.drawio
   ```

## XML Authoring Rules

- Escape XML attribute values: `&amp;`, `&lt;`, `&gt;`, `&quot;`.
- Use `&#xa;` for line breaks inside `value` attributes.
- Snap x/y/width/height to multiples of 10 unless matching a reference image requires finer geometry.
- Use containers properly: child cells set `parent="<containerId>"` and coordinates are relative to the container.
- Add `pointerEvents=0;` to visual containers that should not capture child connections.
- Pin `exitX/exitY/entryX/entryY` when a node has multiple connectors on the same side.
- Route edges through empty corridors with waypoints rather than through unrelated shapes.
- Split important multiline text into separate cells when exact alignment matters.
- Build icons from editable primitives when possible. If exact raster or SVG assets are necessary, record provenance and reduced editability.

## Export and Preview Fallbacks

| Situation | Action |
|---|---|
| draw.io desktop CLI works | Use CLI for draft and final exports |
| CLI crashes or returns empty output in a macOS sandbox | Stop retrying; use local iframe preview or browser fallback |
| CLI missing, Python available | Deliver `.drawio` plus local preview or encoded diagrams.net URL |
| CLI and browser preview unavailable | Deliver valid `.drawio` XML and explain manual open/export steps |
| PNG exported with `-e` | Always run `scripts/repair_png.py` before using or handing off the PNG |
| Browser preview looks stale | Re-run `make_drawio_preview.py` or `serve_drawio_preview.py` and refresh with `?rev=N` |
| Reference-image fidelity is requested | Final handoff requires screenshot review and replication artifact validation |

## Verification Checklist

Before claiming the diagram is ready:

- `.drawio` file exists and is the primary artifact.
- XML parses and contains at least one diagram page and visible cells.
- Structural validation passed or any warnings are explicitly explained.
- No unintended embedded raster images exist.
- Latest preview or export was generated after the last XML edit.
- A screenshot was reviewed for complex, user-facing, or high-fidelity work.
- Text fits, arrows point correctly, connectors do not cross labels, and shapes are not clipped.
- For reference replication, `defect-log.md` contains a red-team visual audit and remaining gaps.
- Final response includes file paths for the `.drawio` source, screenshots/previews, and exports.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Guessing shape names | Use `scripts/shapesearch.py` |
| Treating preview HTML as source | Edit `.drawio`; regenerate HTML |
| Final raster-only output for an editable request | Keep `.drawio` as primary and use editable primitives |
| Skipping screenshots on visual work | Preview, screenshot, inspect, then patch |
| Embedding a reference image as the final answer | Rebuild with editable objects; use the image only as reference unless approved |
| Using huge diagrams.net URLs | Use `make_drawio_preview.py` or `serve_drawio_preview.py` |
| Broad rewrites after minor feedback | Patch the specific XML cells involved |
| Claiming 100% reproduction | List observed evidence and remaining mismatches unless the user accepts the result |

## Attribution

This packaged skill combines MIT-licensed resources from Agents365-ai `drawio-skill` and Will-hxw `drawio-diagram-builder-skill`. Shape index data is derived from jgraph/drawio-mcp and diagrams.net shape libraries under Apache License 2.0; see `data/SHAPE-INDEX-NOTICE.md`.
