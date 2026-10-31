"""Data models and colorimetry calculations for KelvinCal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any


# CIE D65 standard illuminant whitepoint (2° standard observer)
D65_X = 0.31271
D65_Y = 0.32902
D65_U_PRIME = (4.0 * D65_X) / (-2.0 * D65_X + 12.0 * D65_Y + 3.0)
D65_V_PRIME = (9.0 * D65_Y) / (-2.0 * D65_X + 12.0 * D65_Y + 3.0)


@dataclass
class DDCState:
    """Current VCP hardware register values of a monitor (DDC/CI)."""

    brightness: int | None = None       # VCP 0x10 (0..100)
    contrast: int | None = None         # VCP 0x12 (0..100)
    red_gain: int | None = None         # VCP 0x16 (0..100)
    green_gain: int | None = None       # VCP 0x18 (0..100)
    blue_gain: int | None = None        # VCP 0x1A (0..100)
    max_brightness: int = 100
    max_contrast: int = 100
    max_rgb_gain: int = 100


@dataclass
class DisplayInfo:
    """Unified representation of a physical display across DRM sysfs, DDC/CI, and Wayland compositor."""

    connector: str                      # e.g. "DP-1", "DP-2", "HDMI-A-2"
    drm_card_connector: str             # e.g. "card1-DP-1"
    edid_hash: str                      # MD5 hex digest over raw EDID bytes (matches KWin edidHash)
    edid_identifier: str = ""           # e.g. "LEN 25250 0 28 2020 0"
    manufacturer: str = ""              # e.g. "LEN"
    model: str = ""                     # e.g. "LEN P32p-20"
    serial: str = ""                    # ASCII serial number from EDID descriptor 0xFF
    i2c_bus: int | None = None          # e.g. 8 for /dev/i2c-8
    ddc_display_num: int | None = None  # Display index (1, 2, 3...)
    width: int = 0
    height: int = 0
    refresh_hz: float = 60.0
    scale: float = 1.0
    compositor_uuid: str = ""
    color_profile_source: str = ""      # "ICC", "sRGB", "EDID"
    icc_profile_path: str = ""
    compositor_brightness: float = 1.0  # 0.0 .. 1.0
    hdr_enabled: bool = False
    wcg_enabled: bool = False
    ddc: DDCState = field(default_factory=DDCState)

    @property
    def display_label(self) -> str:
        """Human-readable label for UI and CLI output."""
        model_str = self.model or self.edid_identifier or "Unknown Display"
        sn_str = f" ({self.serial})" if self.serial else ""
        return f"{self.connector}: {model_str}{sn_str}"


@dataclass
class ColorMeasurement:
    """Single color patch measurement (from spotread / dispread or simulator)."""

    rgb: tuple[int, int, int]
    X: float
    Y: float  # Luminance in cd/m²
    Z: float

    @property
    def xy(self) -> tuple[float, float]:
        """CIE 1931 chromaticity coordinates (x, y)."""
        total = self.X + self.Y + self.Z
        if total <= 1e-9:
            return (D65_X, D65_Y)
        return (self.X / total, self.Y / total)

    @property
    def u_prime_v_prime(self) -> tuple[float, float]:
        """CIE 1976 UCS (u', v') coordinates for perceptually uniform chromaticity shift detection."""
        denom = self.X + 15.0 * self.Y + 3.0 * self.Z
        if denom <= 1e-9:
            return (D65_U_PRIME, D65_V_PRIME)
        return ((4.0 * self.X) / denom, (9.0 * self.Y) / denom)

    @property
    def cct_kelvin(self) -> float:
        """Correlated Color Temperature (CCT in Kelvin using McCamy's approximation)."""
        x, y = self.xy
        if abs(y - 0.1858) < 1e-9:
            return 6500.0
        n = (x - 0.3320) / (0.1858 - y)
        return 449.0 * (n**3) + 3525.0 * (n**2) + 6823.3 * n + 5520.33

    def delta_uv_to(self, other: ColorMeasurement) -> float:
        """Euclidean chromaticity distance Δu'v' to another measurement."""
        u1, v1 = self.u_prime_v_prime
        u2, v2 = other.u_prime_v_prime
        return math.hypot(u1 - u2, v1 - v2)

    def delta_uv_to_d65(self) -> float:
        """Chromaticity distance Δu'v' to the CIE D65 standard whitepoint."""
        u1, v1 = self.u_prime_v_prime
        return math.hypot(u1 - D65_U_PRIME, v1 - D65_V_PRIME)

    def delta_uv_to_xy(self, x: float, y: float) -> float:
        """Chromaticity distance Δu'v' to a target whitepoint given as CIE xy."""
        denom = -2.0 * x + 12.0 * y + 3.0
        u1, v1 = self.u_prime_v_prime
        return math.hypot(u1 - 4.0 * x / denom, v1 - 9.0 * y / denom)


@dataclass
class ContrastStepResult:
    """Result of a single evaluation step in the binary contrast search."""

    contrast: int
    m_low: ColorMeasurement    # e.g. RGB(248, 248, 248)
    m_high: ColorMeasurement   # RGB(255, 255, 255)
    delta_l_cdm2: float        # Y_high - Y_low in cd/m²
    rel_gain: float            # (Y_high - Y_low) / Y_high
    delta_uv: float            # Δu'v' between m_low and m_high (detects single-channel clipping)
    clipped: bool
    reason: str


@dataclass
class DisplayPresetEntry:
    """Configuration of a single monitor inside a multi-monitor preset."""

    edid_hash: str
    connector: str = ""
    model: str = ""
    serial: str = ""
    ddc_brightness: int | None = None
    ddc_contrast: int | None = None
    ddc_red_gain: int | None = None
    ddc_green_gain: int | None = None
    ddc_blue_gain: int | None = None
    icc_profile: str = ""
    color_profile_source: str = "ICC"
    compositor_brightness: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None and v != ""}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisplayPresetEntry:
        return cls(
            edid_hash=str(data.get("edid_hash", "")),
            connector=str(data.get("connector", "")),
            model=str(data.get("model", "")),
            serial=str(data.get("serial", "")),
            ddc_brightness=data.get("ddc_brightness"),
            ddc_contrast=data.get("ddc_contrast"),
            ddc_red_gain=data.get("ddc_red_gain"),
            ddc_green_gain=data.get("ddc_green_gain"),
            ddc_blue_gain=data.get("ddc_blue_gain"),
            icc_profile=str(data.get("icc_profile", "")),
            color_profile_source=str(
                data.get("color_profile_source", "ICC" if data.get("icc_profile") else "sRGB")
            ),
            compositor_brightness=float(data.get("compositor_brightness", 1.0)),
        )


@dataclass
class Preset:
    """Named multi-monitor preset combining DDC/CI hardware state and ICC profiles."""

    name: str
    description: str = ""
    displays: list[DisplayPresetEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        if self.description:
            result["description"] = self.description
        result["displays"] = [d.to_dict() for d in self.displays]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Preset:
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            displays=[
                DisplayPresetEntry.from_dict(d) for d in data.get("displays", [])
            ],
        )
