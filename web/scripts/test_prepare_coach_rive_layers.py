"""Verify full-canvas Rive layers preserve the original coach and shared coordinates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

from scripts.prepare_coach_rive_layers import BODY_LAYER_NAMES, prepare_layers


WEB_ROOT = Path(__file__).resolve().parents[1]


class PrepareCoachRiveLayersTest(unittest.TestCase):
    """Exercise deterministic body partitioning and facial layer placement."""

    def test_body_layers_recompose_to_the_original_character(self) -> None:
        """Require disjoint body layers to reproduce the source image exactly."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            prepare_layers(
                WEB_ROOT / "public" / "coach" / "coach-original.webp",
                WEB_ROOT / "public" / "coach" / "layers" / "face",
                output,
            )

            expected = Image.open(
                WEB_ROOT / "public" / "coach" / "coach-original.webp"
            ).convert("RGBA")
            recomposed = Image.new("RGBA", expected.size)
            for name in BODY_LAYER_NAMES:
                layer = Image.open(output / "body" / f"{name}.png").convert("RGBA")
                self.assertEqual(layer.size, expected.size)
                recomposed.alpha_composite(layer)
            recomposed.alpha_composite(Image.open(output / "face" / "jaw.png").convert("RGBA"))

            self.assertIsNone(ImageChops.difference(expected, recomposed).getbbox())

    def test_face_layers_share_the_full_canvas_coordinate_system(self) -> None:
        """Require every facial expression layer to be non-empty and full-canvas."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            prepare_layers(
                WEB_ROOT / "public" / "coach" / "coach-original.webp",
                WEB_ROOT / "public" / "coach" / "layers" / "face",
                output,
            )

            face_layers = sorted((output / "face").glob("*.png"))
            self.assertEqual(len(face_layers), 17)
            for path in face_layers:
                image = Image.open(path).convert("RGBA")
                self.assertEqual(image.size, (1254, 1254))
                self.assertIsNotNone(image.getchannel("A").getbbox())
                self.assertEqual(image.getpixel((0, 0))[3], 0)


if __name__ == "__main__":
    unittest.main()
