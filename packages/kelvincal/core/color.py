"""Colour maths: XYZ → CIELAB and the CIEDE2000 colour difference.

CIEDE2000 follows G. Sharma, W. Wu, E. N. Dalal: "The CIEDE2000 Color-Difference Formula:
Implementation Notes, Supplementary Test Data, and Mathematical Observations", Color Research &
Application 30(1), 2005 (kL = kC = kH = 1).
"""

from __future__ import annotations

import math

Lab = tuple[float, float, float]

_EPS = 216 / 24389
_KAPPA = 24389 / 27


def xyz_to_lab(xyz: tuple[float, float, float], white: tuple[float, float, float]) -> Lab:
    """CIE 1976 L*a*b* of `xyz` relative to the reference `white` (same scale, e.g. Y_white = 100)."""

    def f(t: float) -> float:
        return math.cbrt(t) if t > _EPS else (_KAPPA * t + 16) / 116

    fx, fy, fz = (f(max(0.0, v) / w) if w > 0 else 0.0 for v, w in zip(xyz, white))
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e2000(lab1: Lab, lab2: Lab) -> float:
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_bar7 = ((c1 + c2) / 2) ** 7
    g = 0.5 * (1 - math.sqrt(c_bar7 / (c_bar7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hue(b: float, ap: float) -> float:
        return 0.0 if b == 0 and ap == 0 else math.degrees(math.atan2(b, ap)) % 360

    h1p, h2p = hue(b1, a1p), hue(b2, a2p)
    d_lp = l2 - l1
    d_cp = c2p - c1p
    if c1p * c2p == 0:
        d_hp = 0.0
    else:
        d_hp = h2p - h1p
        if d_hp > 180:
            d_hp -= 360
        elif d_hp < -180:
            d_hp += 360
    d_hp_big = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(d_hp / 2))

    l_bar = (l1 + l2) / 2
    c_bar_p = (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        h_bar = (h1p + h2p + 360) / 2
    else:
        h_bar = (h1p + h2p - 360) / 2

    t = (1 - 0.17 * math.cos(math.radians(h_bar - 30)) + 0.24 * math.cos(math.radians(2 * h_bar))
         + 0.32 * math.cos(math.radians(3 * h_bar + 6)) - 0.20 * math.cos(math.radians(4 * h_bar - 63)))
    d_theta = 30 * math.exp(-(((h_bar - 275) / 25) ** 2))
    c_bar_p7 = c_bar_p ** 7
    r_c = 2 * math.sqrt(c_bar_p7 / (c_bar_p7 + 25 ** 7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / math.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * c_bar_p
    s_h = 1 + 0.015 * c_bar_p * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c
    return math.sqrt(
        (d_lp / s_l) ** 2 + (d_cp / s_c) ** 2 + (d_hp_big / s_h) ** 2 + r_t * (d_cp / s_c) * (d_hp_big / s_h)
    )
