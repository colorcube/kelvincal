"""Runs `dispread -d dummy -C hook` while KelvinCal's own (Wayland) patch window shows the patches.

dispread calls the hook for every patch; the hook passes the RGB value over a Unix socket and blocks until
the patch is on screen. dispread's stdin is a pseudo-terminal so that its interactive prompts (instrument
calibration, "place instrument on test window") can be answered by the caller instead of the console.
"""

from __future__ import annotations

import os
from pathlib import Path
import pty
import re
import select
import socket
import subprocess
import sys
import threading
from typing import Callable

from kelvincal.argyll import processes
from kelvincal.argyll.processes import PipelineCancelled, terminate
from kelvincal.core.i18n import translate

__all__ = ["PipelineCancelled", "run_dispread", "terminate"]

_PROMPT_RE = re.compile(r"any (other )?key to continue", re.IGNORECASE)
_CALIBRATION_RE = re.compile(r"calibrat|cap on|reference|dark surface", re.IGNORECASE)

PROMPT_CALIBRATE = "calibrate"   # instrument calibration (e.g. i1 Pro on its tile / cap)
PROMPT_PLACE = "place"           # place the instrument on the screen


def prompt_kind(text: str) -> str:
    """Classifies an ArgyllCMS console prompt (the text since the previous prompt).

    Only the prompt itself counts (from its last "Place ..." line on): status lines before it such as
    "Calibration complete" must not turn the placement prompt into a calibration prompt.
    """
    start = text.rfind("Place ")
    return PROMPT_CALIBRATE if _CALIBRATION_RE.search(text[start:] if start >= 0 else text) else PROMPT_PLACE


def run_argyll_with_patch_hook(
    cmd_builder: Callable[[str], list[str]],
    staging_dir: Path,
    tool_name: str,
    on_rgb: Callable[[tuple[int, int, int], int], None],
    cancel_check: Callable[[], bool] | None = None,
    on_prompt: Callable[[str, str], bool] | None = None,
    sock_name: str = "patch.sock",
    hook_name: str = "patch_hook.py",
) -> str:
    """Runs an ArgyllCMS tool (`dispread` or `dispcal`) with `-d dummy -C hook` inside a PTY.

    The hook script passes each patch's RGB values over a Unix domain socket and blocks until `on_rgb`
    has updated the Wayland patch window. Interactive console prompts on the PTY are answered via
    `on_prompt(kind, text)` (or confirmed with Space if `on_prompt` is None).
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    sock_path = staging_dir / sock_name
    hook_script = staging_dir / hook_name
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

    cmd = cmd_builder(f"{sys.executable} {hook_script}")
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
        # Read unbuffered: prompts do not end with a newline. An unread pipe would block the tool once full.
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
                    on_rgb(rgb, patch_idx)
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
        raise RuntimeError(translate("Errors", "{tool} failed (exit code {code}):\n{output}").format(
            tool=tool_name, code=proc.returncode, output=full_out))
    return full_out


def run_dispread(
    base_path: Path,
    options: list[str],
    total_patches: int,
    update_patch_fn: Callable[[tuple[int, int, int], int, int], None],
    on_status_fn: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    on_prompt: Callable[[str, str], bool] | None = None,
) -> str:
    """Measures `<base_path>.ti1` into `<base_path>.ti3`; returns dispread's output.

    `on_prompt(kind, text)` answers interactive prompts (see `prompt_kind`); True continues, False cancels.
    Without it every prompt is confirmed (the sensor is expected to be placed already).
    """
    def on_rgb(rgb: tuple[int, int, int], patch_idx: int) -> None:
        update_patch_fn(rgb, patch_idx, total_patches)
        if on_status_fn and (patch_idx == 1 or patch_idx % 10 == 0 or patch_idx == total_patches):
            on_status_fn(
                translate("Pipeline", "  Measuring patch {index}/{total} ({pct}%) – RGB{rgb}").format(
                    index=patch_idx,
                    total=total_patches,
                    pct=patch_idx * 100 // max(1, total_patches),
                    rgb=rgb,
                )
            )

    return run_argyll_with_patch_hook(
        cmd_builder=lambda hook_cmd: ["dispread", "-v", "-d", "dummy", "-C", hook_cmd, *options, str(base_path)],
        staging_dir=base_path.parent,
        tool_name="dispread",
        on_rgb=on_rgb,
        cancel_check=cancel_check,
        on_prompt=on_prompt,
    )
