"""wp_color_manager_v1 machinery: connect, capabilities, descriptions.

All wire-level plumbing lives here; display.py builds the tagged patch window on
top. The client binds protocol version 1 — the v1 named enums the declaration
plans in tags.py are written against. Event callbacks are registered on each
proxy's pywayland Dispatcher by event name (proxy.dispatcher["event"] = fn).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from pywayland.client.display import Display

from kelvincal.wayland_cm.protocol.color_management_v1 import (
    WpColorManagerV1,
    WpImageDescriptionCreatorParamsV1,
    WpImageDescriptionV1,
)
from kelvincal.wayland_cm.protocol.wayland import (
    WlCompositor,
    WlOutput,
    WlRegistry,
    WlShm,
)
from kelvincal.wayland_cm.protocol.xdg_output_unstable_v1 import ZxdgOutputManagerV1

from kelvincal.wayland_cm.tags import DeclarationPlan

BIND_TIMEOUT_S = 5.0
OUTPUT_VERSION = 4   # wl_output v4 carries the connector `name`


@dataclass
class Capabilities:
    """What the manager listed in its supported_* events."""

    features: set[int] = field(default_factory=set)
    primaries: set[int] = field(default_factory=set)
    transfer_functions: set[int] = field(default_factory=set)
    intents: set[int] = field(default_factory=set)
    done: bool = False

    def declareable(self, plan: DeclarationPlan) -> list[str]:
        """Human-readable capability problems for `plan`, empty when declarable."""
        problems = []
        for feat in sorted(plan.required_features - self.features):
            problems.append(f"feature {feat}")
        if plan.primaries_named not in self.primaries:
            problems.append(f"named primaries {plan.primaries_named}")
        if plan.tf_named is not None and plan.tf_named not in self.transfer_functions:
            problems.append(f"named transfer function {plan.tf_named}")
        return problems


@dataclass
class DescriptionInfo:
    """What an image description is made of, as the compositor told it."""

    primaries_named: int | None = None
    # (r_x, r_y, g_x, g_y, b_x, b_y, w_x, w_y) — CIE 1931 xy, protocol x1M units decoded
    primaries_xy: tuple[float, float, float, float, float, float, float, float] | None = None
    tf_named: int | None = None
    tf_power: float | None = None
    luminances: tuple[float, float, float] | None = None

    def primaries_str(self) -> str:
        if self.primaries_xy is None:
            return self.named_primaries()
        r_x, r_y, g_x, g_y, b_x, b_y, w_x, w_y = (v / 1e6 for v in self.primaries_xy)
        return (f"R {r_x:.4f},{r_y:.4f} G {g_x:.4f},{g_y:.4f} B {b_x:.4f},{b_y:.4f} "
                f"white {w_x:.4f},{w_y:.4f}")

    def named_primaries(self) -> str:
        names = {1: "srgb", 2: "pal_m", 3: "pal", 4: "ntsc", 5: "generic_film", 6: "bt2020",
                 7: "cie1931_xyz", 8: "dci_p3", 9: "display_p3", 10: "adobe_rgb"}
        if self.primaries_named is None:
            return "unnamed (custom chromaticities)"
        return names.get(self.primaries_named, str(self.primaries_named))


@dataclass
class OutputGlobals:
    proxy: object
    name: str = ""
    description: str = ""
    width: int = 0      # mode size in mode pixels
    height: int = 0
    scale: int = 1      # integer wl_output scale (KWin rounds fractional scales UP)
    logical_width: int = 0    # xdg-output logical size — the real effective scale
    logical_height: int = 0

    def logical_size(self) -> tuple[int, int] | None:
        if self.logical_width and self.logical_height:
            return (self.logical_width, self.logical_height)
        return None


class ColorManagerConnection:
    """One wl_display connection with the CM globals bound.

    Creating this performs no visible action: no surface is attached or
    committed, so it is safe to use while a measurement is running.
    """

    def __init__(self, socket_name: str | None = None) -> None:
        if socket_name is not None:
            import os

            runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            if runtime_dir and not os.path.exists(os.path.join(runtime_dir, socket_name)):
                raise RuntimeError(f"no Wayland socket {socket_name!r} in {runtime_dir}")
        self.display = Display()
        self.display.connect()
        self.registry = self.display.get_registry()
        self._globals: list[tuple[int, str, int]] = []
        self.registry.dispatcher["global"] = self._on_global
        self.registry.dispatcher["global_remove"] = lambda proxy, name: None
        self._roundtrip()
        self.compositor: WlCompositor.proxy_class | None = None
        self.shm: WlShm.proxy_class | None = None
        self.outputs: list[OutputGlobals] = []
        self.manager: WpColorManagerV1.proxy_class | None = None
        self.caps = Capabilities()
        self._bind_globals()

    # ------------------------------------------------------------- plumbing

    def _on_global(self, proxy, name: int, interface: str, version: int) -> None:  # noqa: ANN001
        self._globals.append((name, interface, version))

    def _roundtrip(self) -> None:
        self.display.roundtrip()
        self.display.flush()

    def _dispatch_until(self, predicate, timeout_s: float = BIND_TIMEOUT_S) -> None:  # noqa: ANN001
        # dispatch(block=False) never reads the fd (pywayland maps it to
        # wl_display_dispatch_pending), so wait for data on the socket and
        # dispatch it — with a deadline, because a compositor that never
        # answers must not hang a measurement.
        import select

        fd = self.display.get_fd()
        deadline = time.monotonic() + timeout_s
        while not predicate():
            self.display.flush()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Wayland compositor did not answer in time")
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if ready:
                # data is on the socket: the blocking dispatch reads it and cannot stall
                self.display.dispatch(block=True)
                # pending events from the queue just read may satisfy the predicate
                self.display.dispatch(block=False)

    def _bind_globals(self) -> None:
        manager_bound = False
        output_manager = None
        output_globals: list[tuple[int, int]] = []
        for name, interface, version in self._globals:
            if interface == WlCompositor.name and self.compositor is None:
                self.compositor = self.registry.bind(name, WlCompositor, min(version, 4))
            elif interface == WlShm.name and self.shm is None:
                self.shm = self.registry.bind(name, WlShm, 1)
            elif interface == ZxdgOutputManagerV1.name and output_manager is None:
                output_manager = self.registry.bind(name, ZxdgOutputManagerV1, min(version, 2))
            elif interface == WlOutput.name:
                output_globals.append((name, version))
            elif interface == WpColorManagerV1.name and not manager_bound:
                # v1: the named-enum semantics tags.py is written against
                self.manager = self.registry.bind(name, WpColorManagerV1, 1)
                self._bind_manager()
                manager_bound = True
        for name, version in output_globals:
            self._bind_output(name, version, output_manager)
        self._roundtrip()
        if self.manager is None:
            raise RuntimeError("the compositor does not offer wp_color_manager_v1")
        self._dispatch_until(lambda: self.caps.done)
        self._roundtrip()

    def _bind_output(self, name: int, version: int, output_manager) -> None:  # noqa: ANN001
        info = OutputGlobals(proxy=None)
        proxy = self.registry.bind(name, WlOutput, min(version, OUTPUT_VERSION))

        def on_mode(proxy, flags, width, height, refresh) -> None:  # noqa: ANN001
            if flags & 1:  # WL_OUTPUT_MODE_CURRENT
                info.width, info.height = width, height

        def on_scale(proxy, factor) -> None:  # noqa: ANN001
            info.scale = factor

        def on_name(proxy, output_name) -> None:  # noqa: ANN001
            info.name = output_name

        def on_description(proxy, description) -> None:  # noqa: ANN001
            info.description = description

        proxy.dispatcher["mode"] = on_mode
        proxy.dispatcher["scale"] = on_scale
        proxy.dispatcher["name"] = on_name
        proxy.dispatcher["description"] = on_description
        info.proxy = proxy

        if output_manager is not None:
            # The logical size carries the real effective scale; wl_output.scale
            # is the integer KWin rounds fractional scaling up to.
            xdg_output = output_manager.get_xdg_output(proxy)

            def on_logical_position(proxy, x, y) -> None:  # noqa: ANN001
                pass

            def on_logical_size(proxy, width, height) -> None:  # noqa: ANN001
                info.logical_width, info.logical_height = width, height

            xdg_output.dispatcher["logical_position"] = on_logical_position
            xdg_output.dispatcher["logical_size"] = on_logical_size

        self.outputs.append(info)

    def _bind_manager(self) -> None:
        assert self.manager is not None
        caps = self.caps

        def on_intent(proxy, value) -> None:  # noqa: ANN001
            caps.intents.add(value)

        def on_feature(proxy, value) -> None:  # noqa: ANN001
            caps.features.add(value)

        def on_tf(proxy, value) -> None:  # noqa: ANN001
            caps.transfer_functions.add(value)

        def on_primaries(proxy, value) -> None:  # noqa: ANN001
            caps.primaries.add(value)

        def on_done(proxy) -> None:  # noqa: ANN001
            caps.done = True

        d = self.manager.dispatcher
        d["supported_intent"] = on_intent
        d["supported_feature"] = on_feature
        d["supported_tf_named"] = on_tf
        d["supported_primaries_named"] = on_primaries
        d["done"] = on_done

    def output_for_connector(self, connector: str) -> OutputGlobals:
        for info in self.outputs:
            if info.name == connector:
                return info
        names = ", ".join(i.name or "?" for i in self.outputs) or "none"
        raise RuntimeError(f"no wl_output named {connector!r} (outputs: {names})")

    # -------------------------------------------------------------- queries

    def output_description(self, connector: str) -> DescriptionInfo:
        """What the compositor says the output's own image description is.

        Uses wp_color_management_output_v1.get_image_description on the
        wl_output — no surface involved, nothing can become visible. With an
        ICC profile active this reports the profile's primaries; plain
        `srgb`-named primaries mean the compositor treats the output as sRGB
        (no profile) — a state assumption made visible.
        """
        assert self.manager is not None
        output = self.output_for_connector(connector)
        cm_output = self.manager.get_output(output.proxy)
        state: dict[str, object] = {"desc": None}

        def on_ready(proxy, identity) -> None:  # noqa: ANN001
            state["desc"] = proxy

        def on_failed(proxy, cause, message) -> None:  # noqa: ANN001
            raise RuntimeError(f"compositor refused the output-description query: {message}")

        desc: WpImageDescriptionV1.proxy_class = cm_output.get_image_description()
        desc.dispatcher["ready"] = on_ready
        desc.dispatcher["failed"] = on_failed
        self._dispatch_until(lambda: state["desc"] is not None)
        desc = state["desc"]  # type: ignore[assignment]
        info = DescriptionInfo()
        desc_info = desc.get_information()
        done = {"seen": False}

        def on_primaries(proxy, r_x, r_y, g_x, g_y, b_x, b_y, w_x, w_y) -> None:  # noqa: ANN001
            info.primaries_xy = (r_x, r_y, g_x, g_y, b_x, b_y, w_x, w_y)
            done["seen"] = True

        def on_primaries_named(proxy, value) -> None:  # noqa: ANN001
            info.primaries_named = value
            done["seen"] = True

        def on_tf_power(proxy, exponent) -> None:  # noqa: ANN001
            info.tf_power = exponent

        def on_tf_named(proxy, value) -> None:  # noqa: ANN001
            info.tf_named = value

        def on_luminances(proxy, min_lum, max_lum, ref_lum) -> None:  # noqa: ANN001
            info.luminances = (min_lum, max_lum, ref_lum)

        def on_info_done(proxy) -> None:  # noqa: ANN001
            done["seen"] = True

        d = desc_info.dispatcher
        d["primaries"] = on_primaries
        d["primaries_named"] = on_primaries_named
        d["tf_power"] = on_tf_power
        d["tf_named"] = on_tf_named
        d["luminances"] = on_luminances
        d["done"] = on_info_done
        self._dispatch_until(lambda: done["seen"])
        self._roundtrip()
        for obj in (desc_info, desc, cm_output):
            try:
                obj.destroy()
            except Exception:  # noqa: BLE001 - best effort teardown of query objects
                pass
        self._roundtrip()
        return info

    def create_description(self, plan: DeclarationPlan) -> WpImageDescriptionV1.proxy_class:
        """Creates the image description for `plan`; raises on refusal."""
        assert self.manager is not None
        creator: WpImageDescriptionCreatorParamsV1.proxy_class = self.manager.create_parametric_creator()
        for request, value in plan.requests():
            getattr(creator, request)(value)
        desc: WpImageDescriptionV1.proxy_class = creator.create()
        state = {"ready": False, "failed": ""}

        def on_ready(proxy, identity) -> None:  # noqa: ANN001
            state["ready"] = True

        def on_failed(proxy, cause, message) -> None:  # noqa: ANN001
            state["failed"] = message or f"cause {cause}"

        desc.dispatcher["ready"] = on_ready
        desc.dispatcher["failed"] = on_failed
        self._roundtrip()
        self._dispatch_until(lambda: state["ready"] or bool(state["failed"]))
        if state["failed"]:
            raise RuntimeError(f"the compositor refused the image description: {state['failed']}")
        return desc

    def close(self) -> None:
        try:
            self.display.flush()
            self.display.disconnect()
        except Exception:  # noqa: BLE001 - teardown must not mask the real error
            pass
