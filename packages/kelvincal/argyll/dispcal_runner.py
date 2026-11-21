"""Runs `dispcal -d dummy -C hook` while KelvinCal's Wayland patch window displays the patches.

Generates an ArgyllCMS `.cal` file containing 1D video card gamma table (`vcgt`) calibration curves for
whitepoint and tone response without touching DDC/CI hardware registers (used on internal laptop panels
such as eDP-1 or external monitors without DDC/CI).
"""

from __future__ import annotations

import os
from pathlib import Path
import pty
import re
import select
import shutil
import socket
import subprocess
import sys
import threading
from typing import Callable

from kelvincal.argyll import processes
from kelvincal.argyll.dispread_runner import PROMPT_CALIBRATE, PROMPT_PLACE, _PROMPT_RE, prompt_kind
from kelvincal.argyll.processes import PipelineCancelled, terminate
from kelvincal.core.i18n import translate
from kelvincal.core.targets import TONE_BT1886, TONE_LSTAR, TONE_SRGB

__all__ = ["DEFAULT_DISPCAL_PATCHES", "dispcal_options", "run_dispcal"]

DEFAULT_DISPCAL_PATCHES = 96  # typical patch count of `dispcal -q m` across its 4 passes
_ITER_RE = re.compile(r"Doing iteration\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)


def dispcal_options(
    *,
    gamma: float = 2.2,
    tone_curve: str = "gamma",
    whitepoint_xy: tuple[float, float] | None = None,
    target_luminance: float | None = None,
    display_type: str = "e",
    ccss_path: str | None = None,
    observer: str | None = None,
    quality: str = "m",
) -> list[str]:
    """Builds the ArgyllCMS `dispcal` CLI option list for the given target parameters."""
    from kelvincal.core.targets import adapt_whitepoint_for_observer

    opts: list[str] = [f"-q{quality}"]
    if display_type:
        opts.extend(["-y", display_type])
    if ccss_path:
        opts.extend(["-X", ccss_path])
    if observer and observer != "1931_2":
        opts.extend(["-Q", observer])
    if target_luminance is not None and target_luminance > 0:
        opts.extend(["-b", f"{target_luminance:g}"])
    wp_xy = adapt_whitepoint_for_observer(whitepoint_xy, observer)
    if wp_xy is not None:
        x, y = wp_xy
        opts.extend(["-w", f"{x:.4f},{y:.4f}"])
    if tone_curve == TONE_SRGB:
        opts.append("-gs")
    elif tone_curve == TONE_LSTAR:
        opts.append("-gl")
    elif tone_curve == TONE_BT1886:
        opts.extend(["-G", f"{gamma:g}", "-f", "0"])
    else:
        opts.extend(["-g", f"{gamma:g}"])
    return opts


def run_dispcal(
    base_path: Path,
    options: list[str],
    update_patch_fn: Callable[[tuple[int, int, int], int, int], None],
    on_status_fn: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    on_prompt: Callable[[str, str], bool] | None = None,
    estimated_patches: int = DEFAULT_DISPCAL_PATCHES,
) -> Path:
    """Runs `dispcal` into `<base_path>.cal` and returns the `.cal` path."""
    if not shutil.which("dispcal"):
        raise RuntimeError(
            translate("Errors", "ArgyllCMS tool '{tool}' was not found in PATH.").format(tool="dispcal")
        )

    staging_dir = base_path.parent
    staging_dir.mkdir(parents=True, exist_ok=True)
    sock_path = staging_dir / "dispcal_patch.sock"
    hook_script = staging_dir / "dispcal_hook.py"
    hook_script.write_text(
        "import socket, sys\n"
        f"s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        f"s.connect({str(sock_path)!r})\n"
        "s.sendall(' '.join(sys.argv[1:4]).encode('utf-8'))\n"
        "s.recv(16)\n"
        "s.close()\n",
        encoding="utf-8",
    )
    sock_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(4)
    server.setblocking(False)

    cmd = ["dispcal", "-v", "-m", "-d", "dummy", "-C", f"{sys.executable} {hook_script}", *options, str(base_path)]
    tty_master, tty_slave = pty.openpty()
    try:
        proc = subprocess.Popen(cmd, stdin=tty_slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except BaseException:
        server.close()
        os.close(tty_master)
        os.close(tty_slave)
        raise
    os.close(tty_slave)
    processes.register(proc)

    out_chunks: list[str] = []
    prompts: list[str] = []
    lock = threading.Lock()

    def drain() -> None:
        assert proc.stdout is not None
        pending = ""
        while chunk := os.read(proc.stdout.fileno(), 4096):
            text = chunk.decode("utf-8", errors="replace")
            pending += text
            with lock:
                out_chunks.append(text)
                if _PROMPT_RE.search(pending):
                    prompts.append(pending)
                    pending = ""

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()

    patch_idx = 0
    total = max(1, estimated_patches)
    try:
        while proc.poll() is None:
            if cancel_check is not None and cancel_check():
                raise PipelineCancelled()
            with lock:
                prompt = prompts.pop(0) if prompts else None
            if prompt is not None:
                if on_prompt is not None and not on_prompt(prompt_kind(prompt), prompt):
                    raise PipelineCancelled()
                os.write(tty_master, b" ")
            rlist, _, _ = select.select([server], [], [], 0.05)
            if server not in rlist:
                continue
            conn, _ = server.accept()
            try:
                parts = conn.recv(128).decode("utf-8", errors="replace").split()
                if len(parts) >= 3:
                    rgb = (int(float(parts[0])), int(float(parts[1])), int(float(parts[2])))
                    patch_idx += 1
                    total = max(total, patch_idx)
                    update_patch_fn(rgb, patch_idx, total)
                    if on_status_fn and (patch_idx == 1 or patch_idx % 8 == 0):
                        on_status_fn(
                            translate("Pipeline", "  Software calibration step {index}/{total} – RGB{rgb}").format(
                                index=patch_idx,
                                total=total,
                                rgb=rgb,
                            )
                        )
                conn.sendall(b"OK")
            finally:
                conn.close()
        proc.wait(timeout=30.0)
    except BaseException:
        terminate(proc)
        raise
    finally:
        processes.unregister(proc)
        server.close()
        sock_path.unlink(missing_ok=True)
        os.close(tty_master)
        reader.join(timeout=5.0)
        assert proc.stdout is not None
        proc.stdout.close()

    full_out = "".join(out_chunks)
    if proc.returncode != 0:
        raise RuntimeError(
            translate("Errors", "{tool} failed (exit code {code}):\n{output}").format(
                tool="dispcal", code=proc.returncode, output=full_out
            )
        )
    cal_path = base_path.with_suffix(".cal")
    if not cal_path.is_file():
        raise RuntimeError(
            translate("Errors", "dispcal did not create the expected calibration file: {path}").format(path=cal_path)
        )
    return cal_path
