#!/usr/bin/env python3
"""Generate aligned transparent facial overlays from the project-owned coach portrait."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "public" / "coach" / "rock-coach.webp"
OUTPUT_DIR = ROOT / "public" / "coach" / "face"
SCALE = 3

SKIN_DARK = (118, 49, 21, 255)
LIP = (145, 60, 31, 255)
LIP_LIGHT = (224, 120, 75, 255)
MOUTH_DARK = (48, 16, 11, 255)
TEETH = (250, 235, 205, 255)
TONGUE = (183, 74, 61, 255)
BROW = (65, 27, 16, 255)
BROW_LIGHT = (105, 44, 24, 255)
EYE_WHITE = (247, 226, 190, 255)
IRIS = (91, 43, 21, 255)
PUPIL = (20, 14, 10, 255)


def scaled_box(values: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """Scale one drawing rectangle for antialiased rasterization."""
    return tuple(round(value * SCALE) for value in values)  # type: ignore[return-value]


def scaled_points(values: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Scale drawing points for the supersampled canvas."""
    return [(round(x * SCALE), round(y * SCALE)) for x, y in values]


def quadratic_curve(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    steps: int = 32,
) -> list[tuple[float, float]]:
    """Sample a smooth quadratic curve for illustrated lip and eyelid lines."""
    points: list[tuple[float, float]] = []
    for index in range(steps + 1):
        t = index / steps
        inverse = 1 - t
        points.append(
            (
                inverse * inverse * start[0] + 2 * inverse * t * control[0] + t * t * end[0],
                inverse * inverse * start[1] + 2 * inverse * t * control[1] + t * t * end[1],
            )
        )
    return points


def vector_layer(size: tuple[int, int], painter: Callable[[ImageDraw.ImageDraw], None]) -> Image.Image:
    """Draw one layer at higher resolution and downsample it with smooth edges."""
    canvas = Image.new("RGBA", (size[0] * SCALE, size[1] * SCALE), (0, 0, 0, 0))
    painter(ImageDraw.Draw(canvas))
    return canvas.resize(size, Image.Resampling.LANCZOS)


def make_mask(size: tuple[int, int], ellipses: list[tuple[int, int, int, int]]) -> np.ndarray:
    """Build a local repair mask from face-region ellipses."""
    mask = np.zeros((size[1], size[0]), dtype=np.uint8)
    for x0, y0, x1, y1 in ellipses:
        center = ((x0 + x1) // 2, (y0 + y1) // 2)
        axes = (max(1, (x1 - x0) // 2), max(1, (y1 - y0) // 2))
        cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1, cv2.LINE_AA)
    return mask


def polygon_mask(size: tuple[int, int], polygons: list[list[tuple[int, int]]]) -> np.ndarray:
    """Build a precise repair mask that follows existing illustrated features."""
    mask = np.zeros((size[1], size[0]), dtype=np.uint8)
    for polygon in polygons:
        cv2.fillPoly(mask, [np.asarray(polygon, dtype=np.int32)], 255, cv2.LINE_AA)
    return mask


def repaired_plate(base: Image.Image, mask: np.ndarray, radius: float = 9) -> Image.Image:
    """Replace existing facial marks with nearby skin while feathering the patch edge."""
    rgb = np.asarray(base.convert("RGB"))
    repaired = cv2.inpaint(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, radius, cv2.INPAINT_TELEA)
    repaired_rgb = cv2.cvtColor(repaired, cv2.COLOR_BGR2RGB)
    alpha = Image.fromarray(mask, mode="L").filter(ImageFilter.GaussianBlur(radius=2.4))
    plate = Image.fromarray(repaired_rgb, mode="RGB").convert("RGBA")
    plate.putalpha(alpha)
    return plate


def original_plate(base: Image.Image, mask: np.ndarray) -> Image.Image:
    """Copy original pixels with a feathered alpha edge for visually unchanged rest layers."""
    plate = base.copy()
    alpha = Image.fromarray(mask, mode="L").filter(ImageFilter.GaussianBlur(radius=1.6))
    plate.putalpha(alpha)
    return plate


def moved_feature(base: Image.Image, mask: np.ndarray, dx: int, dy: int, angle: float) -> Image.Image:
    """Move one original illustrated feature while retaining its texture and shading."""
    feature = original_plate(base, mask)
    bbox = feature.getchannel("A").getbbox()
    if bbox is None:
        return Image.new("RGBA", base.size, (0, 0, 0, 0))
    crop = feature.crop(bbox).rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    source_center = ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
    destination = (
        source_center[0] + dx - crop.width // 2,
        source_center[1] + dy - crop.height // 2,
    )
    layer.alpha_composite(crop, destination)
    return layer


def draw_mouth_shape(viseme: str) -> Image.Image:
    """Draw one restrained cartoon viseme in the portrait's original perspective."""
    local_size = (180, 100)

    def paint(draw: ImageDraw.ImageDraw) -> None:
        line_width = 4 * SCALE
        highlight_width = 2 * SCALE
        if viseme == "X":
            upper = quadratic_curve((38, 43), (88, 61), (143, 49))
            lower = quadratic_curve((40, 45), (91, 73), (141, 51))
            draw.line(scaled_points(upper), fill=SKIN_DARK, width=line_width)
            draw.line(scaled_points(lower), fill=LIP, width=3 * SCALE)
            draw.line(scaled_points(quadratic_curve((70, 56), (104, 63), (130, 53))), fill=LIP_LIGHT, width=highlight_width)
        elif viseme == "A":
            draw.line(scaled_points(quadratic_curve((48, 46), (90, 55), (134, 48))), fill=SKIN_DARK, width=5 * SCALE)
            draw.line(scaled_points(quadratic_curve((52, 49), (90, 58), (130, 51))), fill=LIP, width=3 * SCALE)
        elif viseme == "B":
            draw.ellipse(scaled_box((43, 38, 139, 68)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((48, 43, 134, 64)), fill=MOUTH_DARK)
            draw.pieslice(scaled_box((51, 41, 132, 64)), start=180, end=360, fill=TEETH)
            draw.line(scaled_points(quadratic_curve((53, 58), (91, 64), (130, 59))), fill=LIP, width=3 * SCALE)
        elif viseme == "C":
            draw.ellipse(scaled_box((43, 34, 140, 72)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((48, 39, 135, 69)), fill=MOUTH_DARK)
            draw.pieslice(scaled_box((52, 43, 132, 70)), start=192, end=348, fill=TEETH)
            draw.line(scaled_points(quadratic_curve((57, 64), (91, 73), (127, 65))), fill=TONGUE, width=5 * SCALE)
        elif viseme == "D":
            draw.ellipse(scaled_box((38, 27, 144, 80)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((44, 33, 138, 76)), fill=MOUTH_DARK)
            draw.pieslice(scaled_box((48, 35, 135, 65)), start=185, end=355, fill=TEETH)
            draw.pieslice(scaled_box((55, 54, 129, 80)), start=182, end=358, fill=TONGUE)
            draw.line(scaled_points(quadratic_curve((48, 35), (91, 22), (135, 38))), fill=LIP, width=4 * SCALE)
        elif viseme == "E":
            draw.ellipse(scaled_box((65, 27, 118, 77)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((72, 34, 111, 71)), fill=MOUTH_DARK)
            draw.arc(scaled_box((68, 30, 115, 75)), start=205, end=335, fill=LIP_LIGHT, width=3 * SCALE)
        elif viseme == "F":
            draw.ellipse(scaled_box((67, 34, 116, 69)), fill=LIP)
            draw.ellipse(scaled_box((78, 42, 106, 61)), fill=MOUTH_DARK)
            draw.arc(scaled_box((68, 34, 115, 68)), start=185, end=342, fill=LIP_LIGHT, width=3 * SCALE)
        elif viseme == "G":
            draw.rounded_rectangle(scaled_box((45, 35, 137, 70)), radius=14 * SCALE, fill=SKIN_DARK)
            draw.rounded_rectangle(scaled_box((51, 40, 131, 65)), radius=10 * SCALE, fill=MOUTH_DARK)
            draw.pieslice(scaled_box((52, 38, 130, 64)), start=180, end=360, fill=TEETH)
            draw.line(scaled_points(quadratic_curve((56, 58), (91, 67), (127, 59))), fill=LIP, width=4 * SCALE)
        elif viseme == "H":
            draw.ellipse(scaled_box((48, 32, 136, 74)), fill=SKIN_DARK)
            draw.ellipse(scaled_box((54, 38, 130, 70)), fill=MOUTH_DARK)
            draw.ellipse(scaled_box((66, 51, 121, 72)), fill=TONGUE)
            draw.line(scaled_points(quadratic_curve((68, 58), (94, 53), (119, 60))), fill=(225, 118, 101, 255), width=2 * SCALE)

    local = vector_layer(local_size, paint)
    tilted = local.rotate(-5, resample=Image.Resampling.BICUBIC, expand=False)
    layer = Image.new("RGBA", (1254, 1254), (0, 0, 0, 0))
    layer.alpha_composite(tilted, (526, 234))
    return layer


LEFT_EYE = [(571, 169), (584, 157), (603, 157), (619, 171), (614, 186), (592, 188), (576, 180)]
RIGHT_EYE = [(676, 185), (689, 178), (708, 184), (722, 197), (714, 207), (695, 205), (681, 199)]


def draw_eye_mask(size: tuple[int, int]) -> Image.Image:
    """Create the eye-white alpha mask that constrains moving pupils."""
    def paint(draw: ImageDraw.ImageDraw) -> None:
        draw.polygon(scaled_points(LEFT_EYE), fill=(255, 255, 255, 255))
        draw.polygon(scaled_points(RIGHT_EYE), fill=(255, 255, 255, 255))

    return vector_layer(size, paint)


def draw_pupils(size: tuple[int, int]) -> Image.Image:
    """Draw independently movable irises, pupils, and catchlights."""
    def paint(draw: ImageDraw.ImageDraw) -> None:
        for cx, cy, width, height in ((599, 173, 9, 13), (697, 193, 8, 12)):
            draw.ellipse(scaled_box((cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)), fill=IRIS)
            draw.ellipse(scaled_box((cx - 2.5, cy - 4, cx + 2.5, cy + 4)), fill=PUPIL)
            draw.ellipse(scaled_box((cx - 1.5, cy - 4, cx + 0.5, cy - 2)), fill=(255, 246, 220, 230))

    return vector_layer(size, paint)


def draw_closed_eyes(size: tuple[int, int], squint: bool) -> Image.Image:
    """Draw either fully closed lids or a brief expressive squint."""
    def paint(draw: ImageDraw.ImageDraw) -> None:
        if squint:
            for points in (LEFT_EYE, RIGHT_EYE):
                draw.polygon(scaled_points(points), fill=(205, 104, 50, 255))
            draw.line(scaled_points(quadratic_curve((574, 175), (595, 164), (616, 177))), fill=SKIN_DARK, width=4 * SCALE)
            draw.line(scaled_points(quadratic_curve((680, 193), (701, 184), (718, 199))), fill=SKIN_DARK, width=4 * SCALE)
        else:
            draw.line(scaled_points(quadratic_curve((573, 174), (594, 188), (616, 177))), fill=SKIN_DARK, width=5 * SCALE)
            draw.line(scaled_points(quadratic_curve((679, 192), (700, 207), (718, 198))), fill=SKIN_DARK, width=5 * SCALE)
            draw.line(scaled_points(quadratic_curve((578, 177), (594, 184), (612, 179))), fill=(228, 127, 68, 255), width=2 * SCALE)
            draw.line(scaled_points(quadratic_curve((684, 195), (700, 202), (714, 199))), fill=(228, 127, 68, 255), width=2 * SCALE)

    return vector_layer(size, paint)


def save_layer(layer: Image.Image, path: Path) -> None:
    """Save one full-canvas RGBA layer as compact lossless WebP."""
    layer.save(path, "WEBP", lossless=True, method=6)


def validate_assets(paths: list[Path], size: tuple[int, int]) -> dict[str, object]:
    """Verify dimensions, alpha coverage, face bounds, and total resource budget."""
    total_bytes = 0
    records: list[dict[str, object]] = []
    for path in paths:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            bbox = alpha.getbbox()
            if rgba.size != size or bbox is None or alpha.getextrema()[0] != 0:
                raise RuntimeError(f"Invalid transparent layer: {path.name}")
            if bbox[0] < 480 or bbox[1] < 70 or bbox[2] > 770 or bbox[3] > 370:
                raise RuntimeError(f"Layer escaped the face region: {path.name} {bbox}")
        file_bytes = path.stat().st_size
        total_bytes += file_bytes
        records.append({"file": path.name, "width": size[0], "height": size[1], "alpha_bbox": bbox, "bytes": file_bytes})
    if total_bytes >= 1_500_000:
        raise RuntimeError(f"Facial assets exceed budget: {total_bytes} bytes")
    return {"canvas": list(size), "format": "lossless-webp-rgba", "total_bytes": total_bytes, "assets": records}


def main() -> None:
    """Generate every mouth, eye, pupil, blink, squint, and brow layer."""
    base = Image.open(SOURCE_PATH).convert("RGBA")
    size = base.size
    if size != (1254, 1254):
        raise RuntimeError(f"Unexpected coach canvas: {size}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mouth_polygon = [[
        (548, 272), (566, 258), (598, 263), (625, 267), (658, 270),
        (684, 284), (676, 302), (648, 316), (611, 318), (578, 308), (555, 294),
    ]]
    mouth_mask = polygon_mask(size, mouth_polygon)
    mouth_plate = repaired_plate(base, mouth_mask, radius=4)
    resting_mouth = original_plate(base, mouth_mask)
    output_paths: list[Path] = []
    for viseme in "ABCDEFGHX":
        layer = resting_mouth if viseme == "X" else Image.alpha_composite(mouth_plate, draw_mouth_shape(viseme))
        path = OUTPUT_DIR / f"mouth-{viseme}.webp"
        save_layer(layer, path)
        output_paths.append(path)

    pupil_repair_mask = make_mask(size, [(591, 164, 607, 183), (689, 184, 705, 202)])
    neutral_eyes = repaired_plate(base, pupil_repair_mask, radius=3)
    closed_eye_mask = make_mask(size, [(562, 148, 628, 194), (668, 171, 730, 216)])
    closed_eye_plate = repaired_plate(base, closed_eye_mask, radius=6)
    eye_layers = {
        "eyes-neutral.webp": neutral_eyes,
        "eyes-mask.webp": draw_eye_mask(size),
        "pupils.webp": draw_pupils(size),
        "eyes-blink.webp": Image.alpha_composite(closed_eye_plate, draw_closed_eyes(size, squint=False)),
        "eyes-squint.webp": Image.alpha_composite(closed_eye_plate, draw_closed_eyes(size, squint=True)),
    }
    for filename, layer in eye_layers.items():
        path = OUTPUT_DIR / filename
        save_layer(layer, path)
        output_paths.append(path)

    left_brow_polygon = [[(558, 123), (587, 98), (614, 105), (651, 130), (647, 147), (631, 146), (594, 120), (570, 143)]]
    right_brow_polygon = [[(672, 151), (686, 142), (708, 150), (742, 169), (739, 185), (724, 184), (697, 167), (679, 172)]]
    left_brow_mask = polygon_mask(size, left_brow_polygon)
    right_brow_mask = polygon_mask(size, right_brow_polygon)
    brow_mask = np.maximum(left_brow_mask, right_brow_mask)
    brow_plate = repaired_plate(base, brow_mask, radius=4)
    brow_poses = {
        "brow-thinking.webp": ((0, -10, -2.5), (0, 2, 1.0)),
        "brow-emphasis.webp": ((0, -8, -1.5), (0, -7, 1.5)),
    }
    for filename, (left_pose, right_pose) in brow_poses.items():
        layer = brow_plate.copy()
        layer = Image.alpha_composite(layer, moved_feature(base, left_brow_mask, *left_pose))
        layer = Image.alpha_composite(layer, moved_feature(base, right_brow_mask, *right_pose))
        path = OUTPUT_DIR / filename
        save_layer(layer, path)
        output_paths.append(path)

    manifest = validate_assets(output_paths, size)
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"Generated {len(output_paths)} aligned face layers ({manifest['total_bytes']} bytes)")


if __name__ == "__main__":
    main()
