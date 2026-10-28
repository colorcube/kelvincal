"""Protocol client for `dispread -dweb:<port>` to couple with our native Wayland Qt 6 patch window."""

from __future__ import annotations

import http.client
import random
import re
import time
from typing import Callable


HEX_COLOR_RE = re.compile(r"#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})")


def parse_dweb_color(response_text: str) -> tuple[str, tuple[int, int, int]] | None:
    """Parses the response from `dispread -dweb` (`/ajax/messages`), e.g. `\\r\\n#808080`.

    Returns:
        Tuple `(hex_string, (r, g, b))` or `None` if no hex color is present.
    """
    cleaned = response_text.strip()
    m = HEX_COLOR_RE.search(cleaned)
    if not m:
        return None
    r = int(m.group(1), 16)
    g = int(m.group(2), 16)
    b = int(m.group(3), 16)
    hex_str = f"#{m.group(1).lower()}{m.group(2).lower()}{m.group(3).lower()}"
    return (hex_str, (r, g, b))


class DispreadWebClient:
    """Connects to the built-in HTTP server of `dispread -dweb:<port>` and forwards patch colors."""

    def __init__(
        self,
        port: int = 8080,
        host: str = "127.0.0.1",
        frame_settle_s: float = 0.08,
    ) -> None:
        self.host = host
        self.port = port
        self.frame_settle_s = frame_settle_s

    def run_loop(
        self,
        update_patch_fn: Callable[[tuple[int, int, int]], None],
        is_dispread_alive_fn: Callable[[], bool],
    ) -> int:
        """Loops over all measurement patches until `dispread` exits after the final patch."""
        current_hex = "#808080"
        update_patch_fn((128, 128, 128))
        patches_displayed = 0
        first_request = True

        deadline = time.monotonic() + 10.0
        while is_dispread_alive_fn() and time.monotonic() < deadline:
            try:
                conn = http.client.HTTPConnection(self.host, self.port, timeout=30.0)
                conn.connect()
                conn.close()
                break
            except OSError:
                time.sleep(0.1)

        while is_dispread_alive_fn():
            if first_request:
                path = f"/ajax/messages?{current_hex}"
                first_request = False
            else:
                path = f"/ajax/messages?{current_hex}%20{random.random():.8f}"

            try:
                conn = http.client.HTTPConnection(self.host, self.port, timeout=60.0)
                conn.request("GET", path)
                resp = conn.getresponse()
                if resp.status != 200:
                    conn.close()
                    break
                body = resp.read().decode("utf-8", errors="replace")
                conn.close()
            except OSError:
                break

            parsed = parse_dweb_color(body)
            if parsed is None:
                continue

            new_hex, rgb = parsed
            current_hex = new_hex
            update_patch_fn(rgb)
            patches_displayed += 1

            if self.frame_settle_s > 0:
                time.sleep(self.frame_settle_s)

        return patches_displayed
