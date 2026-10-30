"""Component 2 (Backend): Orchestration of the ArgyllCMS pipeline (targen -> dispread -> colprof)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable

from kcal_core.i18n import translate
from kcal_core.paths import user_icc_dir


PATCH_PROGRESS_RE = re.compile(r"patch\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)


class PipelineCancelled(Exception):
    """Raised when a running pipeline was cancelled through `cancel_check`."""


def _terminate(proc: subprocess.Popen) -> None:
    """Terminates an ArgyllCMS child process (SIGTERM, then SIGKILL after 3 s)."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def targen_layout(patch_count: int) -> tuple[int, int, int]:
    """Returns (single_steps -s, gray_steps -g, multi_steps -m) for a targen run with `-f patch_count`.

    `-f` is the total patch count, so every fixed patch (gray ramp, cube grid) is taken from the
    adaptive full-spread budget. The fixed share is kept small: about 20 % gray steps (17..52) and a
    coarse cube grid, so that roughly 60 % of a 175-patch set remains for `-G` optimized spread patches.
    """
    gray_steps = max(17, min(52, round(patch_count * 0.2)))
    if patch_count >= 800:
        multi_steps = 5
    elif patch_count >= 400:
        multi_steps = 4
    elif patch_count >= 100:
        multi_steps = 3
    else:
        multi_steps = 2
    return 5, gray_steps, multi_steps


@dataclass
class ProfileConfig:
    """Configuration for a display calibration and profiling run."""

    monitor_name: str
    patch_count: int = 175              # Number of test patches for targen (-f)
    gamma: float = 2.2
    profile_quality: str = "h"          # colprof -q (l=low, m=medium, h=high, u=ultra)
    profile_type: str = "X"             # colprof -a (X = XYZ cLUT + Matrix, M = Matrix)
    display_type: str = "l"             # dispread -y (l = LCD non-refresh)
    ccss_path: str | None = None
    output_dir: Path = field(default_factory=user_icc_dir)


@dataclass
class StagedProfile:
    """Holds a newly generated ICC profile and its .ti3 measurements in a temporary staging directory."""

    staging_dir: Path
    staged_icc_path: Path
    ti3_path: Path
    suggested_output_path: Path

    def save_to(self, destination: Path | None = None) -> Path:
        """Copies the staged ICC profile to its final destination and cleans up the staging directory."""
        dest = destination or self.suggested_output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.staged_icc_path, dest)
        self.cleanup()
        return dest

    def cleanup(self) -> None:
        """Removes the temporary staging directory."""
        shutil.rmtree(self.staging_dir, ignore_errors=True)


class CalibrationPipeline:
    """Drives targen, dispread (-d dummy -C), and colprof to generate an ICC profile."""

    def __init__(self, config: ProfileConfig) -> None:
        self.config = config

    def generate_staged_profile(
        self,
        update_patch_fn: Callable[[tuple[int, int, int], int, int], None],
        on_status_fn: Callable[[str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        on_measurement_finished: Callable[[], None] | None = None,
        review_measurements: Callable[[Path], None] | None = None,
    ) -> StagedProfile:
        """Executes Phase 2 (patch measurement) and Phase 3 (ICC profile generation) in a staging folder.

        `cancel_check` is polled while dispread/colprof run; when it returns True the running ArgyllCMS
        process is terminated and `PipelineCancelled` is raised. `on_measurement_finished` is called
        once dispread has completed, right before colprof starts. `review_measurements(ti3_path)` runs
        between both; it may correct the .ti3 in place or raise `PipelineCancelled`.
        """
        def _cancelled() -> bool:
            return cancel_check is not None and cancel_check()

        for tool in ("targen", "dispread", "colprof"):
            if not shutil.which(tool):
                raise RuntimeError(translate("Errors", "ArgyllCMS tool '{tool}' was not found in PATH.").format(tool=tool))

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        safe_name = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in self.config.monitor_name
        )
        base_name = f"KelvinCal_{safe_name}_{timestamp}"

        staging_dir = Path(tempfile.mkdtemp(prefix="kelvincal_stage_"))
        try:
            base_path = staging_dir / base_name
            sock_path = staging_dir / "patch.sock"
            hook_script = staging_dir / "patch_hook.py"

            # Small hook script invoked synchronously by `dispread -C` for each patch with "R G B Rf Gf Bf"
            hook_script.write_text(
                "import socket, sys\n"
                f"s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                f"s.connect({str(sock_path)!r})\n"
                "s.sendall(' '.join(sys.argv[1:4]).encode('utf-8'))\n"
                "s.recv(16)\n"
                "s.close()\n",
                encoding="utf-8",
            )

            # 1. targen: fixed gray ramp + small cube grid, remaining budget as adaptive full-spread patches (-G)
            if on_status_fn:
                on_status_fn(
                    translate("Pipeline", "Generating {count} test patches with targen...").format(
                        count=self.config.patch_count
                    )
                )
            single_steps, gray_steps, multi_steps = targen_layout(self.config.patch_count)

            subprocess.run(
                [
                    "targen",
                    "-v",
                    "-d",
                    "3",  # RGB Display
                    "-G",  # Good-fit (farthest point) distribution
                    "-e",
                    "4",  # White patches
                    "-B",
                    "1",  # Black patches
                    "-s",
                    str(single_steps),
                    "-g",
                    str(gray_steps),
                    "-m",
                    str(multi_steps),
                    "-f",
                    str(self.config.patch_count),
                    str(base_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            # Read actual patch count from generated .ti1 file (NUMBER_OF_SETS)
            total_patches = self.config.patch_count
            ti1_file = staging_dir / f"{base_name}.ti1"
            if ti1_file.exists():
                m_sets = re.search(
                    r"^NUMBER_OF_SETS\s+(\d+)",
                    ti1_file.read_text(encoding="utf-8", errors="replace"),
                    re.MULTILINE,
                )
                if m_sets:
                    total_patches = int(m_sets.group(1))

            # 2. dispread: Measure patches synchronously via local Unix domain socket + Wayland PatchWindow
            if on_status_fn:
                on_status_fn(
                    translate(
                        "Pipeline",
                        "Starting measurement ({count} patches, -g {gray} -m {multi}) with dispread...",
                    ).format(count=total_patches, gray=gray_steps, multi=multi_steps)
                )

            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(sock_path))
            server.listen(4)
            server.setblocking(False)

            hook_cmd = f"{sys.executable} {hook_script}"
            dispread_cmd = [
                "dispread",
                "-v",
                "-d",
                "dummy",
                "-C",
                hook_cmd,
                "-Y",
                "p",  # Sensor is already placed on screen; skip interactive prompt
                "-y",
                self.config.display_type,
            ]
            if self.config.ccss_path:
                dispread_cmd.extend(["-X", self.config.ccss_path])
            dispread_cmd.append(str(base_path))

            proc = subprocess.Popen(
                dispread_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            patch_idx = 0
            out_chunks: list[str] = []
            # Drain dispread's verbose output continuously; an unread pipe would block dispread once full.
            assert proc.stdout is not None
            drain = threading.Thread(
                target=lambda: out_chunks.extend(iter(proc.stdout.readline, "")), daemon=True
            )
            drain.start()

            try:
                while proc.poll() is None:
                    if _cancelled():
                        raise PipelineCancelled()
                    rlist, _, _ = select.select([server], [], [], 0.05)
                    if server in rlist:
                        conn, _ = server.accept()
                        try:
                            data = conn.recv(128).decode("utf-8", errors="replace").strip()
                            parts = data.split()
                            if len(parts) >= 3:
                                rgb = (int(float(parts[0])), int(float(parts[1])), int(float(parts[2])))
                                patch_idx += 1
                                update_patch_fn(rgb, patch_idx, total_patches)
                                if on_status_fn and (
                                    patch_idx == 1
                                    or patch_idx % 10 == 0
                                    or patch_idx == total_patches
                                ):
                                    on_status_fn(
                                        translate(
                                            "Pipeline", "  Measuring patch {index}/{total} ({pct}%) – RGB{rgb}"
                                        ).format(
                                            index=patch_idx,
                                            total=total_patches,
                                            pct=patch_idx * 100 // max(1, total_patches),
                                            rgb=rgb,
                                        )
                                    )
                            conn.sendall(b"OK")
                        finally:
                            conn.close()
            except BaseException:
                _terminate(proc)
                raise
            finally:
                server.close()

            proc.wait(timeout=30.0)
            drain.join(timeout=5.0)
            full_out = "".join(out_chunks)

            if proc.returncode != 0:
                raise RuntimeError(translate("Errors", "{tool} failed (exit code {code}):\n{output}").format(
                    tool="dispread", code=proc.returncode, output=full_out))

            staged_icc = staging_dir / f"{base_name}.icc"
            ti3_file = staging_dir / f"{base_name}.ti3"
            if review_measurements:
                review_measurements(ti3_file)
            if on_measurement_finished:
                on_measurement_finished()

            # 3. colprof: Compute the ICC profile inside the staging folder
            if on_status_fn:
                on_status_fn(
                    translate(
                        "Pipeline", "Computing 3D-LUT / Matrix ICC profile with colprof ({name})..."
                    ).format(name=staged_icc.name)
                )
            colprof = subprocess.Popen(
                [
                    "colprof",
                    f"-q{self.config.profile_quality}",
                    f"-a{self.config.profile_type}",
                    "-D",
                    f"KelvinCal {self.config.monitor_name} ({timestamp})",
                    "-O",
                    str(staged_icc),
                    str(base_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                while colprof.poll() is None:
                    if _cancelled():
                        raise PipelineCancelled()
                    time.sleep(0.1)
            except BaseException:
                _terminate(colprof)
                raise
            colprof_out, _ = colprof.communicate()
            if colprof.returncode != 0:
                raise RuntimeError(translate("Errors", "{tool} failed (exit code {code}):\n{output}").format(
                    tool="colprof", code=colprof.returncode, output=colprof_out))

            if not staged_icc.exists():
                raise RuntimeError(translate("Errors", "The ICC profile was not created at {path}.").format(path=staged_icc))

            suggested_out = self.config.output_dir / f"{base_name}.icc"
            return StagedProfile(
                staging_dir=staging_dir,
                staged_icc_path=staged_icc,
                ti3_path=ti3_file,
                suggested_output_path=suggested_out,
            )
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
