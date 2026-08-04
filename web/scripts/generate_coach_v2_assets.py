#!/usr/bin/env python3
"""Generate the aligned comic coach body and facial runtime bundle."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from generate_coach_face_assets import (
    moved_feature,
    original_plate,
    polygon_mask,
    quadratic_curve,
    repaired_plate,
    save_layer,
    scaled_box,
    scaled_points,
    vector_layer,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "public" / "coach" / "v2" / "source" / "coach-base-transparent.png"
OUTPUT_DIR = ROOT / "public" / "coach" / "v2"
FACE_DIR = OUTPUT_DIR / "face"
CANVAS_SIZE = (1254, 1254)
MOUTH_AXIS_DEGREES = 8

SKIN_DARK = (78, 32, 21, 255)
LIP = (137, 57, 35, 255)
LIP_LIGHT = (211, 106, 66, 255)
MOUTH_DARK = (38, 17, 14, 255)
TEETH = (244, 229, 205, 255)
TONGUE = (174, 70, 65, 255)
EYELID = (179, 78, 42, 255)

MOUTH_POLYGON = [[
    (529, 342), (545, 328), (570, 330), (596, 343), (622, 344),
    (651, 331), (670, 326), (676, 347), (663, 373), (633, 389),
    (587, 396), (550, 385), (533, 366),
]]

LEFT_EYE = [(480, 243), (498, 226), (526, 224), (557, 247), (550, 274), (520, 287), (492, 273)]
RIGHT_EYE = [(584, 221), (606, 204), (643, 202), (680, 225), (670, 254), (638, 268), (603, 254)]

LEFT_BROW = [[(458, 210), (480, 191), (517, 192), (551, 217), (549, 239), (520, 235), (488, 218), (468, 239)]]
RIGHT_BROW = [[(578, 192), (605, 166), (646, 171), (687, 194), (684, 216), (650, 209), (618, 190), (591, 210)]]


def draw_mouth_shape(viseme: str) -> Image.Image:
    """Draw one compact viseme in the approved coach face perspective."""
    local_size = (180, 100)

    def paint(draw: ImageDraw.ImageDraw) -> None:
        line_width = 12
        highlight_width = 6
        if viseme == "A":
            draw.line(scaled_points(quadratic_curve((47, 45), (91, 55), (135, 47))), fill=SKIN_DARK, width=line_width)
            draw.line(scaled_points(quadratic_curve((52, 49), (92, 60), (131, 50))), fill=LIP, width=9)
        elif viseme == "B":
            draw.ellipse(scaled_box((43, 37, 140, 68)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((49, 42, 135, 64)), fill=MOUTH_DARK)
            draw.pieslice(scaled_box((52, 40, 133, 63)), start=180, end=360, fill=TEETH)
            draw.line(scaled_points(quadratic_curve((54, 58), (92, 65), (131, 58))), fill=LIP, width=9)
        elif viseme == "C":
            draw.ellipse(scaled_box((43, 33, 141, 73)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((49, 39, 135, 69)), fill=MOUTH_DARK)
            draw.pieslice(scaled_box((52, 42, 133, 68)), start=190, end=350, fill=TEETH)
            draw.line(scaled_points(quadratic_curve((57, 64), (92, 73), (128, 64))), fill=TONGUE, width=15)
        elif viseme == "D":
            draw.ellipse(scaled_box((38, 27, 145, 81)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((45, 33, 138, 76)), fill=MOUTH_DARK)
            draw.pieslice(scaled_box((49, 35, 135, 64)), start=185, end=355, fill=TEETH)
            draw.pieslice(scaled_box((55, 54, 130, 80)), start=182, end=358, fill=TONGUE)
            draw.line(scaled_points(quadratic_curve((49, 35), (92, 23), (135, 38))), fill=LIP, width=12)
        elif viseme == "E":
            draw.ellipse(scaled_box((66, 27, 119, 78)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((73, 34, 112, 71)), fill=MOUTH_DARK)
            draw.arc(scaled_box((69, 30, 116, 75)), start=205, end=335, fill=LIP_LIGHT, width=9)
        elif viseme == "F":
            draw.ellipse(scaled_box((67, 34, 117, 70)), fill=LIP)
            draw.ellipse(scaled_box((78, 42, 107, 62)), fill=MOUTH_DARK)
            draw.arc(scaled_box((68, 34, 116, 69)), start=185, end=342, fill=LIP_LIGHT, width=9)
        elif viseme == "G":
            draw.rounded_rectangle(scaled_box((45, 35, 138, 70)), radius=42, fill=SKIN_DARK)
            draw.rounded_rectangle(scaled_box((51, 40, 132, 65)), radius=30, fill=MOUTH_DARK)
            draw.pieslice(scaled_box((52, 38, 131, 64)), start=180, end=360, fill=TEETH)
            draw.line(scaled_points(quadratic_curve((56, 58), (92, 67), (128, 59))), fill=LIP, width=12)
        elif viseme == "H":
            draw.ellipse(scaled_box((48, 32, 137, 75)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((54, 38, 131, 71)), fill=MOUTH_DARK)
            draw.ellipse(scaled_box((66, 51, 122, 73)), fill=TONGUE)
            draw.line(scaled_points(quadratic_curve((68, 58), (95, 53), (120, 60))), fill=(224, 116, 102, 255), width=6)

    local = vector_layer(local_size, paint)
    tilted = local.rotate(MOUTH_AXIS_DEGREES, resample=Image.Resampling.BICUBIC, expand=False)
    layer = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    layer.alpha_composite(tilted, (520, 310))
    return layer


def draw_closed_eyes(size: tuple[int, int]) -> Image.Image:
    """Draw two softly closed eyelids over the repaired open-eye regions."""
    def paint(draw: ImageDraw.ImageDraw) -> None:
        draw.line(scaled_points(quadratic_curve((486, 251), (520, 278), (551, 251))), fill=SKIN_DARK, width=15)
        draw.line(scaled_points(quadratic_curve((592, 229), (632, 257), (671, 231))), fill=SKIN_DARK, width=15)
        draw.line(scaled_points(quadratic_curve((493, 255), (520, 271), (545, 254))), fill=EYELID, width=6)
        draw.line(scaled_points(quadratic_curve((600, 233), (632, 250), (663, 234))), fill=EYELID, width=6)

    return vector_layer(size, paint)


def smoothed_skin_plate(base: Image.Image, mask: np.ndarray) -> Image.Image:
    """Remove illustrated lip lines without pulling dark nose edges into the repair."""
    rgb = np.asarray(base.convert("RGB"))
    smoothed = cv2.medianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), 41)
    smoothed = cv2.bilateralFilter(smoothed, 9, 35, 35)
    plate = Image.fromarray(cv2.cvtColor(smoothed, cv2.COLOR_BGR2RGB)).convert("RGBA")
    plate.putalpha(Image.fromarray(mask, mode="L").filter(ImageFilter.GaussianBlur(radius=2.4)))
    return plate


def inspect_asset(role: str, path: Path) -> dict[str, object]:
    """Return validated metadata for one full-canvas transparent asset."""
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        corners = (
            alpha.getpixel((0, 0)),
            alpha.getpixel((rgba.width - 1, 0)),
            alpha.getpixel((0, rgba.height - 1)),
            alpha.getpixel((rgba.width - 1, rgba.height - 1)),
        )
        if rgba.size != CANVAS_SIZE or bbox is None or max(corners) > 20:
            raise RuntimeError(f"Invalid v2 asset: {role} size={rgba.size} bbox={bbox} corners={corners}")
    return {
        "role": role,
        "file": str(path.relative_to(OUTPUT_DIR)),
        "width": CANVAS_SIZE[0],
        "height": CANVAS_SIZE[1],
        "alpha_bbox": list(bbox),
        "bytes": path.stat().st_size,
    }


def write_asset(role: str, layer: Image.Image, path: Path) -> dict[str, object]:
    """Save one lossless WebP and return its verified manifest record."""
    save_layer(layer, path)
    return inspect_asset(role, path)


def main() -> None:
    """Build the complete body, viseme, blink, and thinking bundle."""
    base = Image.open(SOURCE_PATH).convert("RGBA")
    if base.size != CANVAS_SIZE:
        raise RuntimeError(f"Unexpected coach v2 canvas: {base.size}")
    FACE_DIR.mkdir(parents=True, exist_ok=True)

    records = [write_asset("body", base, OUTPUT_DIR / "coach-base.webp")]

    mouth_mask = polygon_mask(CANVAS_SIZE, MOUTH_POLYGON)
    mouth_plate = smoothed_skin_plate(base, mouth_mask)
    resting_mouth = original_plate(base, mouth_mask)
    for viseme in "ABCDEFGHX":
        layer = resting_mouth if viseme == "X" else Image.alpha_composite(mouth_plate, draw_mouth_shape(viseme))
        records.append(write_asset(f"mouth-{viseme}", layer, FACE_DIR / f"mouth-{viseme}.webp"))

    eye_mask = polygon_mask(CANVAS_SIZE, [LEFT_EYE, RIGHT_EYE])
    closed_eye_layer = Image.alpha_composite(repaired_plate(base, eye_mask, radius=6), draw_closed_eyes(CANVAS_SIZE))
    records.append(write_asset("eyes-blink", closed_eye_layer, FACE_DIR / "eyes-blink.webp"))

    left_brow_mask = polygon_mask(CANVAS_SIZE, LEFT_BROW)
    right_brow_mask = polygon_mask(CANVAS_SIZE, RIGHT_BROW)
    brow_mask = left_brow_mask.copy()
    brow_mask[right_brow_mask > brow_mask] = right_brow_mask[right_brow_mask > brow_mask]
    thinking_brows = repaired_plate(base, brow_mask, radius=4)
    thinking_brows = Image.alpha_composite(thinking_brows, moved_feature(base, left_brow_mask, 0, -10, -2.5))
    thinking_brows = Image.alpha_composite(thinking_brows, moved_feature(base, right_brow_mask, 0, 2, 1.0))
    records.append(write_asset("brow-thinking", thinking_brows, FACE_DIR / "brow-thinking.webp"))

    total_bytes = sum(int(record["bytes"]) for record in records)
    manifest = {
        "canvas": list(CANVAS_SIZE),
        "format": "lossless-webp-rgba",
        "total_bytes": total_bytes,
        "assets": records,
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(records)} comic coach assets ({total_bytes} bytes)")


if __name__ == "__main__":
    main()
