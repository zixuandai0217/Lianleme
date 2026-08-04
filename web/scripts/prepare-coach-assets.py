"""Slice transparent coach atlases into validated, consistently named Rive layers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

BODY_LAYERS = (
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
    "reference",
)

FACE_LAYERS = (
    "mouth-X",
    "mouth-A",
    "mouth-B",
    "mouth-C",
    "mouth-D",
    "mouth-E",
    "mouth-F",
    "mouth-G",
    "mouth-H",
    "eyes-white",
    "pupils",
    "eyes-closed",
    "eyes-squint",
    "brows-neutral",
    "brows-thinking",
    "brows-emphasis",
)


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Return the occupied alpha bounds for one transparent image."""
    return image.getchannel("A").getbbox()


def padded_bbox(
    bbox: tuple[int, int, int, int],
    width: int,
    height: int,
    padding: int = 4,
) -> tuple[int, int, int, int]:
    """Expand occupied bounds while keeping the crop inside its atlas cell."""
    left, top, right, bottom = bbox
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def slice_atlas(source: Path, output: Path, kind: str) -> None:
    """Split a 4x4 atlas and write layer metadata for Rive assembly."""
    names = BODY_LAYERS if kind == "body" else FACE_LAYERS
    image = Image.open(source).convert("RGBA")
    width, height = image.size
    if width < 400 or height < 400:
        raise ValueError("Coach atlas is too small for stable 4x4 slicing")

    output.mkdir(parents=True, exist_ok=True)
    face_cell_size = ((width + 3) // 4, (height + 3) // 4)
    manifest: dict[str, object] = {
        "source": source.name,
        "kind": kind,
        "atlas_size": [width, height],
        "grid": [4, 4],
        "layers": [],
    }

    for index, name in enumerate(names):
        column = index % 4
        row = index // 4
        cell_box = (
            round(column * width / 4),
            round(row * height / 4),
            round((column + 1) * width / 4),
            round((row + 1) * height / 4),
        )
        cell = image.crop(cell_box)
        occupied = alpha_bbox(cell)
        if occupied is None:
            raise ValueError(f"Layer {name} has no visible pixels")

        # Facial layers keep identical cell coordinates so every viseme aligns in Rive.
        if kind == "face":
            layer = Image.new("RGBA", face_cell_size, (0, 0, 0, 0))
            layer.paste(cell, (0, 0))
            local_box = (0, 0, layer.width, layer.height)
        else:
            local_box = padded_bbox(occupied, cell.width, cell.height)
            layer = cell.crop(local_box)

        corners = (
            layer.getpixel((0, 0))[3],
            layer.getpixel((layer.width - 1, 0))[3],
            layer.getpixel((0, layer.height - 1))[3],
            layer.getpixel((layer.width - 1, layer.height - 1))[3],
        )
        if max(corners) > 20:
            raise ValueError(f"Layer {name} has a non-transparent corner")

        filename = f"{name}.png"
        layer.save(output / filename, optimize=True)
        manifest["layers"].append(
            {
                "name": name,
                "file": filename,
                "cell": [column, row],
                "cell_box": list(cell_box),
                "local_crop": list(local_box),
                "size": [layer.width, layer.height],
                "alpha_bbox": list(occupied),
            }
        )

    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Parse CLI input and prepare one coach atlas."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("body", "face"), required=True)
    args = parser.parse_args()
    slice_atlas(args.source, args.output, args.kind)


if __name__ == "__main__":
    main()
