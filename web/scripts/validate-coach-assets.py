"""Validate generated coach sources and the aligned 2D runtime sprites."""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
COACH_DIR = ROOT / "public" / "coach"
MAX_RUNTIME_FACE_BYTES = 1_500_000
MAX_V2_RUNTIME_BYTES = 2_000_000
MAX_MOUTH_AXIS_DEVIATION = 5.0
MOUTH_AXIS_CROP = (525, 325, 680, 395)
DIRECTIONAL_MOUTH_ROLES = (
    "mouth-A",
    "mouth-B",
    "mouth-C",
    "mouth-D",
    "mouth-G",
    "mouth-H",
)

BODY_NAMES = {
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
}

FACE_NAMES = {
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
}

RUNTIME_FACE_NAMES = {
    "mouth-X",
    "mouth-A",
    "mouth-B",
    "mouth-C",
    "mouth-D",
    "mouth-E",
    "mouth-F",
    "mouth-G",
    "mouth-H",
    "eyes-neutral",
    "eyes-mask",
    "pupils",
    "eyes-blink",
    "eyes-squint",
    "brow-thinking",
    "brow-emphasis",
}

V2_ROLE_FILES = {
    "body": "coach-base.webp",
    "mouth-A": "face/mouth-A.webp",
    "mouth-B": "face/mouth-B.webp",
    "mouth-C": "face/mouth-C.webp",
    "mouth-D": "face/mouth-D.webp",
    "mouth-E": "face/mouth-E.webp",
    "mouth-F": "face/mouth-F.webp",
    "mouth-G": "face/mouth-G.webp",
    "mouth-H": "face/mouth-H.webp",
    "mouth-X": "face/mouth-X.webp",
    "eyes-blink": "face/eyes-blink.webp",
    "brow-thinking": "face/brow-thinking.webp",
}


def validate_alpha_image(
    path: Path,
    expected_size: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Check dimensions, occupied alpha, and transparent image corners."""
    if not path.exists():
        raise AssertionError(f"Missing coach asset: {path}")
    image = Image.open(path).convert("RGBA")
    if expected_size and image.size != expected_size:
        raise AssertionError(f"Unexpected size for {path.name}: {image.size} != {expected_size}")
    alpha = image.getchannel("A")
    if alpha.getbbox() is None:
        raise AssertionError(f"Empty alpha channel: {path}")
    corners = (
        alpha.getpixel((0, 0)),
        alpha.getpixel((image.width - 1, 0)),
        alpha.getpixel((0, image.height - 1)),
        alpha.getpixel((image.width - 1, image.height - 1)),
    )
    if max(corners) > 20:
        raise AssertionError(f"Opaque corner in {path.name}: {corners}")
    return image.size


def estimate_mouth_axis_degrees(path: Path) -> float:
    """Estimate the visual lip axis from dark pixels inside the fixed mouth crop."""
    image = Image.open(path).convert("RGBA")
    left, top, right, bottom = MOUTH_AXIS_CROP
    points: list[tuple[float, float]] = []
    for y in range(top, bottom):
        for x in range(left, right):
            red, green, blue, alpha = image.getpixel((x, y))
            if alpha > 128 and red < 115 and green < 70 and blue < 60:
                points.append((float(x), float(y)))

    if len(points) < 100:
        raise AssertionError(f"Not enough mouth pixels to estimate axis: {path.name}")

    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    covariance_xx = sum((x - mean_x) ** 2 for x, _ in points)
    covariance_yy = sum((y - mean_y) ** 2 for _, y in points)
    covariance_xy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    image_axis = 0.5 * math.atan2(2 * covariance_xy, covariance_xx - covariance_yy)
    return -math.degrees(image_axis)


def validate_layer_group(folder: Path, expected_names: set[str], fixed_size: bool) -> None:
    """Validate a complete named layer group and its generated manifest."""
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        raise AssertionError(f"Missing layer manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = {layer["name"] for layer in manifest.get("layers", [])}
    if names != expected_names:
        raise AssertionError(f"Layer names differ in {folder}: {sorted(names ^ expected_names)}")

    sizes = {
        validate_alpha_image(folder / f"{name}.png")
        for name in expected_names
    }
    if fixed_size and len(sizes) != 1:
        raise AssertionError(f"Facial layers must share one coordinate size: {sorted(sizes)}")


def validate_runtime_face_layers(folder: Path) -> None:
    """Check the aligned WebP face sprites and their combined transfer budget."""
    total_bytes = 0
    for name in RUNTIME_FACE_NAMES:
        path = folder / f"{name}.webp"
        validate_alpha_image(path, (1254, 1254))
        total_bytes += path.stat().st_size
    if total_bytes > MAX_RUNTIME_FACE_BYTES:
        raise AssertionError(f"Runtime face sprites exceed budget: {total_bytes} bytes")


def validate_v2_bundle(folder: Path) -> None:
    """Validate the versioned comic coach manifest against its real image files."""
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        raise AssertionError(f"Missing coach v2 manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("canvas") != [1254, 1254]:
        raise AssertionError(f"Unexpected coach v2 canvas: {manifest.get('canvas')}")
    if manifest.get("format") != "lossless-webp-rgba":
        raise AssertionError(f"Unexpected coach v2 format: {manifest.get('format')}")

    assets = manifest.get("assets", [])
    assets_by_role = {asset.get("role"): asset for asset in assets}
    if set(assets_by_role) != set(V2_ROLE_FILES):
        raise AssertionError(
            f"Coach v2 roles differ: {sorted(set(assets_by_role) ^ set(V2_ROLE_FILES))}"
        )

    total_bytes = 0
    for role, expected_file in V2_ROLE_FILES.items():
        asset = assets_by_role[role]
        if asset.get("file") != expected_file:
            raise AssertionError(f"Unexpected file for {role}: {asset.get('file')}")
        path = folder / expected_file
        validate_alpha_image(path, (1254, 1254))
        image = Image.open(path).convert("RGBA")
        bbox = image.getchannel("A").getbbox()
        size_bytes = path.stat().st_size
        if asset.get("alpha_bbox") != list(bbox or ()):
            raise AssertionError(f"Alpha bounds differ for {role}")
        if asset.get("width") != image.width or asset.get("height") != image.height:
            raise AssertionError(f"Manifest dimensions differ for {role}")
        if asset.get("bytes") != size_bytes:
            raise AssertionError(f"Manifest byte count differs for {role}")
        total_bytes += size_bytes

    if manifest.get("total_bytes") != total_bytes:
        raise AssertionError("Coach v2 total byte count differs from its files")
    if total_bytes > MAX_V2_RUNTIME_BYTES:
        raise AssertionError(f"Coach v2 runtime bundle exceeds budget: {total_bytes} bytes")

    neutral_angle = estimate_mouth_axis_degrees(folder / V2_ROLE_FILES["mouth-X"])
    for role in DIRECTIONAL_MOUTH_ROLES:
        mouth_angle = estimate_mouth_axis_degrees(folder / V2_ROLE_FILES[role])
        deviation = abs(mouth_angle - neutral_angle)
        if deviation > MAX_MOUTH_AXIS_DEVIATION:
            raise AssertionError(
                f"{role} axis {mouth_angle:.2f} differs from neutral "
                f"{neutral_angle:.2f} by {deviation:.2f} degrees"
            )


def main() -> None:
    """Run every project-owned coach asset validation."""
    validate_alpha_image(COACH_DIR / "coach-original.webp", (1254, 1254))
    validate_alpha_image(COACH_DIR / "rock-coach.webp", (1254, 1254))
    validate_layer_group(COACH_DIR / "layers" / "body", BODY_NAMES, fixed_size=False)
    validate_layer_group(COACH_DIR / "layers" / "face", FACE_NAMES, fixed_size=True)
    validate_runtime_face_layers(COACH_DIR / "face")
    validate_v2_bundle(COACH_DIR / "v2")


if __name__ == "__main__":
    main()
