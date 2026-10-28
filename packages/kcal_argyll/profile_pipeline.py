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
    profile_quality: str = "m"          # colprof -q (l=low, m=medium, h=high, u=ultra)
    profile_type: str = "X"             # colprof -a (X = XYZ cLUT + Matrix, M = Matrix)
    display_type: str = "l"             # dispread -y (l = LCD non-refresh)
    ccss_path: str | None = None
    output_dir: Path = field(default_factory=lambda: Path.home() / ".local" / "share" / "icc")


class CalibrationPipeline:
    """Drives targen, dispread (-d dummy -C), and colprof to generate an ICC profile."""

    def __init__(self, config: ProfileConfig) -> None:
        self.config = config

    def generate_icc_profile(
        self,
        update_patch_fn: Callable[[tuple[int, int, int], int, int], None] | Callable[[tuple[int, int, int]], None],
        on_status_fn: Callable[[str], None] | None = None,
    ) -> Path:
        """Executes Phase 2 (patch measurement) and Phase 3 (ICC profile generation)."""
        for tool in ("targen", "dispread", "colprof"):
            if not shutil.which(tool):
                raise RuntimeError(f"ArgyllCMS tool '{tool}' was not found in PATH.")

        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        safe_name = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in self.config.monitor_name
        )
        base_name = f"KelvinCal_{safe_name}_{timestamp}"

        with tempfile.TemporaryDirectory(prefix="kelvincal_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            base_path = tmp_dir / base_name
            sock_path = tmp_dir / "patch.sock"
            hook_script = tmp_dir / "patch_hook.py"

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

            # 1. targen: Generate test patch set (.ti1)
            if on_status_fn:
                on_status_fn(f"Generating {self.config.patch_count} test patches with targen...")
            gray_steps = min(16, max(2, self.config.patch_count // 4))
            subprocess.run(
                [
                    "targen",
                    "-d",
                    "3",  # RGB Display
                    "-G",
                    "-e",
                    "2",  # White patches
                    "-B",
                    "2",  # Black patches
                    "-s",
                    str(gray_steps),
                    "-f",
                    str(self.config.patch_count),
                    str(base_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            # 2. dispread: Measure patches synchronously via local Unix domain socket + Wayland PatchWindow
            if on_status_fn:
                on_status_fn(
                    f"Starting measurement ({self.config.patch_count} patches) with dispread..."
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
            total_patches = self.config.patch_count
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

            # 3. colprof: Compute the ICC profile
            final_icc = self.config.output_dir / f"{base_name}.icc"
            if on_status_fn:
                on_status_fn(f"Computing 3D-LUT / Matrix ICC profile with colprof ({final_icc.name})...")
            subprocess.run(
                [
                    "colprof",
                    f"-q{self.config.profile_quality}",
                    f"-a{self.config.profile_type}",
                    "-D",
                    f"KelvinCal {self.config.monitor_name} ({timestamp})",
                    "-O",
                    str(final_icc),
                    str(base_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        if not final_icc.exists():
            raise RuntimeError(f"ICC profile was not created at {final_icc}.")
        return final_icc
