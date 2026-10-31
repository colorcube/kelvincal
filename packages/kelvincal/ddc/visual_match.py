"""Visual whitepoint matching: nudge the RGB gains of a display by eye until its white matches another one.

Two panels with different spectra (e.g. W-LED vs. KSF phosphor) can measure identical and still look
different, because the CIE 1931 observer is only an average of human vision. The user moves the white of
one display in small DDC steps until it matches a reference display; measuring the white before and after
gives the offset in xy, which later calibrations add to their whitepoint target for this display.
"""

from __future__ import annotations

WARMER, COOLER, GREENER, MAGENTA = "warmer", "cooler", "greener", "magenta"
DIRECTIONS = (WARMER, COOLER, GREENER, MAGENTA)

Gains = tuple[int, int, int]


def nudge(gains: Gains, direction: str, min_gain: int = 50, max_gain: int = 100) -> Gains:
    """One DDC step in `direction`. Gains only go up while below `max_gain`, otherwise the opposite
    channels go down (the calibration keeps the strongest channel at the maximum)."""
    r, g, b = gains
    if direction == WARMER:
        r, b = (r + 1, b) if r < max_gain else (r, b - 1)
    elif direction == COOLER:
        r, b = (r, b + 1) if b < max_gain else (r - 1, b)
    elif direction == GREENER:
        g, r, b = (g + 1, r, b) if g < max_gain else (g, r - 1, b - 1)
    elif direction == MAGENTA:
        g = g - 1
    else:
        raise ValueError(direction)
    clamp = lambda v: max(min_gain, min(max_gain, v))  # noqa: E731
    return clamp(r), clamp(g), clamp(b)


def white_offset(start_xy: tuple[float, float], final_xy: tuple[float, float],
                 previous: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    """New xy offset of a display: the previous one plus the visual shift (final − start white).

    `start_xy` is the white the display was calibrated to (target + previous offset), so the new target
    is target + previous + (final − start).
    """
    return (round(previous[0] + final_xy[0] - start_xy[0], 4), round(previous[1] + final_xy[1] - start_xy[1], 4))
