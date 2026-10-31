"""ICC profile and ArgyllCMS .ti3 measurement inspector with DisplayCAL-style curves and kink detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from pathlib import Path
import struct

from kelvincal.core.i18n import translate
from kelvincal.core.models import ColorMeasurement, D65_X, D65_Y


# Standard sRGB primaries in CIE 1931 (x, y)
SRGB_PRIMARIES_XY: dict[str, tuple[float, float]] = {
    "R": (0.6400, 0.3300),
    "G": (0.3000, 0.6000),
    "B": (0.1500, 0.0600),
}

# Reference RGB spaces (primaries from the published standards: IEC 61966-2-1, Adobe RGB (1998),
# SMPTE RP 431-2 / DCI-P3, ITU-R BT.2020), CIE 1931 xy
REFERENCE_GAMUTS: dict[str, dict[str, tuple[float, float]]] = {
    "sRGB": SRGB_PRIMARIES_XY,
    "AdobeRGB": {"R": (0.6400, 0.3300), "G": (0.2100, 0.7100), "B": (0.1500, 0.0600)},
    "DCI-P3": {"R": (0.6800, 0.3200), "G": (0.2650, 0.6900), "B": (0.1500, 0.0600)},
    "Rec.2020": {"R": (0.7080, 0.2920), "G": (0.1700, 0.7970), "B": (0.1310, 0.0460)},
}


@dataclass(frozen=True)
class GrayRampPoint:
    """A single neutral grayscale measurement point (R == G == B) from a .ti3 dataset."""

    input_pct: float                       # 0.0 .. 100.0
    X: float
    Y: float
    Z: float
    norm_y: float                          # Black-compensated normalized Y in 0.0 .. 1.0
    norm_r: float                          # Black-compensated normalized R luminance response (0..1)
    norm_g: float                          # Black-compensated normalized G luminance response (0..1)
    norm_b: float                          # Black-compensated normalized B luminance response (0..1)
    ideal_y: float                         # Ideal (input_pct / 100) ** gamma
    local_gamma: float | None              # Effective gamma log(norm_y)/log(x) at this level
    rgb_balance_dev_pct: tuple[float, float, float]  # (dR%, dG%, dB%) deviation relative to neutral gray
    delta_uv_to_white: float               # Chromaticity drift relative to measured whitepoint


@dataclass(frozen=True)
class KinkWarning:
    """Represents a detected discontinuity, reversal, or kink ('Knick') in a tone curve."""

    channel: str              # "Gray", "R", "G", "B", or "GrayBalance"
    input_pct: float          # Input signal level (0..100%) where the anomaly occurs
    severity: str             # "warning" or "error"
    message: str              # Translated, user-facing description


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

    # Measured .ti3 grayscale ramp and per-channel (R, G, B) ramps (list of (input_pct, norm_val))
    gray_ramp: list[GrayRampPoint] = field(default_factory=list)
    channel_ramps: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    total_measured_patches: int = 0

    # CIE 1931 (x, y) primaries of the display and sRGB gamut coverage
    primaries_xy: dict[str, tuple[float, float]] = field(default_factory=dict)
    srgb_coverage_pct: float | None = None
    srgb_volume_pct: float | None = None
    coverage_pct: dict[str, float] = field(default_factory=dict)  # REFERENCE_GAMUTS name -> % (u′v′)

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


@dataclass(frozen=True)
class ProfileSummary:
    """Header-level facts about an ICC file for list views (cheap to read)."""

    path: Path
    description: str
    created: datetime | None
    version: str
    profile_type: str  # "cLUT + Matrix", "Matrix", "cLUT" or ""


def read_profile_summary(path: str | Path) -> ProfileSummary:
    """Reads description, creation date, version and LUT/matrix type from an ICC file header and tag table."""
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 132 or data[36:40] != b"acsp":
        raise ValueError(translate("Errors", "{path} is not an ICC profile.").format(path=path))
    tags = _parse_icc_tags(data)
    desc = _decode_desc_tag(tags.get(b"desc", b"")) or path.stem
    created: datetime | None
    try:
        created = datetime(*struct.unpack(">6H", data[24:36]))
    except ValueError:
        created = None
    version = f"{data[8]}.{data[9] >> 4}"
    has_lut = b"A2B0" in tags
    has_matrix = all(t in tags for t in (b"rXYZ", b"gXYZ", b"bXYZ"))
    profile_type = {(True, True): "cLUT + Matrix", (False, True): "Matrix", (True, False): "cLUT"}.get(
        (has_lut, has_matrix), ""
    )
    return ProfileSummary(path=path, description=desc, created=created, version=version, profile_type=profile_type)


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


def _xyz_to_srgb_linear(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Converts CIE XYZ (relative to D65) to linear sRGB components."""
    r = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    b = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    return (r, g, b)


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    n = len(pts)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return 0.5 * abs(area)


def _sutherland_hodgman_clip(
    subject_polygon: list[tuple[float, float]],
    clip_polygon: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Clips a 2D convex polygon against another convex polygon (ccw order)."""
    # Ensure clip_polygon is counter-clockwise
    signed = 0.0
    for i in range(len(clip_polygon)):
        x1, y1 = clip_polygon[i]
        x2, y2 = clip_polygon[(i + 1) % len(clip_polygon)]
        signed += x1 * y2 - x2 * y1
    if signed < 0:
        clip_polygon = list(reversed(clip_polygon))

    def _inside(p: tuple[float, float], cp1: tuple[float, float], cp2: tuple[float, float]) -> bool:
        return (cp2[0] - cp1[0]) * (p[1] - cp1[1]) >= (cp2[1] - cp1[1]) * (p[0] - cp1[0])

    def _intersection(
        cp1: tuple[float, float],
        cp2: tuple[float, float],
        s: tuple[float, float],
        e: tuple[float, float],
    ) -> tuple[float, float]:
        dc = (cp1[0] - cp2[0], cp1[1] - cp2[1])
        dp = (s[0] - e[0], s[1] - e[1])
        n1 = cp1[0] * cp2[1] - cp1[1] * cp2[0]
        n2 = s[0] * e[1] - s[1] * e[0]
        denom = dc[0] * dp[1] - dc[1] * dp[0]
        if abs(denom) < 1e-12:
            return e
        return ((n1 * dp[0] - n2 * dc[0]) / denom, (n1 * dp[1] - n2 * dc[1]) / denom)

    output_list = list(subject_polygon)
    cp1 = clip_polygon[-1]
    for cp2 in clip_polygon:
        input_list = output_list
        output_list = []
        if not input_list:
            break
        s = input_list[-1]
        for e in input_list:
            if _inside(e, cp1, cp2):
                if not _inside(s, cp1, cp2):
                    output_list.append(_intersection(cp1, cp2, s, e))
                output_list.append(e)
            elif _inside(s, cp1, cp2):
                output_list.append(_intersection(cp1, cp2, s, e))
            s = e
        cp1 = cp2
    return output_list


def _compute_srgb_gamut_metrics(
    primaries_xy: dict[str, tuple[float, float]],
) -> tuple[float | None, float | None]:
    """Returns (sRGB coverage %, gamut area ratio vs sRGB %) in CIE 1931 xy."""
    if not all(k in primaries_xy for k in ("R", "G", "B")):
        return None, None
    disp_tri = [primaries_xy["R"], primaries_xy["G"], primaries_xy["B"]]
    srgb_tri = [SRGB_PRIMARIES_XY["R"], SRGB_PRIMARIES_XY["G"], SRGB_PRIMARIES_XY["B"]]
    srgb_area = _polygon_area(srgb_tri)
    disp_area = _polygon_area(disp_tri)
    if srgb_area <= 1e-9:
        return None, None
    clipped = _sutherland_hodgman_clip(disp_tri, srgb_tri)
    inter_area = _polygon_area(clipped)
    coverage = min(100.0, (inter_area / srgb_area) * 100.0)
    volume_ratio = (disp_area / srgb_area) * 100.0
    return coverage, volume_ratio


def xy_to_uv(x: float, y: float) -> tuple[float, float]:
    """CIE 1931 xy → CIE 1976 u′v′."""
    d = -2.0 * x + 12.0 * y + 3.0
    return (4.0 * x / d, 9.0 * y / d) if abs(d) > 1e-12 else (0.0, 0.0)


def gamut_coverage_pct(
    primaries_xy: dict[str, tuple[float, float]],
    reference_xy: dict[str, tuple[float, float]],
) -> float | None:
    """Share of the reference triangle covered by the display triangle, in CIE 1976 u′v′ (2D)."""
    if not all(k in primaries_xy for k in ("R", "G", "B")):
        return None
    disp = [xy_to_uv(*primaries_xy[k]) for k in ("R", "G", "B")]
    ref = [xy_to_uv(*reference_xy[k]) for k in ("R", "G", "B")]
    ref_area = _polygon_area(ref)
    if ref_area <= 1e-12:
        return None
    inter = _polygon_area(_sutherland_hodgman_clip(ref, disp))
    return min(100.0, inter / ref_area * 100.0)


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
                    message=translate(
                        "ProfileInspector",
                        "{channel} TRC reversal at {pct:.1f}% input (output drops by {drop:.2f}%).",
                    ).format(
                        channel=channel,
                        pct=pct,
                        drop=abs(diff) * 100,
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
                    message=translate(
                        "ProfileInspector",
                        "{channel} TRC slope discontinuity ('kink') near {pct:.0f}% input.",
                    ).format(
                        channel=channel,
                        pct=pct,
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

    _, kx, ky, kz = avg_rows[0]
    _, wx, wy, wz = avg_rows[-1]
    y_min = ky
    y_max = wy
    white_meas = ColorMeasurement(rgb=(255, 255, 255), X=wx, Y=wy, Z=wz)
    wu, wv = white_meas.u_prime_v_prime
    span_y = max(1e-6, y_max - y_min)

    # Whitepoint-normalized linear RGB reference
    wr_lin, wg_lin, wb_lin = _xyz_to_srgb_linear(
        max(0.0, wx - kx), max(0.0, wy - ky), max(0.0, wz - kz)
    )
    wr_lin = max(1e-6, wr_lin)
    wg_lin = max(1e-6, wg_lin)
    wb_lin = max(1e-6, wb_lin)

    ramp: list[GrayRampPoint] = []
    gamma_samples: list[float] = []
    for pct, x, y, z in avg_rows:
        norm_y = max(0.0, min(1.0, (y - y_min) / span_y))
        rl, gl, bl = _xyz_to_srgb_linear(
            max(0.0, x - kx), max(0.0, y - ky), max(0.0, z - kz)
        )
        norm_r = max(0.0, min(1.0, rl / wr_lin))
        norm_g = max(0.0, min(1.0, gl / wg_lin))
        norm_b = max(0.0, min(1.0, bl / wb_lin))

        x_norm = max(0.0, min(1.0, pct / 100.0))
        ideal_y = x_norm**target_gamma
        lvl = int(round(x_norm * 255))
        meas = ColorMeasurement(rgb=(lvl, lvl, lvl), X=x, Y=y, Z=z)
        u, v = meas.u_prime_v_prime
        duv = math.hypot(u - wu, v - wv) if y > 1.0 else 0.0

        local_g: float | None = None
        if 0.04 <= x_norm <= 0.96 and 0.002 < norm_y < 0.998:
            local_g = math.log(norm_y) / math.log(x_norm)
            if 0.12 <= x_norm <= 0.92:
                gamma_samples.append(local_g)

        # RGB grayscale balance deviation in % of signal relative to neutral luminance
        if norm_y > 0.005:
            inv_g = 1.0 / target_gamma
            sig_y = norm_y**inv_g
            sig_r = norm_r**inv_g
            sig_g = norm_g**inv_g
            sig_b = norm_b**inv_g
            bal_dev = (
                (sig_r - sig_y) * 100.0,
                (sig_g - sig_y) * 100.0,
                (sig_b - sig_y) * 100.0,
            )
        else:
            bal_dev = (0.0, 0.0, 0.0)

        ramp.append(
            GrayRampPoint(
                input_pct=pct,
                X=x,
                Y=y,
                Z=z,
                norm_y=norm_y,
                norm_r=norm_r,
                norm_g=norm_g,
                norm_b=norm_b,
                ideal_y=ideal_y,
                local_gamma=local_g,
                rgb_balance_dev_pct=bal_dev,
                delta_uv_to_white=duv,
            )
        )

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
                    message=translate(
                        "ProfileInspector",
                        "Luminance reversal between {from_pct:.1f}% ({from_y:.2f} cd/m²) and {to_pct:.1f}% ({to_y:.2f} cd/m²). Possible measurement glitch.",
                    ).format(
                        from_pct=prev_pt.input_pct,
                        from_y=prev_pt.Y,
                        to_pct=cur_pt.input_pct,
                        to_y=cur_pt.Y,
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
                        message=translate(
                            "ProfileInspector",
                            "Grayscale color shift spike at {input_pct:.1f}% (Δu'v' step = {duv_jump:.4f}).",
                        ).format(
                            input_pct=cur_pt.input_pct,
                            duv_jump=duv_jump,
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
                    message=translate(
                        "ProfileInspector",
                        "Tone curve kink at {input_pct:.1f}% (local deviation spike of {spike:.1f}%).",
                    ).format(
                        input_pct=pt.input_pct,
                        spike=spike * 100,
                    ),
                )
            )

    return ramp, kinks, eff_gamma


def _extract_primaries_from_ti3_or_tags(
    ti3_rows: list[tuple[float, float, float, float, float, float]],
    tags: dict[bytes, bytes],
) -> dict[str, tuple[float, float]]:
    """Extracts Red, Green, Blue CIE 1931 (x, y) primaries from .ti3 patches or ICC XYZ tags."""
    primaries: dict[str, tuple[float, float]] = {}

    # Prefer unadapted pure primary measurements from .ti3 if available
    for ch, target_rgb in (("R", (100.0, 0.0, 0.0)), ("G", (0.0, 100.0, 0.0)), ("B", (0.0, 0.0, 100.0))):
        matches = [
            r
            for r in ti3_rows
            if abs(r[0] - target_rgb[0]) < 1.0
            and abs(r[1] - target_rgb[1]) < 1.0
            and abs(r[2] - target_rgb[2]) < 1.0
        ]
        if matches:
            _, _, _, x, y, z = matches[0]
            s = x + y + z
            if s > 1e-6:
                primaries[ch] = (x / s, y / s)

    if len(primaries) < 3:
        for ch, sig in (("R", b"rXYZ"), ("G", b"gXYZ"), ("B", b"bXYZ")):
            if ch not in primaries and sig in tags:
                xyz = _decode_xyz_tag(tags[sig])
                if xyz is not None and sum(xyz) > 1e-6:
                    s = sum(xyz)
                    primaries[ch] = (xyz[0] / s, xyz[1] / s)

    return primaries


def _extract_channel_ramps(
    rows: list[tuple[float, float, float, float, float, float]],
    target_gamma: float = 2.2,
) -> tuple[dict[str, list[tuple[float, float]]], list[KinkWarning]]:
    """Extracts measured (input_pct, normalized_output) ramps for pure R, G, and B channels from .ti3."""
    if not rows:
        return {}, []

    black_rows = [r for r in rows if r[0] < 0.25 and r[1] < 0.25 and r[2] < 0.25]
    y_black = (
        sum(r[4] for r in black_rows) / len(black_rows)
        if black_rows
        else min(r[4] for r in rows)
    )

    ramps: dict[str, list[tuple[float, float]]] = {}
    kinks: list[KinkWarning] = []

    ch_specs = [
        ("R", lambda r: r[0] >= 0.0 and r[1] < 0.25 and r[2] < 0.25, 0),
        ("G", lambda r: r[1] >= 0.0 and r[0] < 0.25 and r[2] < 0.25, 1),
        ("B", lambda r: r[2] >= 0.0 and r[0] < 0.25 and r[1] < 0.25, 2),
    ]
    for ch, pred, idx in ch_specs:
        ch_rows = [r for r in rows if pred(r)]
        grouped: dict[float, list[float]] = {}
        for r in ch_rows:
            pct = round(r[idx], 2)
            grouped.setdefault(pct, []).append(r[4])  # Use Y (or Z for B if Y is tiny)
        if len(grouped) < 4:
            continue
        sorted_pcts = sorted(grouped.keys())
        y_vals = [sum(grouped[p]) / len(grouped[p]) for p in sorted_pcts]
        span = max(1e-6, y_vals[-1] - y_black)
        pts = [
            (pct, max(0.0, min(1.0, (y - y_black) / span)))
            for pct, y in zip(sorted_pcts, y_vals)
        ]
        ramps[ch] = pts

        for i in range(1, len(pts)):
            p0, v0 = pts[i - 1]
            p1, v1 = pts[i]
            if p1 - p0 > 0.5 and v1 - v0 < -0.004:
                kinks.append(
                    KinkWarning(
                        channel=ch,
                        input_pct=p1,
                        severity="error",
                        message=translate(
                            "ProfileInspector",
                            "Measured {ch} channel reversal between {p0:.1f}% and {p1:.1f}%.",
                        ).format(
                            ch=ch,
                            p0=p0,
                            p1=p1,
                        ),
                    )
                )
        devs = [v - (p / 100.0) ** target_gamma for p, v in pts]
        for i in range(1, len(devs) - 1):
            navg = 0.5 * (devs[i - 1] + devs[i + 1])
            spike = abs(devs[i] - navg)
            if spike > 0.035:
                p_spike = pts[i][0]
                kinks.append(
                    KinkWarning(
                        channel=ch,
                        input_pct=p_spike,
                        severity="warning",
                        message=translate(
                            "ProfileInspector",
                            "Measured {ch} channel kink at {p_spike:.1f}% ({spike:.1f}% spike).",
                        ).format(
                            ch=ch,
                            p_spike=p_spike,
                            spike=spike * 100,
                        ),
                    )
                )

    return ramps, kinks


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
    channel_ramps, ch_kinks = _extract_channel_ramps(
        ti3_rows, target_gamma=target_gamma
    )

    primaries_xy = _extract_primaries_from_ti3_or_tags(ti3_rows, tags)
    srgb_cov, srgb_vol = _compute_srgb_gamut_metrics(primaries_xy)
    coverage = {
        name: pct for name, ref in REFERENCE_GAMUTS.items()
        if (pct := gamut_coverage_pct(primaries_xy, ref)) is not None
    }

    kinks: list[KinkWarning] = []
    for ch_name, curve in (("R", r_trc), ("G", g_trc), ("B", b_trc)):
        kinks.extend(_detect_trc_kinks(ch_name, curve))
    kinks.extend(ramp_kinks)
    kinks.extend(ch_kinks)

    # Determine luminance, black point, contrast ratio, and whitepoint chromaticity
    luminance_cdm2: float | None = None
    black_cdm2: float | None = None
    white_xyz: tuple[float, float, float] | None = wtpt_xyz

    if gray_ramp:
        luminance_cdm2 = gray_ramp[-1].Y
        black_cdm2 = gray_ramp[0].Y
        white_xyz = (gray_ramp[-1].X, gray_ramp[-1].Y, gray_ramp[-1].Z)
        # dispread stores the measurements normalised to white Y = 100; the absolute white is in 'lumi'
        if lumi_xyz is not None and lumi_xyz[1] > 0 and abs(luminance_cdm2 - 100.0) < 0.5:
            scale = lumi_xyz[1] / luminance_cdm2
            luminance_cdm2, black_cdm2 = lumi_xyz[1], black_cdm2 * scale
    elif lumi_xyz is not None:
        luminance_cdm2 = lumi_xyz[1]
        if bkpt_xyz is not None and wtpt_xyz is not None and wtpt_xyz[1] > 0:
            black_cdm2 = bkpt_xyz[1] * (luminance_cdm2 / wtpt_xyz[1])

    contrast_ratio: float | None = None
    if luminance_cdm2 is not None and black_cdm2 is not None and black_cdm2 > 0.0005:
        contrast_ratio = luminance_cdm2 / black_cdm2

    white_cct: float | None = None
    white_xy: tuple[float, float] | None = (D65_X, D65_Y)
    white_duv: float | None = None
    if white_xyz is not None and sum(white_xyz) > 0:
        wm = ColorMeasurement(
            rgb=(255, 255, 255), X=white_xyz[0], Y=white_xyz[1], Z=white_xyz[2]
        )
        white_xy = wm.xy
        white_cct = wm.cct_kelvin
        white_duv = wm.delta_uv_to_d65()

    # Estimate effective gamma from G TRC if no .ti3 mid-tone gray steps were present
    if eff_gamma is None and len(g_trc) >= 64:
        samples = []
        n = len(g_trc)
        for idx in range(int(n * 0.15), int(n * 0.85)):
            xm = idx / (n - 1)
            ym = g_trc[idx]
            if 0.01 < ym < 0.99:
                samples.append(math.log(ym) / math.log(xm))
        if samples:
            eff_gamma = sum(samples) / len(samples)

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
        channel_ramps=channel_ramps,
        total_measured_patches=len(ti3_rows),
        primaries_xy=primaries_xy,
        srgb_coverage_pct=srgb_cov,
        srgb_volume_pct=srgb_vol,
        coverage_pct=coverage,
        kinks=kinks,
    )
