"""Tagged verification patches: expectations from the patch's own colour space."""

from __future__ import annotations

import unittest

from kelvincal.core.color import delta_e2000, xyz_to_lab
from kelvincal.core.colorspaces import DISPLAY_P3, REC2020_G22, SRGB, rgb8_to_xyz
from kelvincal.core.verification import evaluate, report_html, test_patches, wide_gamut_patches

D65 = (0.31271, 0.32902)
# A D65 panel at 120 cd/m² — exactly the shared white of all registered spaces.
PANEL_WHITE = (0.95047 * 120.0, 120.0, 1.08883 * 120.0)


class TestTaggedVerification(unittest.TestCase):

    def test_default_patch_set_is_unchanged_without_a_tag(self):
        self.assertEqual(len(test_patches()), len(test_patches(None)))
        self.assertEqual(len(test_patches()), len(test_patches(SRGB)))
        self.assertTrue(all(p.space_name == "srgb" for p in test_patches(DISPLAY_P3)[:len(test_patches())]))

    def test_wide_tag_adds_wide_gamut_patches(self):
        base = test_patches()
        tagged = test_patches(DISPLAY_P3)
        self.assertEqual(len(tagged), len(base) + len(wide_gamut_patches(DISPLAY_P3)))
        extra = [p for p in tagged if p.space_name == "display-p3"]
        self.assertTrue(extra)
        for p in extra:
            self.assertEqual(p.space.name, "display-p3")

    def test_wide_patches_are_outside_srgb_for_wide_panels(self):
        """A P3-tagged saturated patch measured on a P3 panel must be graded
        against P3's definition — sRGB expectations would fail it wrongly."""
        patches = [p for p in test_patches(DISPLAY_P3) if p.space_name == "display-p3"]
        measured = [rgb8_to_xyz(DISPLAY_P3, p.rgb) for p in patches]
        # scale to panel white for realism
        scaled = [(x * 120.0, y * 120.0, z * 120.0) for x, y, z in measured]
        result = evaluate(patches, scaled, PANEL_WHITE, (0.0, 0.0, 0.0), D65, "p", "d")
        self.assertEqual(result.content_tag, "display-p3")
        for p in result.patches:
            self.assertLess(p.delta_e, 0.5, f"{p.patch.display_name}: {p.delta_e}")

    def test_evaluate_defaults_to_srgb_tag(self):
        patches = test_patches()
        measured = [rgb8_to_xyz(SRGB, p.rgb) for p in patches]
        scaled = [(x * 120.0, y * 120.0, z * 120.0) for x, y, z in measured]
        result = evaluate(patches, scaled, PANEL_WHITE, (0.0, 0.0, 0.0), D65, "p", "d")
        self.assertEqual(result.content_tag, "srgb")
        self.assertLess(result.mean, 0.5)

    def test_mixed_tags_report_the_non_srgb_tag(self):
        patches = test_patches(REC2020_G22)
        self.assertIn("rec2020", [p.space_name for p in patches])
        measured = [rgb8_to_xyz(p.space, p.rgb) for p in patches]
        scaled = [(x * 120.0, y * 120.0, z * 120.0) for x, y, z in measured]
        result = evaluate(patches, scaled, PANEL_WHITE, (0.0, 0.0, 0.0), D65, "p", "d")
        self.assertEqual(result.content_tag, "rec2020")

    def test_report_html_carries_the_tag(self):
        patches = test_patches(DISPLAY_P3)
        measured = [rgb8_to_xyz(p.space, p.rgb) for p in patches]
        result = evaluate(patches, measured, PANEL_WHITE, (0.0, 0.0, 0.0), D65, "p", "d")
        html = report_html(result)
        self.assertIn("display-p3", html)
        self.assertIn("Tag", html)


if __name__ == "__main__":
    unittest.main()