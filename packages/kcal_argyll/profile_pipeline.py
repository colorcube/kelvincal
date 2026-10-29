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
from typing import Callable


PATCH_PROGRESS_RE = re.compile(r"patch\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)


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
    output_dir: Path = field(default_factory=lambda: Path.home() / ".local" / "share" / "icc")


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
        update_patch_fn: Callable[[tuple[int, int, int], int, int], None] | Callable[[tuple[int, int, int]], None],
        on_status_fn: Callable[[str], None] | None = None,
    ) -> StagedProfile:
        """Executes Phase 2 (patch measurement) and Phase 3 (ICC profile generation) in a staging folder."""
        for tool in ("targen", "dispread", "colprof"):
            if not shutil.which(tool):
                raise RuntimeError(f"ArgyllCMS tool '{tool}' was not found in PATH.")

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

            # 1. targen: Generate test patch set (.ti1) with dense neutral gray ramp (-g 52 at 175 patches),
            # 3D multi-dimensional cube grid (-m 5), and single-channel steps (-s 5)
            if on_status_fn:
                on_status_fn(f"Generating {self.config.patch_count} test patches with targen...")
            if self.config.patch_count >= 175:
                gray_steps = 52
                single_steps = 5
                multi_steps = 5
            elif self.config.patch_count >= 100:
                gray_steps = max(24, int(round(self.config.patch_count * 52 / 175)))
                single_steps = 5
                multi_steps = 4
            else:
                gray_steps = max(12, self.config.patch_count // 3)
                single_steps = 4
                multi_steps = 3

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
                    f"Starting measurement ({total_patches} patches, -g {gray_steps} -m {multi_steps}) with dispread..."
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

            try:
                while proc.poll() is None:
                    rlist, _, _ = select.select([server], [], [], 0.05)
                    if server in rlist:
                        conn, _ = server.accept()
                        try:
                            data = conn.recv(128).decode("utf-8", errors="replace").strip()
                            parts = data.split()
                            if len(parts) >= 3:
                                rgb = (int(float(parts[0])), int(float(parts[1])), int(float(parts[2])))
                                patch_idx += 1
                                try:
                                    update_patch_fn(rgb, patch_idx, total_patches)  # type: ignore[call-arg]
                                except TypeError:
                                    update_patch_fn(rgb)  # type: ignore[call-arg]
                                if on_status_fn and (
                                    patch_idx == 1
                                    or patch_idx % 10 == 0
                                    or patch_idx == total_patches
                                ):
                                    on_status_fn(
                                        f"  Measuring patch {patch_idx}/{total_patches} "
                                        f"({patch_idx * 100 // max(1, total_patches)}%) – RGB{rgb}"
                                    )
                            conn.sendall(b"OK")
                        finally:
                            conn.close()
            finally:
                server.close()

            rem_out, _ = proc.communicate(timeout=30.0)
            if rem_out:
                out_chunks.append(rem_out)
            full_out = "".join(out_chunks)

            if proc.returncode != 0:
                raise RuntimeError(
                    f"dispread failed (exit code {proc.returncode}):\n{full_out}"
                )

            # 3. colprof: Compute the ICC profile inside the staging folder
            staged_icc = staging_dir / f"{base_name}.icc"
            ti3_file = staging_dir / f"{base_name}.ti3"
            if on_status_fn:
                on_status_fn(f"Computing 3D-LUT / Matrix ICC profile with colprof ({staged_icc.name})...")
            subprocess.run(
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
                check=True,
                capture_output=True,
                text=True,
            )

            if not staged_icc.exists():
                raise RuntimeError(f"ICC profile was not created at {staged_icc}.")

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

    def generate_icc_profile(
        self,
        update_patch_fn: Callable[[tuple[int, int, int], int, int], None] | Callable[[tuple[int, int, int]], None],
        on_status_fn: Callable[[str], None] | None = None,
    ) -> Path:
        """Executes Phase 2+3 and immediately saves the ICC profile to `config.output_dir`."""
        staged = self.generate_staged_profile(
            update_patch_fn=update_patch_fn, on_status_fn=on_status_fn
        )
        return staged.save_to()
