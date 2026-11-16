"""Fullscreen Wayland patch window with an explicit wp_color_manager tag.

Qt 6.12 exposes no per-surface colour management API, so verification patches
that must carry a tag are rendered by this raw-Wayland window: an xdg-shell
fullscreen toplevel on the target output, filled via a wl_shm buffer, with a
wp_color_management_surface_v1 image description set from the declaration plan.
The window is created on the session's own connection — it must only be shown
when no measurement is in flight on the panel.
"""

from __future__ import annotations

from typing import BinaryIO
import mmap
import tempfile
import time

from kelvincal.wayland_cm.cm import BIND_TIMEOUT_S, ColorManagerConnection
from kelvincal.wayland_cm.protocol.wayland import WlBuffer
from kelvincal.wayland_cm.protocol.xdg_shell import XdgWmBase
from kelvincal.wayland_cm.tags import DEFAULT_INTENT, DeclarationPlan

XRGB8888 = 0x34325258  # 'XR24' little-endian


def rgb_to_xrgb8888(rgb: tuple[int, int, int]) -> int:
    """Little-endian XRGB8888 pixel for an 8-bit RGB triple."""
    r, g, b = (v & 0xff for v in rgb)
    return r | (g << 8) | (b << 16)


def buffer_stride(width: int) -> int:
    """Row stride in bytes: 32-bit pixels on 4-byte alignment."""
    return width * 4


class TaggedPatchWindow:
    """One fullscreen tagged window on `connector`; `show()` waits for scanout."""

    def __init__(self, conn: ColorManagerConnection, connector: str, plan: DeclarationPlan,
                 settle_s: float = 0.5) -> None:
        if plan.space.name == "srgb":
            raise ValueError("the sRGB tag needs no protocol client: untagged surfaces are "
                             "assumed sRGB — use compositor-mode verification")
        self.conn = conn
        self.connector = connector
        self.plan = plan
        self.settle_s = settle_s
        self._surface = None
        self._mapped = False
        self._pool_fd: BinaryIO | None = None   # anonymous tempfile backing the shm pool
        self._pool_map: mmap.mmap | None = None
        self._pool = None
        self._buffer: WlBuffer.proxy_class | None = None
        self._buffer_w = 0
        self._buffer_h = 0
        self._cm_surface = None
        self._desc = None
        self._xdg_surface = None
        self._toplevel = None

    # -------------------------------------------------------------- lifetime

    def open(self) -> None:
        from kelvincal.wayland_cm.protocol.wayland import WlCompositor

        assert self.conn.compositor is not None and self.conn.manager is not None
        output = self.conn.output_for_connector(self.connector)

        # xdg_wm_base is not bound by ColorManagerConnection: bind it now
        wm_base = None
        for name, interface, version in self.conn._globals:  # noqa: SLF001 - same package
            if interface == XdgWmBase.name:
                wm_base = self.conn.registry.bind(name, XdgWmBase, min(version, 1))
                break
        if wm_base is None:
            raise RuntimeError("the compositor does not offer xdg_wm_base")
        wm_base.dispatcher["ping"] = lambda proxy, serial: proxy.pong(serial)

        problems = self.conn.caps.declareable(self.plan)
        if problems:
            raise RuntimeError(f"the compositor cannot declare {self.plan.space.name}: "
                                f"unsupported {', '.join(problems)}")

        surface = self.conn.compositor.create_surface()
        self._desc = self.conn.create_description(self.plan)
        self._cm_surface = self.conn.manager.get_surface(surface)
        self._cm_surface.set_image_description(self._desc, DEFAULT_INTENT)

        self._xdg_surface = wm_base.get_xdg_surface(surface)
        configured = {"serial": None}

        def on_configure(proxy, serial) -> None:  # noqa: ANN001
            configured["serial"] = serial

        self._xdg_surface.dispatcher["configure"] = on_configure
        self._toplevel = self._xdg_surface.get_toplevel()
        self._toplevel.set_title(f"KelvinCal {self.plan.space.label} verification")
        self._toplevel.set_fullscreen(output.proxy)
        self._surface = surface
        surface.commit()
        self.conn._dispatch_until(lambda: configured["serial"] is not None,  # noqa: SLF001
                                  timeout_s=BIND_TIMEOUT_S)
        assert configured["serial"] is not None
        self._xdg_surface.ack_configure(configured["serial"])

        logical_w, logical_h = self._configured_size(configured["serial"])
        scale = max(1, output.scale)
        self._allocate_buffer(logical_w * scale, logical_h * scale)
        surface.set_buffer_scale(scale)
        self._commit_fill((0, 0, 0))
        self._mapped = True

    def _configured_size(self, serial: int) -> tuple[int, int]:
        """Window size from the toplevel configure that followed the ack.

        xdg_toplevel.configure delivers (width, height, states); 0 means the
        client may pick, in which case fall back to the output's mode.
        """
        state = {"size": None}

        def on_toplevel_configure(proxy, width, height, states) -> None:  # noqa: ANN001
            if width and height:
                state["size"] = (width, height)

        assert self._toplevel is not None
        self._toplevel.dispatcher["configure"] = on_toplevel_configure
        self._toplevel.dispatcher["close"] = lambda proxy: None
        self.conn._roundtrip()  # noqa: SLF001
        output = self.conn.output_for_connector(self.connector)
        return state["size"] or (output.width // max(1, output.scale),
                                 output.height // max(1, output.scale))

    # --------------------------------------------------------------- buffer

    def _allocate_buffer(self, width: int, height: int) -> None:
        assert self.conn.shm is not None
        stride = buffer_stride(width)
        size = stride * height
        fd = tempfile.TemporaryFile()  # anonymous memfd-backed file
        fd.truncate(size)
        self._pool_fd = fd
        pool = self.conn.shm.create_pool(fd.fileno(), size)
        buffer = pool.create_buffer(0, width, height, stride, XRGB8888)
        self._pool_map = mmap.mmap(fd.fileno(), size)
        self._pool = pool
        self._buffer = buffer
        self._buffer_w, self._buffer_h = width, height

    # ----------------------------------------------------------------- show

    def show(self, rgb: tuple[int, int, int]) -> None:
        """Fills the window with `rgb` and waits until the frame is on screen."""
        assert self._mapped and self._surface is not None
        self._commit_fill(rgb)
        # frame callback: the compositor presents only after a commit is done
        presented = {"done": False}

        def on_frame(proxy, callback_data) -> None:  # noqa: ANN001
            presented["done"] = True
            proxy.destroy()

        callback = self._surface.frame()
        callback.dispatcher["done"] = on_frame
        self._surface.commit()
        self.conn._dispatch_until(lambda: presented["done"],  # noqa: SLF001
                                  timeout_s=BIND_TIMEOUT_S)
        if self.settle_s > 0:
            time.sleep(self.settle_s)

    def _commit_fill(self, rgb: tuple[int, int, int]) -> None:
        assert self._surface is not None and self._pool_map is not None and self._buffer is not None
        pixel = rgb_to_xrgb8888(rgb).to_bytes(4, "little") * self._buffer_w
        stride = buffer_stride(self._buffer_w)
        for row in range(self._buffer_h):
            self._pool_map.seek(row * stride)
            self._pool_map.write(pixel)
        self._pool_map.flush()
        self._surface.damage_buffer(0, 0, self._buffer_w, self._buffer_h)
        self._surface.attach(self._buffer, 0, 0)

    # ---------------------------------------------------------------- close

    def close(self) -> None:
        for obj in (self._toplevel, self._xdg_surface, self._cm_surface, self._buffer,
                    self._pool, self._surface):
            if obj is not None:
                try:
                    obj.destroy()
                except Exception:  # noqa: BLE001 - teardown must not mask the real error
                    pass
        if self._desc is not None:
            try:
                self._desc.destroy()
            except Exception:  # noqa: BLE001
                pass
        if self._pool_map is not None:
            self._pool_map.close()
            self._pool_map = None
        if self._pool_fd is not None:
            self._pool_fd.close()
            self._pool_fd = None
        try:
            self.conn._roundtrip()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
        self._mapped = False
