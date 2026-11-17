"""Content colour spaces: primary derivation, TRCs, registry."""

from __future__ import annotations

import math
import unittest

from kelvincal.core.color import delta_e2000, xyz_to_lab
from kelvincal.core.colorspaces import (
    ADOBE_RGB,
    DISPLAY_P3,
    REC2020_G22,
    SRGB,
    chromaticity_of,
    rgb8_to_xyz,
    space_by_name,
    white_xyz,
)

# The sRGB standard's published matrix constants (IEC 61966-2-1, 4 decimals).
LEGACY_SRGB_MATRIX = (
    (0.4124, 0.3576, 0.1805),
    (0.2126, 0.7152, 0.0722),
    (0.0193, 0.1192, 0.9505),
)
LEGACY_SRGB_WHITE = (0.95047, 1.0, 1.08883)


def legacy_srgb_to_xyz(rgb):
    def lin(v):
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in rgb)
    m = LEGACY_SRGB_MATRIX
    return (m[0][0] * r + m[0][1] * g + m[0][2] * b,
            m[1][0] * r + m[1][1] * g + m[1][2] * b,
            m[2][0] * r + m[2][1] * g + m[2][2] * b)


class TestColorSpaces(unittest.TestCase):

    def test_srgb_matches_published_constants(self):
        """The derived sRGB transform agrees with the published 4-decimal matrix."""
        for rgb in ((0, 0, 0), (255, 255, 255), (128, 128, 128), (1, 2, 3),
                    (255, 0, 0), (0, 255, 0), (0, 0, 255), (115, 82, 68), (231, 199, 31)):
            with self.subTest(rgb=rgb):
                legacy = xyz_to_lab(legacy_srgb_to_xyz(rgb), LEGACY_SRGB_WHITE)
                ours = xyz_to_lab(rgb8_to_xyz(SRGB, rgb), SRGB.white_xyz)
                self.assertLess(delta_e2000(legacy, ours), 0.1)

    def test_srgb_white_is_the_published_d65(self):
        self.assertEqual(SRGB.white_xyz, LEGACY_SRGB_WHITE)
        self.assertEqual(white_xyz(SRGB), LEGACY_SRGB_WHITE)

    def test_primaries_derive_back_to_their_chromaticities(self):
        for space, rgb, xy in (
            (DISPLAY_P3, (255, 0, 0), (0.680, 0.320)),
            (REC2020_G22, (255, 0, 0), (0.7080, 0.2920)),
            (REC2020_G22, (0, 255, 0), (0.1700, 0.7960)),
            (REC2020_G22, (0, 0, 255), (0.1310, 0.0460)),
            (ADOBE_RGB, (0, 255, 0), (0.210, 0.710)),
        ):
            with self.subTest(space=space.name, rgb=rgb):
                got = chromaticity_of(rgb8_to_xyz(space, rgb))
                self.assertAlmostEqual(got[0], xy[0], places=3)
                self.assertAlmostEqual(got[1], xy[1], places=3)

    def test_trc_endpoints_and_midpoints(self):
        for space in (SRGB, DISPLAY_P3, ADOBE_RGB, REC2020_G22):
            with self.subTest(space=space.name):
                self.assertEqual(space.decode(0), 0.0)
                self.assertAlmostEqual(space.decode(255), 1.0, places=9)
                self.assertLess(space.decode(128), 0.5)  # all encodings are sub-linear
        # Adobe RGB's gamma 563/256 sits between sRGB and 2.2
        self.assertAlmostEqual(ADOBE_RGB.decode(128), (128 / 255) ** (563 / 256), places=9)
        self.assertAlmostEqual(REC2020_G22.decode(128), (128 / 255) ** 2.2, places=9)

    def test_wide_space_red_exceeds_srgb_red(self):
        """P3 and Rec.2020 primaries must be more saturated than sRGB's."""
        for space in (DISPLAY_P3, REC2020_G22):
            with self.subTest(space=space.name):
                srgb = xyz_to_lab(rgb8_to_xyz(SRGB, (255, 0, 0)), SRGB.white_xyz)
                wide = xyz_to_lab(rgb8_to_xyz(space, (255, 0, 0)), space.white_xyz)
                self.assertGreater(wide[1], srgb[1] + 10)  # redder in a*b*: P3 ≈ +14, Rec.2020 ≈ +25

    def test_registry(self):
        self.assertIs(space_by_name("display-p3"), DISPLAY_P3)
        self.assertIs(space_by_name("nonsense"), SRGB)   # unknown tags fall back to sRGB
        self.assertIs(space_by_name(""), SRGB)


if __name__ == "__main__":
    unittest.main()