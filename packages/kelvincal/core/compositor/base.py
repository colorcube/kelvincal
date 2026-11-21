"""Abstract base class for Wayland compositor backends and pre-flight CalibrationColorGuard."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
import logging
import time
from typing import Any

from kelvincal.core import recovery
from kelvincal.core.models import is_internal_connector

logger = logging.getLogger(__name__)

NIGHTLIGHT_DAYLIGHT_K = 6450
NIGHTLIGHT_TRANSITION_TIMEOUT_S = 3.0
NIGHTLIGHT_POLL_S = 0.1


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

    def night_light_guard(self) -> AbstractContextManager[Any]:
        """Context manager that suppresses Night Light during measurements (even when keeping the ICC profile)."""
        return nullcontext()

    def default_srgb_eotf(self) -> str:
        """Transfer function the compositor uses when decoding untagged sRGB surfaces ('srgb' or 'gamma22')."""
        return "srgb"

    def calibration_guard(
        self,
        connector: str,
        settle_seconds: float = 0.4,
        *,
        ddc_answers: bool = True,
        on_status: Any = None,
    ) -> CalibrationColorGuard:
        """Creates a context manager that prevents double-profiling during measurements."""
        return CalibrationColorGuard(
            backend=self,
            connector=connector,
            settle_seconds=settle_seconds,
            ddc_answers=ddc_answers,
            on_status=on_status,
        )


class NightLightInhibitor(AbstractContextManager["NightLightInhibitor"]):
    """Inhibits KWin's Night Light on the session D-Bus and waits for its colour-temperature ramp to finish.

    Uses a private D-Bus connection so that KWin's QDBusServiceWatcher automatically drops the inhibition
    if the KelvinCal process terminates unexpectedly. Can be used standalone (e.g. during verification or
    spot check) as well as inside `CalibrationColorGuard`.
    """

    def __init__(
        self,
        transition_timeout_s: float = NIGHTLIGHT_TRANSITION_TIMEOUT_S,
        poll_interval_s: float = NIGHTLIGHT_POLL_S,
    ) -> None:
        self.transition_timeout_s = transition_timeout_s
        self.poll_interval_s = poll_interval_s
        self._conn_name: str | None = None
        self._bus: Any = None
        self._cookie: Any = None

    def __enter__(self) -> NightLightInhibitor:
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
        except ImportError:  # pragma: no cover
            return self

        conn_name = f"kelvincal-nightlight-{time.monotonic_ns()}"
        bus = QDBusConnection.connectToBus(QDBusConnection.BusType.SessionBus, conn_name)
        if not bus.isConnected():
            logger.warning("Could not connect to session D-Bus to inhibit KWin Night Light.")
            return self

        iface = QDBusInterface(
            "org.kde.KWin.NightLight", "/org/kde/KWin/NightLight", "org.kde.KWin.NightLight", bus
        )
        was_running = bool(iface.property("running"))
        pre_temp = iface.property("currentTemperature")
        was_warm_shifted = was_running or (isinstance(pre_temp, int) and 0 < pre_temp < NIGHTLIGHT_DAYLIGHT_K)

        reply = iface.call("inhibit")
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            err = reply.errorName()
            if err != "org.freedesktop.DBus.Error.ServiceUnknown":
                logger.warning("Failed to inhibit KWin Night Light (%s): %s", err, reply.errorMessage())
            QDBusConnection.disconnectFromBus(conn_name)
            return self

        self._conn_name = conn_name
        self._bus = bus
        self._cookie = reply.arguments()[0] if reply.arguments() else None

        # KWin ramps colour temperature smoothly (~2 s) after inhibit(); wait until ~6500 K is reached.
        if was_warm_shifted and self.transition_timeout_s > 0:
            deadline = time.monotonic() + self.transition_timeout_s
            while time.monotonic() < deadline:
                cur_temp = iface.property("currentTemperature")
                if isinstance(cur_temp, int) and cur_temp >= NIGHTLIGHT_DAYLIGHT_K:
                    break
                if cur_temp is None and not bool(iface.property("running")):
                    time.sleep(min(2.0, self.transition_timeout_s))
                    break
                time.sleep(self.poll_interval_s)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn_name is None:
            return
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface

            if self._cookie is not None and self._bus is not None:
                try:
                    QDBusInterface(
                        "org.kde.KWin.NightLight",
                        "/org/kde/KWin/NightLight",
                        "org.kde.KWin.NightLight",
                        self._bus,
                    ).call("uninhibit", self._cookie)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Could not uninhibit KWin Night Light cleanly: %s", exc)
            QDBusConnection.disconnectFromBus(self._conn_name)
        finally:
            self._conn_name = None
            self._bus = None
            self._cookie = None


class CalibrationColorGuard(AbstractContextManager["CalibrationColorGuard"]):
    """Switches a display to an uncalibrated raw state (sRGB, HDR/WCG off, Night Light off) for a measurement."""

    def __init__(
        self,
        backend: CompositorBackend,
        connector: str,
        settle_seconds: float = 0.4,
        *,
        ddc_answers: bool = True,
        on_status: Any = None,
    ) -> None:
        self.backend = backend
        self.connector = connector
        self.settle_seconds = settle_seconds
        self.ddc_answers = ddc_answers
        self.on_status = on_status
        self.previous_state: CompositorOutputState | None = None
        self.keep_new_profile: bool = False
        self._night_light_cm: AbstractContextManager[Any] = nullcontext()

    @property
    def previous_icc_path(self) -> str:
        return self.previous_state.icc_profile_path if self.previous_state else ""

    @property
    def previous_source(self) -> str:
        return self.previous_state.color_profile_source if self.previous_state else "sRGB"

    def _is_software_dimmed(self) -> bool:
        """True when KWin's output brightness < 1.0 dims pixels in software rather than driving hardware.

        Internal panels (eDP/LVDS/DSI) drive a kernel hardware backlight via KWin and must never be forced
        to 100 % (which would also overwrite the user's interactive brightness setting). External displays
        dim in software whenever they lack working DDC/CI (`not ddc_answers`) or DDC/CI is disabled in KWin
        (`not allow_ddc_ci`).
        """
        st = self.previous_state
        if st is None or st.brightness >= 1.0 or is_internal_connector(self.connector):
            return False
        return (not self.ddc_answers) or (not st.allow_ddc_ci)

    def __enter__(self) -> CalibrationColorGuard:
        from kelvincal.core.i18n import translate

        self._night_light_cm = self.backend.night_light_guard()
        self._night_light_cm.__enter__()
        try:
            outputs = self.backend.get_outputs()
            self.previous_state = outputs.get(self.connector)
            recovery.record(self.connector, self.previous_state)   # in case KelvinCal dies before __exit__
            sw_dimmed = self._is_software_dimmed()
            if sw_dimmed and self.previous_state is not None:
                pct = round(self.previous_state.brightness * 100)
                msg = translate(
                    "Controller",
                    "ℹ Compositor software dimming ({pct} %) on {connector} temporarily set to 100 % for measurement.",
                ).format(pct=pct, connector=self.connector)
                logger.info(msg)
                if callable(self.on_status):
                    self.on_status(msg)
            raw_brightness = 1.0 if sw_dimmed else None
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
        except BaseException:
            self._night_light_cm.__exit__(None, None, None)
            self._night_light_cm = nullcontext()
            raise

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        from kelvincal.core.i18n import translate

        try:
            restore_sw_brightness = (
                self.previous_state.brightness
                if (self.previous_state is not None and self._is_software_dimmed())
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
            if restore_sw_brightness is not None:
                pct = round(restore_sw_brightness * 100)
                msg = translate(
                    "Controller",
                    "ℹ Restored compositor software dimming to {pct} % on {connector} "
                    "(active luminance is lower than the 100 % profile measurement).",
                ).format(pct=pct, connector=self.connector)
                logger.info(msg)
                if callable(self.on_status):
                    self.on_status(msg)
        finally:
            self._night_light_cm.__exit__(exc_type, exc_val, exc_tb)
            self._night_light_cm = nullcontext()
