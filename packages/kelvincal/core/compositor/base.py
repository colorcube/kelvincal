"""Abstract base class for Wayland compositor backends and pre-flight CalibrationColorGuard."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
import time
from typing import Callable

from kelvincal.core import recovery


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


def _inhibit_kwin_night_light() -> Callable[[], None]:
    """Inhibits KWin's Night Light on the session D-Bus for the duration of a measurement.

    Uses a private D-Bus connection so that KWin's QDBusServiceWatcher automatically releases the
    inhibition even if the process terminates unexpectedly.
    """
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
    except ImportError:  # pragma: no cover
        return lambda: None
    conn_name = f"kelvincal-nightlight-{time.monotonic_ns()}"
    bus = QDBusConnection.connectToBus(QDBusConnection.BusType.SessionBus, conn_name)
    if not bus.isConnected():
        return lambda: None
    iface = QDBusInterface("org.kde.KWin.NightLight", "/org/kde/KWin/NightLight", "org.kde.KWin.NightLight", bus)
    reply = iface.call("inhibit")
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        QDBusConnection.disconnectFromBus(conn_name)
        return lambda: None
    cookie = reply.arguments()[0] if reply.arguments() else None

    def release() -> None:
        if cookie is not None:
            try:
                QDBusInterface(
                    "org.kde.KWin.NightLight", "/org/kde/KWin/NightLight", "org.kde.KWin.NightLight", bus
                ).call("uninhibit", cookie)
            except Exception:  # noqa: BLE001
                pass
        QDBusConnection.disconnectFromBus(conn_name)

    return release


class CalibrationColorGuard(AbstractContextManager["CalibrationColorGuard"]):
    """Switches a display to an uncalibrated raw state (sRGB, HDR/WCG off, Night Light off) for a measurement."""

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
        self._release_night_light: Callable[[], None] = lambda: None

    @property
    def previous_icc_path(self) -> str:
        return self.previous_state.icc_profile_path if self.previous_state else ""

    @property
    def previous_source(self) -> str:
        return self.previous_state.color_profile_source if self.previous_state else "sRGB"

    def __enter__(self) -> CalibrationColorGuard:
        self._release_night_light = _inhibit_kwin_night_light()
        outputs = self.backend.get_outputs()
        self.previous_state = outputs.get(self.connector)
        recovery.record(self.connector, self.previous_state)   # in case KelvinCal dies before __exit__
        # If KWin does not control hardware DDC/CI (allow_ddc_ci=False), a compositor brightness < 1.0
        # dims the output in software, which would distort patch measurements; reset to 1.0 during the run.
        raw_brightness = (
            1.0
            if (self.previous_state is not None and not self.previous_state.allow_ddc_ci and self.previous_state.brightness < 1.0)
            else None
        )
        self.backend.apply_output_profile(
            connector=self.connector,
            icc_profile_path="",
            color_profile_source="sRGB",
            brightness=raw_brightness,
            disable_hdr_wcg=True,
        )
        if self.settle_seconds > 0:
            time.sleep(self.settle_seconds)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            # Restore software brightness if we temporarily reset it to 100 % on a non-DDC output
            restore_sw_brightness = (
                self.previous_state.brightness
                if (self.previous_state is not None and not self.previous_state.allow_ddc_ci and self.previous_state.brightness < 1.0)
                else None
            )
            # with keep_new_profile the staged profile stays active: the recovery record is cleared once it
            # has been saved or discarded (recovery.clear)
            if not self.keep_new_profile and self.previous_state is not None:
                self.backend.apply_output_profile(
                    connector=self.connector,
                    icc_profile_path=self.previous_state.icc_profile_path,
                    color_profile_source=self.previous_state.color_profile_source,
                    brightness=restore_sw_brightness,
                )
                recovery.clear(self.connector)
            elif restore_sw_brightness is not None and self.previous_state is not None:
                outputs = self.backend.get_outputs()
                cur = outputs.get(self.connector)
                self.backend.apply_output_profile(
                    connector=self.connector,
                    icc_profile_path=cur.icc_profile_path if cur else "",
                    color_profile_source=cur.color_profile_source if cur else "ICC",
                    brightness=restore_sw_brightness,
                )
        finally:
            self._release_night_light()
            self._release_night_light = lambda: None
