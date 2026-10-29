"""Reads the 'vcgt' tag (video card gamma table) of ICC profiles.

The tag holds calibration curves that are meant to be loaded into the graphics card. Whether they are
applied depends on the system (X11 + dispwin: yes; Wayland: up to the compositor). KelvinCal does not
write vcgt – its calibration happens in the display hardware via DDC/CI.

Layout (ICC.1 private tag, Apple): 'vcgt' sig, 4 reserved bytes, uint32 gammaType
  0 = table:   uint16 channels, uint16 entryCount, uint16 entrySize (1 or 2 bytes), then the curves
  1 = formula: per channel s15Fixed16 gamma, min, max (R, G, B)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from kcal_argyll.profile_inspector import _parse_icc_tags


@dataclass(frozen=True)
class Vcgt:
    curves: tuple[list[float], list[float], list[float]]   # 0..1 per channel

    @property
    def size(self) -> int:
        return len(self.curves[0])

    @property
    def white(self) -> tuple[float, float, float]:
        """Output at full input: < 1.0 means the curves pull that channel down (white point correction)."""
        return tuple(c[-1] for c in self.curves)  # type: ignore[return-value]

    @property
    def max_deviation(self) -> float:
        """Largest difference from a linear (identity) curve, 0..1."""
        dev = 0.0
        for curve in self.curves:
            n = len(curve) - 1 or 1
            dev = max(dev, max(abs(v - i / n) for i, v in enumerate(curve)))
        return dev

    @property
    def is_identity(self) -> bool:
        return self.max_deviation < 0.002


def read_vcgt(icc_path: str | Path) -> Vcgt | None:
    """The calibration curves of a profile, or None if it has no (readable) vcgt tag."""
    tags = _parse_icc_tags(Path(icc_path).read_bytes())
    data = tags.get(b"vcgt")
    if not data or len(data) < 12 or data[:4] != b"vcgt":
        return None
    gamma_type = struct.unpack_from(">I", data, 8)[0]
    if gamma_type == 0:
        channels, count, size = struct.unpack_from(">HHH", data, 12)
        if channels not in (1, 3) or count < 2 or size not in (1, 2):
            return None
        fmt, top = (">B", 255.0) if size == 1 else (">H", 65535.0)
        offset = 18
        curves: list[list[float]] = []
        for _ch in range(channels):
            values = []
            for _i in range(count):
                if offset + size > len(data):
                    return None
                values.append(struct.unpack_from(fmt, data, offset)[0] / top)
                offset += size
            curves.append(values)
        if channels == 1:
            curves = [curves[0]] * 3
        return Vcgt((curves[0], curves[1], curves[2]))
    if gamma_type == 1 and len(data) >= 12 + 36:
        params = [struct.unpack_from(">i", data, 12 + 4 * k)[0] / 65536.0 for k in range(9)]
        curves = []
        for ch in range(3):
            gamma, lo, hi = params[3 * ch: 3 * ch + 3]
            curves.append([lo + (hi - lo) * (i / 255) ** gamma for i in range(256)])
        return Vcgt((curves[0], curves[1], curves[2]))
    return None
