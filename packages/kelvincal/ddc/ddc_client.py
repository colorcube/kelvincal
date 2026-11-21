"""Fast wrapper around ddcutil for direct I²C bus access (/dev/i2c-X)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from kelvincal.core.models import DDCState


VCP_BRIGHTNESS = "10"
VCP_CONTRAST = "12"
VCP_RED_GAIN = "16"
VCP_GREEN_GAIN = "18"
VCP_BLUE_GAIN = "1A"
GAIN_CODES = (VCP_RED_GAIN, VCP_GREEN_GAIN, VCP_BLUE_GAIN)
GAIN_PROBE_VALUES = (64, 32)
GAIN_RANGE_PROBE_FACTOR = 2  # probe write at max*this to detect raw-0-255 passthrough


def derive_scale(probes: list[tuple[int, int]]) -> float:
    """Derives the readback scale from (written, read-back) probes.

    Monitors exist whose gain readback runs on a different scale than the write
    path (e.g. reads 0-255 while advertising max 100), which makes readback
    values above max look like clipping.
    """
    if len(probes) < 2:
        return 1.0
    (w1, r1), (w2, r2) = probes[0], probes[1]
    if w1 == w2:
        return 1.0
    scale = (r2 - r1) / (w2 - w1)
    return scale if 0.5 <= scale <= 8.0 else 1.0


def classify_gain_channel(
    probes: list[tuple[int, int]], range_probe: tuple[int, int] | None, max_val: int
) -> tuple[float, float]:
    """Returns (read_scale, write_scale) for a gain channel from its probe data.

    - scaled readback: writes are 0..max but reads come back on 0..255 (JBM32O240 green/blue)
    - passthrough: writes and reads both hit a raw 0..255 register (JBM32O240 red)
    - identity: honest 0..max channel
    `range_probe` is (written, read) for a write above max; accepting it unclamped
    means the write path is a raw register wider than max.
    """
    scale = derive_scale(probes)
    if range_probe is not None and max_val > 0:
        written, read = range_probe
        if read > max_val and abs(read - written) <= 4:
            return 255.0 / max_val, 255.0 / max_val
    if abs(scale - 2.55) < 0.3 and max_val <= 100:
        return 2.55, 1.0
    return 1.0, 1.0


def normalized_gain(raw: int, scale: float, offset: float, max_val: int) -> int:
    """Converts a raw readback value into the monitor's write space, clamped to range."""
    write_val = (raw - offset) / scale if scale > 0 else raw
    return max(0, min(max_val, round(write_val)))


def parse_terse_getvcp(raw_output: str) -> dict[str, tuple[int, int]]:
    """Parses `ddcutil --terse getvcp ...` lines such as `VCP 10 C 87 100`.

    Returns:
        Mapping of uppercase VCP hex code (e.g. "10", "1A") -> `(current_val, max_val)`
    """
    values: dict[str, tuple[int, int]] = {}
    for line in raw_output.splitlines():
        m = re.match(r"^\s*VCP\s+([0-9A-Fa-f]{2})\s+C\s+(\d+)\s+(\d+)", line)
        if m:
            code = m.group(1).upper()
            cur_val = int(m.group(2))
            max_val = int(m.group(3))
            values[code] = (cur_val, max_val)
    return values


CALIBRATION_STORE: Path | None = None


def calibration_store() -> Path:
    if CALIBRATION_STORE is not None:
        return CALIBRATION_STORE
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "kelvincal" / "ddc_calibration.json"


def _bus_edid_map(drm_root: Path = Path("/sys/class/drm")) -> dict[int, str]:
    from kelvincal.core.discovery import read_sysfs_drm_displays

    return {
        int(info["i2c_bus"]): str(info["edid_hash"])
        for info in read_sysfs_drm_displays(drm_root).values()
        if isinstance(info.get("i2c_bus"), int) and info.get("edid_hash")
    }


def load_calibrations() -> dict[str, dict[str, tuple[float, float, float]]]:
    try:
        data = json.loads(calibration_store().read_text(encoding="utf-8"))
        return {
            (f"bus:{key}" if str(key).isdigit() else str(key)): {
                code.upper(): (float(f[0]), float(f[1]), float(f[2]))
                for code, f in factors.items()
            }
            for key, factors in data.items()
        }
    except (OSError, ValueError, TypeError, IndexError):
        return {}


def save_calibrations(factors: dict[str, dict[str, tuple[float, float, float]]]) -> None:
    store = calibration_store()
    try:
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps(factors, indent=2), encoding="utf-8")
    except OSError:
        pass


class DDCClient:
    """Controls monitor VCP registers directly via the I²C bus number."""

    def __init__(self, settle_seconds: float = 0.25, sleep_multiplier: float = 0.2) -> None:
        self.settle_seconds = settle_seconds
        self.sleep_multiplier = sleep_multiplier
        self.ddc_bin = shutil.which("ddcutil") or "ddcutil"
        self._readback_factors: dict[str, dict[str, tuple[float, float, float]]] = load_calibrations()
        self._bus_edids: dict[int, str] | None = None

    def _cache_key(self, i2c_bus: int) -> str:
        if self._bus_edids is None:
            self._bus_edids = _bus_edid_map()
        return self._bus_edids.get(i2c_bus) or f"bus:{i2c_bus}"

    def _getvcp_raw(self, i2c_bus: int, code: str) -> tuple[int, int] | None:
        cmd = [
            self.ddc_bin, "--bus", str(i2c_bus),
            "--sleep-multiplier", str(self.sleep_multiplier),
            "--terse", "getvcp", code,
        ]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=8.0)
        except (OSError, subprocess.SubprocessError):
            return None
        parsed = parse_terse_getvcp(proc.stdout)
        return parsed.get(code.upper())

    def _calibrate_gain_readback(self, i2c_bus: int) -> dict[str, tuple[float, float, float]]:
        """Probes each gain code to learn the readback scale and the write scale.

        Returns {code: (read_scale, offset, write_scale)} where
        raw_read = read_scale * gain + offset and monitor_write = write_scale * gain.
        """
        factors: dict[str, tuple[float, float, float]] = {}
        for code in GAIN_CODES:
            raw = self._getvcp_raw(i2c_bus, code)
            if raw is None:
                continue
            cur, max_val = raw
            read_scale, offset, write_scale = 1.0, 0.0, 1.0
            classified = False
            try:
                probes: list[tuple[int, int]] = []
                for probe in GAIN_PROBE_VALUES:
                    self.set_vcp_values(i2c_bus, {code: probe}, settle=False, _raw=True)
                    after = self._getvcp_raw(i2c_bus, code)
                    if after is None:
                        break
                    probes.append((probe, after[0]))
                range_probe: tuple[int, int] | None = None
                if max_val > 0 and max_val < 255:
                    over = max_val * GAIN_RANGE_PROBE_FACTOR
                    self.set_vcp_values(i2c_bus, {code: over}, settle=False, _raw=True)
                    after = self._getvcp_raw(i2c_bus, code)
                    if after is not None:
                        range_probe = (over, after[0])
                if probes:
                    read_scale, write_scale = classify_gain_channel(probes, range_probe, max_val)
                    # Probe writes bypass the write scale, so a probe-derived offset is
                    # only meaningful when writes are already in gain space.
                    offset = (
                        probes[0][1] - read_scale * probes[0][0]
                        if write_scale == 1.0 else 0.0
                    )
                    factors[code] = (read_scale, offset, write_scale)
                    classified = True
            finally:
                # Without classification, writing `cur` raw restores passthrough 0–255 channels
                # verbatim; on scaled-readback channels (0–100 write, 0–255 read) the firmware at
                # worst clamps `cur` to `max_val` instead of dimming a passthrough channel to ~39 %.
                raw_restore = (
                    round(normalized_gain(cur, read_scale, offset, max_val) * write_scale)
                    if classified
                    else cur
                )
                try:
                    self.set_vcp_values(i2c_bus, {code: raw_restore}, settle=False, _raw=True)
                except Exception:  # noqa: BLE001
                    pass
        return factors

    def read_state(self, i2c_bus: int) -> DDCState:
        """Reads brightness (10), contrast (12), and RGB gains (16, 18, 1A) in a single call."""
        cmd = [
            self.ddc_bin,
            "--bus",
            str(i2c_bus),
            "--sleep-multiplier",
            str(self.sleep_multiplier),
            "--terse",
            "getvcp",
            VCP_BRIGHTNESS,
            VCP_CONTRAST,
            VCP_RED_GAIN,
            VCP_GREEN_GAIN,
            VCP_BLUE_GAIN,
        ]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=8.0,
            )
        except (OSError, subprocess.SubprocessError):
            return DDCState()

        parsed = parse_terse_getvcp(proc.stdout)
        state = DDCState()
        if VCP_BRIGHTNESS in parsed:
            state.brightness, state.max_brightness = parsed[VCP_BRIGHTNESS]
        if VCP_CONTRAST in parsed:
            state.contrast, state.max_contrast = parsed[VCP_CONTRAST]

        key = self._cache_key(i2c_bus)
        gain_raw = {code: parsed[code] for code in GAIN_CODES if code in parsed}
        if key in self._readback_factors:
            factors = self._readback_factors[key]
        elif gain_raw and any(cur > mx for cur, mx in gain_raw.values()):
            factors = self._calibrate_gain_readback(i2c_bus)
            self._readback_factors[key] = factors
            save_calibrations(self._readback_factors)
        else:
            factors = {}
        for code, (cur, mx) in gain_raw.items():
            read_scale, offset, _ = factors.get(code, (1.0, 0.0, 1.0))
            setattr(state, {"16": "red_gain", "18": "green_gain", "1A": "blue_gain"}[code],
                    normalized_gain(cur, read_scale, offset, mx))
            if code == VCP_RED_GAIN:
                state.max_rgb_gain = mx
        return state

    def set_vcp_values(
        self,
        i2c_bus: int,
        vcp_pairs: dict[str, int],
        verify: bool = False,
        settle: bool = True,
        *,
        _raw: bool = False,
    ) -> None:
        """Sets one or more VCP values in a single I²C bus invocation."""
        if not vcp_pairs:
            return

        factors = {} if _raw else self._readback_factors.get(self._cache_key(i2c_bus), {})
        cmd = [
            self.ddc_bin,
            "--bus",
            str(i2c_bus),
            "--sleep-multiplier",
            str(self.sleep_multiplier),
            "--verify" if verify else "--noverify",
            "setvcp",
        ]
        for code, val in vcp_pairs.items():
            upper = code.upper()
            write_scale = factors.get(upper, (1.0, 0.0, 1.0))[2] if upper in GAIN_CODES else 1.0
            cmd.extend([upper, str(round(int(val) * write_scale))])

        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10.0)
        if settle and self.settle_seconds > 0:
            time.sleep(self.settle_seconds)

    def set_contrast(self, i2c_bus: int, contrast: int, settle: bool = True) -> None:
        self.set_vcp_values(i2c_bus, {VCP_CONTRAST: contrast}, settle=settle)

    def set_brightness(self, i2c_bus: int, brightness: int, settle: bool = True) -> None:
        self.set_vcp_values(i2c_bus, {VCP_BRIGHTNESS: brightness}, settle=settle)

    def set_rgb_gains(
        self, i2c_bus: int, red: int, green: int, blue: int, settle: bool = True
    ) -> None:
        self.set_vcp_values(
            i2c_bus,
            {
                VCP_RED_GAIN: red,
                VCP_GREEN_GAIN: green,
                VCP_BLUE_GAIN: blue,
            },
            settle=settle,
        )
