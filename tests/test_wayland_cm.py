"""wp_color_manager_v1 client: declaration plans, capabilities, encodings.

No compositor needed: capability answers are fixtures recorded from the live
KWin 6.8.2 session (kelvin-log 2026-11-16), pinning the matching logic against
real compositor behaviour.
"""

from __future__ import annotations

import unittest

from kelvincal.core.colorspaces import ADOBE_RGB, DISPLAY_P3, REC2020_G22, SRGB
from kelvincal.core.verification import test_patches
from kelvincal.wayland_cm.display import buffer_stride, rgb_to_xrgb8888
from kelvincal.wayland_cm.tags import (
    FEATURE_PARAMETRIC,
    FEATURE_SET_TF_POWER,
    PRIMARIES_ADOBE_RGB,
    PRIMARIES_BT2020,
    PRIMARIES_DISPLAY_P3,
    PRIMARIES_SRGB,
    TF_GAMMA22,
    TF_SRGB,
    plan_for,
)
from kelvincal.wayland_cm.cm import Capabilities, DescriptionInfo

# Recorded live from KWin 6.8.2 (2026-11-16): what the compositor's
# wp_color_manager_v1 actually listed. No sRGB TF, no set_tf_power.
KWIN_6_8_CAPS = Capabilities(
    features={1, 2, 4, 5, 6, 7},
    primaries={1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
    transfer_functions={1, 2, 5, 11, 13},
    intents={0, 1, 3, 4},
    done=True,
)


class TestDeclarationPlans(unittest.TestCase):

    def test_protocol_values(self):
        self.assertEqual((plan_for(SRGB).primaries_named, plan_for(SRGB).tf_named),
                         (PRIMARIES_SRGB, TF_SRGB))
        self.assertEqual((plan_for(DISPLAY_P3).primaries_named, plan_for(DISPLAY_P3).tf_named),
                         (PRIMARIES_DISPLAY_P3, TF_SRGB))
        self.assertEqual((plan_for(REC2020_G22).primaries_named, plan_for(REC2020_G22).tf_named),
                         (PRIMARIES_BT2020, TF_GAMMA22))
        adobe = plan_for(ADOBE_RGB)
        self.assertEqual(adobe.primaries_named, PRIMARIES_ADOBE_RGB)
        self.assertIsNone(adobe.tf_named)
        self.assertAlmostEqual(adobe.tf_power, 563 / 256, places=9)

    def test_plan_requests(self):
        self.assertEqual(plan_for(REC2020_G22).requests(),
                         [("set_primaries_named", PRIMARIES_BT2020), ("set_tf_named", TF_GAMMA22)])
        self.assertEqual(plan_for(ADOBE_RGB).requests()[-1], ("set_tf_power", 563 / 256))

    def test_plans_match_the_colour_space_definitions(self):
        """The declared TRC must be the same encoding core.colorspaces grades against."""
        for space in (SRGB, DISPLAY_P3, REC2020_G22):
            self.assertEqual(plan_for(space).space.trc, space.trc)
        # Adobe RGB's pure power is declared as exactly the space's gamma
        self.assertAlmostEqual(plan_for(ADOBE_RGB).tf_power, 563 / 256, places=9)
        self.assertEqual(ADOBE_RGB.trc, "adobe-rgb")


class TestCapabilitiesAgainstKwin68(unittest.TestCase):
    """The live KWin 6.8.2 answers: only gamma22 spaces are declarable."""

    def test_rec2020_is_declarable(self):
        self.assertEqual(KWIN_6_8_CAPS.declareable(plan_for(REC2020_G22)), [])

    def test_srgb_and_p3_are_refused_by_missing_named_tf(self):
        for space in (SRGB, DISPLAY_P3):
            problems = KWIN_6_8_CAPS.declareable(plan_for(space))
            self.assertIn("named transfer function 9", problems, space.name)

    def test_adobe_is_refused_by_missing_set_tf_power(self):
        problems = KWIN_6_8_CAPS.declareable(plan_for(ADOBE_RGB))
        self.assertIn("feature 3", problems)
        self.assertTrue(any("transfer function" in p or "feature" in p for p in problems))

    def test_full_compositor_ignores_feature_gaps(self):
        caps = Capabilities(features={FEATURE_PARAMETRIC, FEATURE_SET_TF_POWER},
                            primaries={PRIMARIES_ADOBE_RGB}, transfer_functions={TF_SRGB})
        self.assertEqual(caps.declareable(plan_for(ADOBE_RGB)), [])


class TestEncodings(unittest.TestCase):

    def test_xrgb8888_pixel(self):
        # XRGB8888: R in bits 23:16 — a red fill must not come out blue
        self.assertEqual(rgb_to_xrgb8888((255, 0, 0)), 0x00FF0000)
        self.assertEqual(rgb_to_xrgb8888((0, 255, 0)), 0x0000FF00)
        self.assertEqual(rgb_to_xrgb8888((0, 0, 255)), 0x000000FF)
        self.assertEqual(rgb_to_xrgb8888((255, 255, 255)), 0x00FFFFFF)

    def test_stride_is_four_byte_aligned(self):
        self.assertEqual(buffer_stride(1920), 7680)
        self.assertEqual(buffer_stride(1), 4)


class TestDescriptionInfo(unittest.TestCase):

    def test_primaries_str_decodes_protocol_units(self):
        # recorded shape: values scaled by 1e6 (D65 white 0.31271, 0.32902)
        info = DescriptionInfo(primaries_xy=(700000, 300000, 200000, 700000,
                                             150000, 60000, 312710, 329020))
        text = info.primaries_str()
        self.assertIn("white 0.3127,0.3290", text)
        self.assertIn("R 0.7000,0.3000", text)

    def test_unnamed_primaries_fall_back(self):
        self.assertEqual(DescriptionInfo().named_primaries(), "unnamed (custom chromaticities)")
        self.assertEqual(DescriptionInfo(primaries_named=6).named_primaries(), "bt2020")


class TestVerifyTaggedPatchSet(unittest.TestCase):

    def test_patches_come_from_the_tagged_set(self):
        # the driver measures test_patches(space); the plan's space must match
        for space in (REC2020_G22, DISPLAY_P3):
            patches = test_patches(space)
            self.assertTrue(any(p.space_name == space.name for p in patches))
            self.assertEqual(len(patches), len(test_patches()) + 12 + 10)  # corner + gray extras


if __name__ == "__main__":
    unittest.main()