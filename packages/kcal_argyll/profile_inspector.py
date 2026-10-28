"""ICC profile and ArgyllCMS .ti3 measurement inspector with kink/discontinuity detection."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import struct

from kcal_core.models import ColorMeasurement


@dataclass(frozen=True)
class GrayRampPoint:
    """A single neutral grayscale measurement point (R == G == B) from a .ti3 dataset."""

    input_pct: float          # 0.0 .. 100.0
    X: float
    Y: float
    Z: float
    norm_y: float             # Black-compensated normalized Y in 0.0 .. 1.0
    ideal_y: float            # Ideal (input_pct / 100) ** gamma
    delta_uv_to_white: float  # Chromaticity drift relative to measured whitepoint


@dataclass(frozen=True)
class KinkWarning:
    """Represents a detected discontinuity, reversal, or kink ('Knick') in a tone curve."""

    channel: str              # "Gray", "R", "G", "B", or "GrayBalance"
    input_pct: float          # Input signal level (0..100%) where the anomaly occurs
    severity: str             # "warning" or "error"
    message_en: str
    message_de: str


@dataclass
class ProfileInspection:
    """Complete analysis result of an ICC profile and/or ArgyllCMS .ti3 measurement file."""

    profile_path: Path
    description: str
    white_xyz: tuple[float, float, float] | None = None
    black_xyz: tuple[float, float, float] | None = None
    luminance_cdm2: float | None = None
    black_luminance_cdm2: float | None = None
    contrast_ratio: float | None = None
    white_cct_kelvin: float | None = None
    white_xy: tuple[float, float] | None = None
    white_delta_uv_d65: float | None = None
    effective_gamma: float | None = None
    target_gamma: float = 2.2

    # Tone response curves normalized to 0..1 over N evenly spaced samples (default 256)
    r_trc: list[float] = field(default_factory=list)
    g_trc: list[float] = field(default_factory=list)
    b_trc: list[float] = field(default_factory=list)

    # Measured .ti3 grayscale ramp and per-channel points (if .ti3 or embedded 'targ' tag available)
    gray_ramp: list[GrayRampPoint] = field(default_factory=list)
    total_measured_patches: int = 0

    # Kink / discontinuity analysis
    kinks: list[KinkWarning] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(k.severity == "error" for k in self.kinks)

    @property
    def is_clean(self) -> bool:
        return len(self.kinks) == 0


def _parse_icc_tags(data: bytes) -> dict[bytes, bytes]:
    """Extracts raw tag payloads keyed by 4-byte signature from an ICC v2/v4 binary."""
    if len(data) < 132:
        return {}
    tag_count = struct.unpack(">I", data[128:132])[0]
    if tag_count > 200 or 132 + tag_count * 12 > len(data):
        return {}
    tags: dict[bytes, bytes] = {}
    for i in range(tag_count):
        pos = 132 + i * 12
        sig, offset, size = struct.unpack(">4sII", data[pos : pos + 12])
        if offset + size <= len(data) and size >= 8:
            tags[sig] = data[offset : offset + size]
    return tags


def _decode_xyz_tag(payload: bytes) -> tuple[float, float, float] | None:
    if len(payload) < 20 or payload[:4] != b"XYZ ":
        return None
    x_raw, y_raw, z_raw = struct.unpack(">iii", payload[8:20])
    return (x_raw / 65536.0, y_raw / 65536.0, z_raw / 65536.0)


def _decode_desc_tag(payload: bytes) -> str | None:
    tag_type = payload[:4]
    if tag_type == b"desc" and len(payload) >= 12:
        str_len = struct.unpack(">I", payload[8:12])[0]
        raw = payload[12 : 12 + max(0, str_len - 1)]
        return raw.decode("latin-1", errors="replace").strip("\x00").strip()
    if tag_type == b"mluc" and len(payload) >= 28:
        rec_count = struct.unpack(">I", payload[8:12])[0]
        if rec_count >= 1:
            str_len, str_off = struct.unpack(">II", payload[20:28])
            if str_off + str_len <= len(payload):
                return (
                    payload[str_off : str_off + str_len]
                    .decode("utf-16-be", errors="replace")
                    .strip("\x00")
                    .strip()
                )
    return None


def _decode_text_tag(payload: bytes) -> str | None:
    if len(payload) < 8 or payload[:4] != b"text":
        return None
    return payload[8:].decode("latin-1", errors="replace").rstrip("\x00")


def _decode_trc_tag(payload: bytes, num_samples: int = 256) -> list[float]:
    """Decodes an ICC 'curv' or 'para' tag into `num_samples` normalized [0..1] values."""
    tag_type = payload[:4]
    if tag_type == b"curv" and len(payload) >= 12:
        count = struct.unpack(">I", payload[8:12])[0]
        if count == 0:
            return [i / (num_samples - 1) for i in range(num_samples)]
        if count == 1 and len(payload) >= 14:
            gamma = struct.unpack(">H", payload[12:14])[0] / 256.0
            return [(i / (num_samples - 1)) ** gamma for i in range(num_samples)]
        if count > 1 and len(payload) >= 12 + count * 2:
            vals = struct.unpack(f">{count}H", payload[12 : 12 + count * 2])
            return [v / 65535.0 for v in vals]
    elif tag_type == b"para" and len(payload) >= 16:
        func_type = struct.unpack(">H", payload[8:10])[0]
        n_params = {0: 1, 1: 3, 2: 4, 3: 5, 4: 7}.get(func_type, 1)
        if len(payload) >= 12 + n_params * 4:
            params = [
                v / 65536.0
                for v in struct.unpack(f">{n_params}i", payload[12 : 12 + n_params * 4])
            ]
            g = max(0.1, params[0])
            out: list[float] = []
            for i in range(num_samples):
                x = i / (num_samples - 1)
                if func_type == 0:
                    y = x**g
                elif func_type == 3 and len(params) >= 5:
                    a, b, c, d = params[1], params[2], params[3], params[4]
                    y = (a * x + b) ** g if x >= d else c * x
                else:
                    y = x**g
                out.append(max(0.0, min(1.0, y)))
            return out
    return []


def parse_ti3_text(ti3_text: str) -> list[tuple[float, float, float, float, float, float]]:
    """Parses ArgyllCMS .ti3 text and returns rows of (R, G, B, X, Y, Z) with RGB in 0..100."""
    lines = ti3_text.splitlines()
    in_format = False
    in_data = False
    fields: list[str] = []
    raw_rows: list[tuple[float, float, float, float, float, float]] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "BEGIN_DATA_FORMAT":
            in_format = True
            continue
        if line == "END_DATA_FORMAT":
            in_format = False
            continue
        if line == "BEGIN_DATA":
            in_data = True
            continue
        if line == "END_DATA":
            in_data = False
            break

        if in_format:
            fields.extend(line.split())
        elif in_data and fields:
            parts = line.split()
            if len(parts) < len(fields):
                continue
            row_map = dict(zip(fields, parts))
            try:
                r = float(row_map["RGB_R"])
                g = float(row_map["RGB_G"])
                b = float(row_map["RGB_B"])
                x = float(row_map["XYZ_X"])
                y = float(row_map["XYZ_Y"])
                z = float(row_map["XYZ_Z"])
                raw_rows.append((r, g, b, x, y, z))
            except (KeyError, ValueError):
                continue

    if not raw_rows:
        return []

    max_rgb = max(max(r[0], r[1], r[2]) for r in raw_rows)
    scale = (100.0 / max_rgb) if max_rgb > 100.5 else 1.0
    return [(r * scale, g * scale, b * scale, x, y, z) for (r, g, b, x, y, z) in raw_rows]


def _detect_trc_kinks(channel: str, trc: list[float]) -> list[KinkWarning]:
    """Checks an ICC tone response curve for non-monotonic reversals or sharp kinks."""
    warnings: list[KinkWarning] = []
    n = len(trc)
    if n < 16:
        return warnings

    for i in range(1, n):
        diff = trc[i] - trc[i - 1]
        if diff < -0.0015:
            pct = i * 100.0 / (n - 1)
            warnings.append(
                KinkWarning(
                    channel=channel,
                    input_pct=pct,
                    severity="error",
                    message_en=(
                        f"{channel} TRC reversal at {pct:.1f}% input "
                        f"(output drops by {abs(diff) * 100:.2f}%)."
                    ),
                    message_de=(
                        f"{channel}-Kurvenknick (Rückläufigkeit) bei {pct:.1f}% Signalpegel "
                        f"(Ausgang fällt um {abs(diff) * 100:.2f}% ab)."
                    ),
                )
            )
            break

    # Check second derivative on a 32-step subsampled grid to detect localized kinks
    step = max(1, (n - 1) // 32)
    pts = [trc[idx] for idx in range(0, n, step)]
    slopes = [pts[i + 1] - pts[i] for i in range(len(pts) - 1)]
    for i in range(2, len(slopes) - 2):
        local_ref = 0.5 * (slopes[i - 1] + slopes[i + 1])
        jump = abs(slopes[i] - local_ref)
        if jump > 0.025 and jump > 2.8 * max(0.002, abs(slopes[i - 1] - slopes[i - 2])):
            pct = (i * step) * 100.0 / (n - 1)
            warnings.append(
                KinkWarning(
                    channel=channel,
                    input_pct=pct,
                    severity="warning",
                    message_en=(
                        f"{channel} TRC slope discontinuity ('kink') near {pct:.0f}% input."
                    ),
                    message_de=(
                        f"{channel}-Tonwertkurve zeigt einen Steigungsknick nahe {pct:.0f}%."
                    ),
                )
            )
            break

    return warnings


def _analyze_gray_ramp(
    rows: list[tuple[float, float, float, float, float, float]],
    target_gamma: float = 2.2,
) -> tuple[list[GrayRampPoint], list[KinkWarning], float | None]:
    """Extracts neutral grayscale ramp points, checks for measurement kinks, and estimates effective gamma."""
    neutral = [r for r in rows if abs(r[0] - r[1]) < 0.25 and abs(r[1] - r[2]) < 0.25]
    if len(neutral) < 3:
        return [], [], None

    # Group repeated patches (e.g. multiple black/white patches) by rounded input level
    grouped: dict[float, list[tuple[float, float, float, float, float, float]]] = {}
    for row in neutral:
        key = round(row[0], 2)
        grouped.setdefault(key, []).append(row)

    avg_rows: list[tuple[float, float, float, float]] = []
    for pct in sorted(grouped.keys()):
        grp = grouped[pct]
        m = len(grp)
        avg_x = sum(g[3] for g in grp) / m
        avg_y = sum(g[4] for g in grp) / m
        avg_z = sum(g[5] for g in grp) / m
        avg_rows.append((pct, avg_x, avg_y, avg_z))

    y_min = avg_rows[0][2]
    y_max = avg_rows[-1][2]
    _, wx, wy, wz = avg_rows[-1]
    white_meas = ColorMeasurement(rgb=(255, 255, 255), X=wx, Y=wy, Z=wz)
    wu, wv = white_meas.u_prime_v_prime
    span = max(1e-6, y_max - y_min)

    ramp: list[GrayRampPoint] = []
    gamma_samples: list[float] = []
    for pct, x, y, z in avg_rows:
        norm_y = max(0.0, min(1.0, (y - y_min) / span))
        x_norm = max(0.0, min(1.0, pct / 100.0))
        ideal_y = x_norm**target_gamma
        lvl = int(round(x_norm * 255))
        meas = ColorMeasurement(rgb=(lvl, lvl, lvl), X=x, Y=y, Z=z)
        u, v = meas.u_prime_v_prime
        duv = math.hypot(u - wu, v - wv) if y > 1.0 else 0.0
        ramp.append(
            GrayRampPoint(
                input_pct=pct,
                X=x,
                Y=y,
                Z=z,
                norm_y=norm_y,
                ideal_y=ideal_y,
                delta_uv_to_white=duv,
            )
        )
        if 0.12 <= x_norm <= 0.92 and 0.01 < norm_y < 0.99:
            gamma_samples.append(math.log(norm_y) / math.log(x_norm))

    eff_gamma = (
        sum(gamma_samples) / len(gamma_samples) if gamma_samples else None
    )

    kinks: list[KinkWarning] = []
    for i in range(1, len(ramp)):
        prev_pt = ramp[i - 1]
        cur_pt = ramp[i]
        dx = (cur_pt.input_pct - prev_pt.input_pct) / 100.0
        if dx <= 0.005:
            continue
        dy = cur_pt.norm_y - prev_pt.norm_y
        if dy < -0.002:
            kinks.append(
                KinkWarning(
                    channel="Gray",
                    input_pct=cur_pt.input_pct,
                    severity="error",
                    message_en=(
                        f"Luminance reversal between {prev_pt.input_pct:.1f}% ({prev_pt.Y:.2f} cd/m²) "
                        f"and {cur_pt.input_pct:.1f}% ({cur_pt.Y:.2f} cd/m²). Possible measurement glitch."
                    ),
                    message_de=(
                        f"Helligkeitsabfall (Knick) zwischen {prev_pt.input_pct:.1f}% ({prev_pt.Y:.2f} cd/m²) "
                        f"und {cur_pt.input_pct:.1f}% ({cur_pt.Y:.2f} cd/m²). Möglicher Messfehler."
                    ),
                )
            )
        # Check abrupt chromaticity jump on neutral ramp (for Y > 5 cd/m²)
        if cur_pt.Y > 5.0 and prev_pt.Y > 5.0:
            duv_jump = abs(cur_pt.delta_uv_to_white - prev_pt.delta_uv_to_white)
            if duv_jump > 0.0060:
                kinks.append(
                    KinkWarning(
                        channel="GrayBalance",
                        input_pct=cur_pt.input_pct,
                        severity="warning",
                        message_en=(
                            f"Grayscale color shift spike at {cur_pt.input_pct:.1f}% "
                            f"(Δu'v' step = {duv_jump:.4f})."
                        ),
                        message_de=(
                            f"Farbsprung in der Graubalance bei {cur_pt.input_pct:.1f}% "
                            f"(Δu'v'-Sprung = {duv_jump:.4f})."
                        ),
                    )
                )

    # Check second derivative of normalized luminance vs ideal gamma curve
    deviations = [pt.norm_y - pt.ideal_y for pt in ramp]
    for i in range(1, len(deviations) - 1):
        neighbor_avg = 0.5 * (deviations[i - 1] + deviations[i + 1])
        spike = abs(deviations[i] - neighbor_avg)
        if spike > 0.030:
            pt = ramp[i]
            kinks.append(
                KinkWarning(
                    channel="Gray",
                    input_pct=pt.input_pct,
                    severity="warning",
                    message_en=(
                        f"Tone curve kink at {pt.input_pct:.1f}% "
                        f"(local deviation spike of {spike * 100:.1f}%)."
                    ),
                    message_de=(
                        f"Knick in der gemessenen Tonwertkurve bei {pt.input_pct:.1f}% "
                        f"(lokaler Ausreißer von {spike * 100:.1f}%)."
                    ),
                )
            )

    return ramp, kinks, eff_gamma


def inspect_profile(
    profile_path: str | Path,
    ti3_path: str | Path | None = None,
    target_gamma: float = 2.2,
) -> ProfileInspection:
    """Inspects an `.icc` profile (and optional `.ti3` file) for curves, metrics, and kinks."""
    path = Path(profile_path)
    data = path.read_bytes()
    tags = _parse_icc_tags(data)

    desc = (
        (_decode_desc_tag(tags[b"desc"]) if b"desc" in tags else None)
        or path.stem
    )
    r_trc = _decode_trc_tag(tags[b"rTRC"]) if b"rTRC" in tags else []
    g_trc = _decode_trc_tag(tags[b"gTRC"]) if b"gTRC" in tags else []
    b_trc = _decode_trc_tag(tags[b"bTRC"]) if b"bTRC" in tags else []

    lumi_xyz = _decode_xyz_tag(tags[b"lumi"]) if b"lumi" in tags else None
    wtpt_xyz = _decode_xyz_tag(tags[b"wtpt"]) if b"wtpt" in tags else None
    bkpt_xyz = _decode_xyz_tag(tags[b"bkpt"]) if b"bkpt" in tags else None

    ti3_text: str | None = None
    if ti3_path is not None and Path(ti3_path).exists():
        ti3_text = Path(ti3_path).read_text(encoding="latin-1", errors="replace")
    elif b"targ" in tags:
        ti3_text = _decode_text_tag(tags[b"targ"])

    ti3_rows = parse_ti3_text(ti3_text) if ti3_text else []
    gray_ramp, ramp_kinks, eff_gamma = _analyze_gray_ramp(
        ti3_rows, target_gamma=target_gamma
    )

    kinks: list[KinkWarning] = []
    for ch_name, curve in (("R", r_trc), ("G", g_trc), ("B", b_trc)):
        kinks.extend(_detect_trc_kinks(ch_name, curve))
    kinks.extend(ramp_kinks)

    # Determine luminance, black point, contrast ratio, and whitepoint chromaticity
    luminance_cdm2: float | None = None
    black_cdm2: float | None = None
    white_xyz: tuple[float, float, float] | None = wtpt_xyz

    if gray_ramp:
        luminance_cdm2 = gray_ramp[-1].Y
        black_cdm2 = gray_ramp[0].Y
        white_xyz = (gray_ramp[-1].X, gray_ramp[-1].Y, gray_ramp[-1].Z)
    elif lumi_xyz is not None:
        luminance_cdm2 = lumi_xyz[1]
        if bkpt_xyz is not None and wtpt_xyz is not None and wtpt_xyz[1] > 0:
            black_cdm2 = bkpt_xyz[1] * (luminance_cdm2 / wtpt_xyz[1])

    contrast_ratio: float | None = None
    if luminance_cdm2 is not None and black_cdm2 is not None and black_cdm2 > 0.0005:
        contrast_ratio = luminance_cdm2 / black_cdm2

    white_cct: float | None = None
    white_xy: tuple[float, float] | None = None
    white_duv: float | None = None
    if white_xyz is not None and sum(white_xyz) > 0:
        wm = ColorMeasurement(
            rgb=(255, 255, 255), X=white_xyz[0], Y=white_xyz[1], Z=white_xyz[2]
        )
        white_xy = wm.xy
        white_cct = wm.cct_kelvin
        white_duv = wm.delta_uv_to_d65()

    # Estimate effective gamma from G TRC if no .ti3 grayscale ramp was present
    if eff_gamma is None and len(g_trc) >= 64:
        mid_idx = len(g_trc) // 2
        x_mid = mid_idx / (len(g_trc) - 1)
        y_mid = g_trc[mid_idx]
        if 0.01 < y_mid < 0.99:
            eff_gamma = math.log(y_mid) / math.log(x_mid)

    return ProfileInspection(
        profile_path=path,
        description=desc,
        white_xyz=white_xyz,
        black_xyz=bkpt_xyz,
        luminance_cdm2=luminance_cdm2,
        black_luminance_cdm2=black_cdm2,
        contrast_ratio=contrast_ratio,
        white_cct_kelvin=white_cct,
        white_xy=white_xy,
        white_delta_uv_d65=white_duv,
        effective_gamma=eff_gamma,
        target_gamma=target_gamma,
        r_trc=r_trc,
        g_trc=g_trc,
        b_trc=b_trc,
        gray_ramp=gray_ramp,
        total_measured_patches=len(ti3_rows),
        kinks=kinks,
    )
