"""Abstract base class for Wayland compositor backends and pre-flight CalibrationColorGuard."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
import time


@dataclass
class CompositorOutputState:
    """State of a display output as reported by the Wayland compositor."""

    connector: str
    edid_hash: str = ""
    edid_identifier: str = ""
    uuid: str = ""
    color_profile_source: str = "sRGB"  # "ICC", "sRGB", "EDID"
    icc_profile_path: str = ""
    brightness: float = 1.0             # 0.0 .. 1.0
    sdr_brightness: int = 200
    hdr_enabled: bool = False
    wcg_enabled: bool = False
    allow_ddc_ci: bool = True
    width: int = 0
    height: int = 0
    refresh_hz: float = 60.0
    scale: float = 1.0


class CompositorBackend(ABC):
    """Interface for querying and applying ICC profiles in the Wayland compositor."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the compositor backend (e.g. 'kwin' or 'mutter')."""

    @abstractmethod
    def get_outputs(self) -> dict[str, CompositorOutputState]:
        """Returns detected display outputs keyed by connector name (e.g. 'DP-1')."""

    @abstractmethod
    def apply_output_profile(
        self,
        connector: str,
        icc_profile_path: str = "",
        color_profile_source: str = "ICC",
        brightness: float | None = None,
        disable_hdr_wcg: bool = False,
    ) -> None:
        """Activates an ICC profile (or sRGB/EDID mode) for a single display output."""

    @abstractmethod
    def apply_batch(
        self,
        updates: list[dict[str, object]],
    ) -> None:
        """Applies multiple display profile updates atomically in a single step."""

    def sync_brightness(self, values: dict[str, int]) -> list[str]:
        """Sets the compositor's own brightness of each output to its DDC brightness (`{connector: 0..100}`).

        KWin controls VCP 0x10 itself when DDC/CI is allowed and writes *its* brightness back to the display
        later (e.g. after idle dimming), which silently undoes a calibrated hardware brightness. Keeping both
        values equal prevents that. Returns the connectors that were updated. Default: nothing to do.
        """
        return []

    def reset_for_calibration(self, connector: str) -> None:
        """Switches a display output to uncalibrated sRGB mode without altering hardware DDC brightness."""
        self.apply_output_profile(
            connector=connector,
            icc_profile_path="",
            color_profile_source="sRGB",
            brightness=None,
        )

    def calibration_guard(
        self, connector: str, settle_seconds: float = 0.4
    ) -> CalibrationColorGuard:
        """Creates a context manager that prevents double-profiling during measurements."""
        return CalibrationColorGuard(
            backend=self, connector=connector, settle_seconds=settle_seconds
        )


class CalibrationColorGuard(AbstractContextManager["CalibrationColorGuard"]):
    """Switches a display to an uncalibrated raw state (sRGB, HDR/WCG off) for the duration of a measurement."""

    def __init__(
        self,
        backend: CompositorBackend,
        connector: str,
        settle_seconds: float = 0.4,
    ) -> None:
        self.backend = backend
        self.connector = connector
        self.settle_seconds = settle_seconds
        self.previous_state: CompositorOutputState | None = None
        self.keep_new_profile: bool = False

    @property
    def previous_icc_path(self) -> str:
        return self.previous_state.icc_profile_path if self.previous_state else ""

    @property
    def previous_source(self) -> str:
        return self.previous_state.color_profile_source if self.previous_state else "sRGB"

    def __enter__(self) -> CalibrationColorGuard:
        outputs = self.backend.get_outputs()
        self.previous_state = outputs.get(self.connector)
        self.backend.apply_output_profile(
            connector=self.connector,
            icc_profile_path="",
            color_profile_source="sRGB",
            brightness=None,
            disable_hdr_wcg=True,
        )
        if self.settle_seconds > 0:
            time.sleep(self.settle_seconds)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self.keep_new_profile and self.previous_state is not None:
            self.backend.apply_output_profile(
                connector=self.connector,
                icc_profile_path=self.previous_state.icc_profile_path,
                color_profile_source=self.previous_state.color_profile_source,
                brightness=None,
            )
