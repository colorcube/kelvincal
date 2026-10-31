"""Fast wrapper around ddcutil for direct I²C bus access (/dev/i2c-X)."""

from __future__ import annotations

import re
import shutil
import subprocess
import time

from kelvincal.core.models import DDCState


VCP_BRIGHTNESS = "10"
VCP_CONTRAST = "12"
VCP_RED_GAIN = "16"
VCP_GREEN_GAIN = "18"
VCP_BLUE_GAIN = "1A"


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


class DDCClient:
    """Controls monitor VCP registers directly via the I²C bus number."""

    def __init__(self, settle_seconds: float = 0.25, sleep_multiplier: float = 0.2) -> None:
        self.settle_seconds = settle_seconds
        self.sleep_multiplier = sleep_multiplier
        self.ddc_bin = shutil.which("ddcutil") or "ddcutil"

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
        if VCP_RED_GAIN in parsed:
            state.red_gain, state.max_rgb_gain = parsed[VCP_RED_GAIN]
        if VCP_GREEN_GAIN in parsed:
            state.green_gain, _ = parsed[VCP_GREEN_GAIN]
        if VCP_BLUE_GAIN in parsed:
            state.blue_gain, _ = parsed[VCP_BLUE_GAIN]
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
