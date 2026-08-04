"""Build full-canvas character layers that can be centered together in Rive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


BODY_LAYER_NAMES = (
    "head-neck",
    "torso",
    "upper-arm-left",
    "upper-arm-right",
    "forearm-left",
    "forearm-right",
    "hand-left",
    "hand-right",
    "pelvis",
    "thigh-left",
    "thigh-right",
    "lower-leg-left",
    "lower-leg-right",
    "shoe-left",
    "shoe-right",
)

BODY_PIVOTS = {
    "head-neck": (627, 220),
    "torso": (627, 490),
    "upper-arm-left": (470, 280),
    "upper-arm-right": (784, 280),
    "forearm-left": (398, 425),
    "forearm-right": (856, 425),
    "hand-left": (374, 610),
    "hand-right": (880, 610),
    "pelvis": (627, 620),
    "thigh-left": (560, 705),
    "thigh-right": (694, 705),
    "lower-leg-left": (535, 900),
    "lower-leg-right": (719, 900),
    "shoe-left": (505, 1095),
    "shoe-right": (749, 1095),
}

FACE_CELL_ORIGIN = (438, -39)


def body_labels(width: int, height: int) -> np.ndarray:
    """Assign each canvas pixel to exactly one articulated body region."""
    y, x = np.indices((height, width))
    labels = np.full((height, width), BODY_LAYER_NAMES.index("shoe-right"), dtype=np.uint8)

    labels[(y < 1105) & (x < width / 2)] = BODY_LAYER_NAMES.index("lower-leg-left")
    labels[(y < 1105) & (x >= width / 2)] = BODY_LAYER_NAMES.index("lower-leg-right")
    labels[(y < 900) & (x < width / 2)] = BODY_LAYER_NAMES.index("thigh-left")
    labels[(y < 900) & (x >= width / 2)] = BODY_LAYER_NAMES.index("thigh-right")
    labels[y < 745] = BODY_LAYER_NAMES.index("pelvis")
    labels[y < 590] = BODY_LAYER_NAMES.index("torso")

    labels[(y < 760) & (x < 465)] = BODY_LAYER_NAMES.index("hand-left")
    labels[(y < 760) & (x > 789)] = BODY_LAYER_NAMES.index("hand-right")
    labels[(y < 620) & (x < 470)] = BODY_LAYER_NAMES.index("forearm-left")
    labels[(y < 620) & (x > 784)] = BODY_LAYER_NAMES.index("forearm-right")
    labels[(y < 420) & (x < 500)] = BODY_LAYER_NAMES.index("upper-arm-left")
    labels[(y < 420) & (x > 754)] = BODY_LAYER_NAMES.index("upper-arm-right")
    labels[(y < 285) & (x >= 500) & (x <= 754)] = BODY_LAYER_NAMES.index("head-neck")

    labels[(y >= 1105) & (x < width / 2)] = BODY_LAYER_NAMES.index("shoe-left")
    return labels


def expand_face_layer(image: Image.Image, canvas_size: tuple[int, int]) -> Image.Image:
    """Place one atlas-relative face layer into the shared stage coordinate system."""
    canvas = Image.new("RGBA", canvas_size)
    canvas.alpha_composite(image.convert("RGBA"), dest=FACE_CELL_ORIGIN)
    return canvas


def prepare_layers(base_path: Path, face_dir: Path, output_dir: Path) -> None:
    """Write disjoint body layers, aligned face layers, and a Rive placement manifest."""
    base = Image.open(base_path).convert("RGBA")
    base_array = np.asarray(base)
    labels = body_labels(base.width, base.height)
    visible = base_array[:, :, 3] > 0
    y, x = np.indices((base.height, base.width))
    jaw_mask = (
        visible
        & (y >= 120)
        & ((((x - 627) / 112) ** 2) + (((y - 188) / 88) ** 2) <= 1)
    )
    body_output = output_dir / "body"
    face_output = output_dir / "face"
    body_output.mkdir(parents=True, exist_ok=True)
    face_output.mkdir(parents=True, exist_ok=True)

    for index, name in enumerate(BODY_LAYER_NAMES):
        layer_array = np.zeros_like(base_array)
        mask = visible & ~jaw_mask & (labels == index)
        layer_array[mask] = base_array[mask]
        Image.fromarray(layer_array, mode="RGBA").save(body_output / f"{name}.png", optimize=True)

    jaw_array = np.zeros_like(base_array)
    jaw_array[jaw_mask] = base_array[jaw_mask]
    Image.fromarray(jaw_array, mode="RGBA").save(face_output / "jaw.png", optimize=True)

    face_names = ["jaw"]
    for path in sorted(face_dir.glob("*.png")):
        face_names.append(path.stem)
        aligned = expand_face_layer(Image.open(path), base.size)
        aligned.save(face_output / path.name, optimize=True)

    manifest = {
        "canvas_size": list(base.size),
        "face_cell_origin": list(FACE_CELL_ORIGIN),
        "body_layers": [
            {"name": name, "pivot": list(BODY_PIVOTS[name])}
            for name in BODY_LAYER_NAMES
        ],
        "face_layers": face_names,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    """Parse project paths and generate full-canvas Rive source layers."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--face-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    prepare_layers(args.base, args.face_dir, args.output_dir)


if __name__ == "__main__":
    main()
