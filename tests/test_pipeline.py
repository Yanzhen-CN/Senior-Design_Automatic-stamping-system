from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stamping_system.calibration import build_homography, relative_to_pixel_on_quad
from stamping_system.config import load_config, save_config
from stamping_system.gcode import build_jog_gcode
from stamping_system.mode_a import paper_feed_lines, xy_zero_lines
from stamping_system.pipeline import preview_target
from stamping_system.targeting import TargetInput


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(ROOT / "config" / "machine.toml")

    def test_homography_maps_calibration_points(self) -> None:
        homography = build_homography(self.config.calibration.points)
        for point in self.config.calibration.points:
            actual = homography.transform(point.pixel)
            self.assertAlmostEqual(actual[0], point.real_mm[0], places=3)
            self.assertAlmostEqual(actual[1], point.real_mm[1], places=3)

    def test_preset_preview_builds_stamp_gcode(self) -> None:
        result = preview_target(
            TargetInput(source="paper_preset", preset="bottom_right_stamp"),
            self.config,
        )
        self.assertTrue(any(line.startswith("G0 X") for line in result.gcode))
        self.assertTrue(any(line.startswith("G1 Z") for line in result.gcode))

    def test_relative_target_can_use_detected_quad(self) -> None:
        quad = [(100.0, 100.0), (500.0, 100.0), (500.0, 700.0), (100.0, 700.0)]
        pixel = relative_to_pixel_on_quad(0.5, 0.5, quad)
        self.assertAlmostEqual(pixel[0], 300.0, places=3)
        self.assertAlmostEqual(pixel[1], 400.0, places=3)

    def test_jog_uses_axis_scale(self) -> None:
        raw = copy.deepcopy(self.config.raw)
        raw["machine"]["axes"]["x"]["actual_mm_per_commanded_mm"] = 0.5
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "machine.toml"
            cfg = save_config(raw, path)
            plan = build_jog_gcode("x", 10.0, cfg)
        self.assertIn("X20", plan.lines[2])

    def test_save_config_round_trip(self) -> None:
        raw = copy.deepcopy(self.config.raw)
        raw["camera"]["height_mm"] = 355.5
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "machine.toml"
            saved = save_config(raw, path)
            loaded = load_config(path)
        self.assertEqual(saved.camera.height_mm, 355.5)
        self.assertEqual(loaded.camera.height_mm, 355.5)

    def test_mode_a_zero_lines_include_xy_zero(self) -> None:
        lines = xy_zero_lines(self.config)
        self.assertEqual(lines[0], "G21")
        self.assertEqual(lines[1], "G90")
        self.assertTrue(lines[2].startswith("G0 X0 Y0 F"))

    def test_mode_a_feed_lines_repeat(self) -> None:
        lines = paper_feed_lines(self.config, "forward", 3)
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(line == self.config.paper_feed.command for line in lines))


if __name__ == "__main__":
    unittest.main()
