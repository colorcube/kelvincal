"""Content colour spaces for tagged verification patches.

A verification expectation must come from whatever the content is *tagged as*,
not from a hardcoded sRGB: wide-gamut panels display far outside sRGB, and once
patch surfaces can declare their colour space to the compositor, test patches
must be encoded *and expected* in that space. Each space defines its own
primaries, white point and transfer function; the RGB→XYZ transform is derived
from the primaries and white (IEC 61966-2-1 style), not copied from a
neighbouring space.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from kelvincal.core.i18n import QT_TRANSLATE_NOOP


def _xy_to_xyz(xy: tuple[float, float]) -> tuple[float, float, float]:
    x, y = xy
    return x / y, 1.0, (1.0 - x - y) / y


def _primaries_to_matrix(
    red: tuple[float, float],
    green: tuple[float, float],
    blue: tuple[float, float],
    white: tuple[float, float],
) -> tuple[tuple[float, float, float], ...]:
    """RGB→XYZ matrix (Y_white = 1) from xy chromaticities."""
    cols = [_xy_to_xyz(c) for c in (red, green, blue)]
    white_xyz = _xy_to_xyz(white)
    # X_white = sR·Xr + sG·Xg + sB·Xb (and likewise Y, Z); solve for (sR, sG, sB).
    matrix_rows = [
        [cols[j][i] for j in range(3)] + [white_xyz[i]] for i in range(3)
    ]
    # Gaussian elimination on the 3x3 system [Xr Xg Xb | Xw] etc.
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(matrix_rows[r][col]))
        matrix_rows[col], matrix_rows[pivot] = matrix_rows[pivot], matrix_rows[col]
        pivot_val = matrix_rows[col][col]
        for r in range(3):
            if r == col or pivot_val == 0:
                continue
            factor = matrix_rows[r][col] / pivot_val
            for c in range(col, 4):
                matrix_rows[r][c] -= factor * matrix_rows[col][c]
    scale = [matrix_rows[i][3] / matrix_rows[i][i] if matrix_rows[i][i] else 0.0
             for i in range(3)]
    scaled = [[scale[j] * cols[j][i] for j in range(3)] for i in range(3)]
    return tuple(tuple(row) for row in scaled)  # type: ignore[return-value]


@dataclass(frozen=True)
class ColorSpace:
    """A tagged content colour space: chromaticities + transfer function."""

    name: str                                     # registry key, e.g. "display-p3"
    label: str                                    # human-readable label
    red_xy: tuple[float, float]
    green_xy: tuple[float, float]
    blue_xy: tuple[float, float]
    white_xy: tuple[float, float]
    trc: str                                      # "srgb" | "adobe-rgb" | "gamma22"
    white_xyz_override: tuple[float, float, float] | None = None  # published white beats xy-derived

    @property
    def white_xyz(self) -> tuple[float, float, float]:
        """The space's reference white as XYZ with Y = 1."""
        return self.white_xyz_override if self.white_xyz_override else _xy_to_xyz(self.white_xy)

    @property
    def matrix(self) -> tuple[tuple[float, float, float], ...]:
        return _primaries_to_matrix(self.red_xy, self.green_xy, self.blue_xy, self.white_xy)

    def decode(self, v8: int) -> float:
        """8-bit code value → linear-light factor (the space's own TRC)."""
        c = v8 / 255.0
        if self.trc == "srgb":
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        if self.trc == "adobe-rgb":
            return c ** (563 / 256)
        if self.trc == "gamma22":
            return c ** 2.2
        raise ValueError(f"unknown TRC {self.trc!r} in colour space {self.name!r}")


D65_XY = (0.31271, 0.32902)
# Published D65 white (the IEC sRGB reference white); beats the xy-derived value.
D65_XYZ = (0.95047, 1.0, 1.08883)

SRGB = ColorSpace(
    name="srgb",
    label=QT_TRANSLATE_NOOP("ColorSpaces", "sRGB (IEC 61966-2-1)"),
    red_xy=(0.640, 0.330), green_xy=(0.300, 0.600), blue_xy=(0.150, 0.060),
    white_xy=D65_XY, trc="srgb", white_xyz_override=D65_XYZ,
)
DISPLAY_P3 = ColorSpace(
    name="display-p3",
    label=QT_TRANSLATE_NOOP("ColorSpaces", "Display P3"),
    red_xy=(0.680, 0.320), green_xy=(0.265, 0.690), blue_xy=(0.150, 0.060),
    white_xy=D65_XY, trc="srgb", white_xyz_override=D65_XYZ,
)
ADOBE_RGB = ColorSpace(
    name="adobe-rgb",
    label=QT_TRANSLATE_NOOP("ColorSpaces", "Adobe RGB (1998)"),
    red_xy=(0.640, 0.330), green_xy=(0.210, 0.710), blue_xy=(0.150, 0.060),
    white_xy=D65_XY, trc="adobe-rgb", white_xyz_override=D65_XYZ,
)
# Rec.2020 primaries with a plain 2.2 power TRC: the common tagging convention
# (and what wp_color_manager_v1's bt2020 primaries + set_tf_power encode).
# Explicitly *not* the BT.2020 camera OETF.
REC2020_G22 = ColorSpace(
    name="rec2020",
    label=QT_TRANSLATE_NOOP("ColorSpaces", "Rec.2020 (gamma 2.2)"),
    red_xy=(0.7080, 0.2920), green_xy=(0.1700, 0.7960), blue_xy=(0.1310, 0.0460),
    white_xy=D65_XY, trc="gamma22", white_xyz_override=D65_XYZ,
)

SPACES: dict[str, ColorSpace] = {s.name: s for s in (SRGB, DISPLAY_P3, ADOBE_RGB, REC2020_G22)}


def space_by_name(name: str) -> ColorSpace:
    """The registered colour space for `name`; "srgb" if the name is unknown."""
    return SPACES.get(name, SRGB) if name else SRGB


def white_xyz(space: ColorSpace) -> tuple[float, float, float]:
    """The space's white point as XYZ with Y = 1 (the Lab reference white)."""
    return space.white_xyz


def rgb8_to_xyz(space: ColorSpace, rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """8-bit RGB *encoded in `space`* → XYZ with Y(white) = 1."""
    r, g, b = (space.decode(max(0, min(255, int(v)))) for v in rgb)
    m = space.matrix
    return (m[0][0] * r + m[0][1] * g + m[0][2] * b,
            m[1][0] * r + m[1][1] * g + m[1][2] * b,
            m[2][0] * r + m[2][1] * g + m[2][2] * b)


def chromaticity_of(xyz: tuple[float, float, float]) -> tuple[float, float]:
    total = sum(xyz)
    return (xyz[0] / total, xyz[1] / total) if total > 0 else (0.0, 0.0)