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
VCP_INPUT_SOURCE = "60"
DEFAULT_INPUT_SOURCE = 0x0F  # DisplayPort-1
ALTERNATE_INPUT_SOURCE = 0x11  # HDMI-1
SIX_AXIS_HUE_CODES = {"red": "9B", "yellow": "9C", "green": "9D", "cyan": "9E", "blue": "9F", "magenta": "A0"}
INPUT_SOURCE_RE = re.compile(r"sl=0x([0-9A-Fa-f]{2})")
APPLY_SETTLE_SECONDS = 3.0


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


CALIBRATION_STORE = Path(
    os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")
) / "kelvincal" / "ddc_calibration.json"


def load_calibrations() -> dict[int, dict[str, tuple[float, float, float]]]:
    try:
        data = json.loads(CALIBRATION_STORE.read_text())
        return {
            int(bus): {code: tuple(f) for code, f in factors.items()}
            for bus, factors in data.items()
        }
    except (OSError, ValueError, TypeError):
        return {}


def save_calibrations(factors: dict[int, dict[str, tuple[float, float, float]]]) -> None:
    try:
        CALIBRATION_STORE.parent.mkdir(parents=True, exist_ok=True)
        payload = {str(bus): factors_bus for bus, factors_bus in factors.items()}
        CALIBRATION_STORE.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


class DDCClient:
    """Controls monitor VCP registers directly via the I²C bus number."""

    def __init__(self, settle_seconds: float = 0.25, sleep_multiplier: float = 0.2) -> None:
        self.settle_seconds = settle_seconds
        self.sleep_multiplier = sleep_multiplier
        self.ddc_bin = shutil.which("ddcutil") or "ddcutil"
        self._readback_factors: dict[int, dict[str, tuple[float, float, float]]] = load_calibrations()

    def _getvcp_raw_output(self, i2c_bus: int, *codes: str) -> str:
        cmd = [
            self.ddc_bin, "--bus", str(i2c_bus),
            "--sleep-multiplier", str(self.sleep_multiplier),
            "--terse", "getvcp", *codes,
        ]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=8.0)
        except (OSError, subprocess.SubprocessError):
            return ""
        return proc.stdout

    def _getvcp_raw(self, i2c_bus: int, code: str) -> tuple[int, int] | None:
        parsed = parse_terse_getvcp(self._getvcp_raw_output(i2c_bus, code))
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
            probes: list[tuple[int, int]] = []
            for probe in GAIN_PROBE_VALUES:
                self.set_vcp_values(i2c_bus, {code: probe}, settle=False)
                after = self._getvcp_raw(i2c_bus, code)
                if after is None:
                    break
                probes.append((probe, after[0]))
            range_probe: tuple[int, int] | None = None
            if max_val > 0 and max_val < 255:
                over = max_val * GAIN_RANGE_PROBE_FACTOR
                self.set_vcp_values(i2c_bus, {code: over}, settle=False)
                after = self._getvcp_raw(i2c_bus, code)
                if after is not None:
                    range_probe = (over, after[0])
            read_scale, write_scale = classify_gain_channel(probes, range_probe, max_val)
            # Probe writes bypass the write scale, so a probe-derived offset is
            # only meaningful when writes are already in gain space.
            offset = (
                probes[0][1] - read_scale * probes[0][0]
                if probes and write_scale == 1.0 else 0.0
            )
            factors[code] = (read_scale, offset, write_scale)
            restore = normalized_gain(cur, read_scale, offset, max_val)
            self.set_vcp_values(i2c_bus, {code: round(restore * write_scale)}, settle=False)
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
            *SIX_AXIS_HUE_CODES.values(),
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

        gain_raw = {code: parsed[code] for code in GAIN_CODES if code in parsed}
        if gain_raw and any(cur > mx for cur, mx in gain_raw.values()):
            if i2c_bus not in self._readback_factors:
                self._readback_factors[i2c_bus] = self._calibrate_gain_readback(i2c_bus)
                save_calibrations(self._readback_factors)
            factors = self._readback_factors[i2c_bus]
        else:
            factors = {code: (1.0, 0.0, 1.0) for code in GAIN_CODES}
        for code, (cur, mx) in gain_raw.items():
            read_scale, offset, _ = factors.get(code, (1.0, 0.0, 1.0))
            setattr(state, {"16": "red_gain", "18": "green_gain", "1A": "blue_gain"}[code],
                    normalized_gain(cur, read_scale, offset, mx))
            if code == VCP_RED_GAIN:
                state.max_rgb_gain = mx
        hue_axes = {code: axis for axis, code in SIX_AXIS_HUE_CODES.items()}
        state.six_axis_hue = {hue_axes[code]: cur for code, (cur, _mx) in parsed.items() if code in hue_axes}
        return state

    def set_vcp_values(
        self,
        i2c_bus: int,
        vcp_pairs: dict[str, int],
        verify: bool = False,
        settle: bool = True,
    ) -> None:
        """Sets one or more VCP values in a single I²C bus invocation."""
        if not vcp_pairs:
            return

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
            cmd.extend([code.upper(), str(int(val))])

        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10.0)
        if settle and self.settle_seconds > 0:
            time.sleep(self.settle_seconds)

    def set_contrast(self, i2c_bus: int, contrast: int, settle: bool = True) -> None:
        self.set_vcp_values(i2c_bus, {VCP_CONTRAST: contrast}, settle=settle)

    def set_brightness(self, i2c_bus: int, brightness: int, settle: bool = True) -> None:
        self.set_vcp_values(i2c_bus, {VCP_BRIGHTNESS: brightness}, settle=settle)

    def read_input_source(self, i2c_bus: int) -> int | None:
        """Reads the current input source selector value (e.g. 0x0f DisplayPort-1)."""
        cmd = [
            self.ddc_bin, "--bus", str(i2c_bus),
            "--sleep-multiplier", str(self.sleep_multiplier), "getvcp", VCP_INPUT_SOURCE,
        ]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=8.0)
        except (OSError, subprocess.SubprocessError):
            return None
        m = INPUT_SOURCE_RE.search(proc.stdout)
        return int(m.group(1), 16) if m else None

    def force_settings_apply(self, i2c_bus: int) -> None:
        """Forces the monitor to re-apply all settings through its OSD/boot apply path.

        Panels whose DDC write handler applies gains differently from the OSD
        (JBM32O240) render DDC-written registers wrongly until a full apply runs.
        Toggling the input source away and back triggers that apply.
        """
        current = self.read_input_source(i2c_bus)
        target = current if current is not None else DEFAULT_INPUT_SOURCE
        other = ALTERNATE_INPUT_SOURCE if target != ALTERNATE_INPUT_SOURCE else DEFAULT_INPUT_SOURCE
        self.set_vcp_values(i2c_bus, {VCP_INPUT_SOURCE: other}, settle=False)
        time.sleep(APPLY_SETTLE_SECONDS)
        self.set_vcp_values(i2c_bus, {VCP_INPUT_SOURCE: target}, settle=False)
        time.sleep(APPLY_SETTLE_SECONDS)

    def set_hue(self, i2c_bus: int, values: dict[str, int]) -> None:
        """Writes six-axis hue controls (VCP 0x9B-0xA0, 50 = neutral)."""
        writes = {SIX_AXIS_HUE_CODES[axis]: value for axis, value in values.items()}
        self.set_vcp_values(i2c_bus, writes)

    def read_hue(self, i2c_bus: int) -> dict[str, int]:
        """Reads the six-axis hue controls; empty when the panel does not expose them."""
        parsed = parse_terse_getvcp(self._getvcp_raw_output(i2c_bus, *SIX_AXIS_HUE_CODES.values()))
        code_to_axis = {code: axis for axis, code in SIX_AXIS_HUE_CODES.items()}
        return {code_to_axis[code]: cur for code, (cur, _max) in parsed.items()}

    def set_rgb_gains(
        self, i2c_bus: int, red: int, green: int, blue: int, settle: bool = True,
        apply: bool = False,
    ) -> None:
        """Writes gains in gain space; `apply=True` ends with an input-source toggle so
        panels that need the OSD apply path render the gains correctly."""
        gains = {VCP_RED_GAIN: red, VCP_GREEN_GAIN: green, VCP_BLUE_GAIN: blue}
        factors = self._readback_factors.get(i2c_bus, {})
        writes = {
            code: round(val * factors.get(code, (1.0, 0.0, 1.0))[2])
            for code, val in gains.items()
        }
        self.set_vcp_values(i2c_bus, writes, settle=settle)
        if apply:
            self.force_settings_apply(i2c_bus)
