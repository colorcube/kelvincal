"""Runs `dispcal -d dummy -C hook` while KelvinCal's Wayland patch window displays the patches.

Generates an ArgyllCMS `.cal` file containing 1D video card gamma table (`vcgt`) calibration curves for
whitepoint and tone response without touching DDC/CI hardware registers (used on internal laptop panels
such as eDP-1 or external monitors without DDC/CI).
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Callable

from kelvincal.argyll.dispread_runner import run_argyll_with_patch_hook
from kelvincal.core.i18n import translate
from kelvincal.core.targets import TONE_BT1886, TONE_LSTAR, TONE_SRGB

__all__ = ["DEFAULT_DISPCAL_PATCHES", "dispcal_options", "run_dispcal"]

DEFAULT_DISPCAL_PATCHES = 96  # typical patch count of `dispcal -q m` across its 4 passes


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
    from kelvincal.argyll.dispread_runner import run_argyll_with_patch_hook

    if not shutil.which("dispcal"):
        raise RuntimeError(
            translate("Errors", "ArgyllCMS tool '{tool}' was not found in PATH.").format(tool="dispcal")
        )

    def on_rgb(rgb: tuple[int, int, int], patch_idx: int) -> None:
        total = max(1, estimated_patches, patch_idx)
        update_patch_fn(rgb, patch_idx, total)
        if on_status_fn and (patch_idx == 1 or patch_idx % 8 == 0):
            on_status_fn(
                translate("Pipeline", "  Software calibration step {index}/{total} – RGB{rgb}").format(
                    index=patch_idx,
                    total=total,
                    rgb=rgb,
                )
            )

    run_argyll_with_patch_hook(
        cmd_builder=lambda hook_cmd: ["dispcal", "-v", "-m", "-d", "dummy", "-C", hook_cmd, *options, str(base_path)],
        staging_dir=base_path.parent,
        tool_name="dispcal",
        on_rgb=on_rgb,
        cancel_check=cancel_check,
        on_prompt=on_prompt,
        sock_name="dispcal_patch.sock",
        hook_name="dispcal_hook.py",
    )
    cal_path = base_path.with_suffix(".cal")
    if not cal_path.is_file():
        raise RuntimeError(
            translate("Errors", "dispcal did not create the expected calibration file: {path}").format(path=cal_path)
        )
    return cal_path
