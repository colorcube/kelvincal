"""Plausibility check of dispread measurements (.ti3) before colprof (mockup 1i).

A notification popping up over the patch window or a sensor that slipped produces single patches
that do not fit the rest of the data set. The check works in two stages:

1. A simple display model (black + per-channel tone curves from the single-channel ramps + a 3×3
   matrix fitted by least squares) predicts every patch. Its residuals are small but systematic
   (e.g. saturated reds on panels that are not perfectly additive).
2. Each patch's residual is compared with the median residual of its neighbours in RGB space. What
   remains (ΔE00) is patch-specific – an outlier in the measurement, not a property of the display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
import statistics

from kcal_core.color import delta_e2000, xyz_to_lab

DEFAULT_THRESHOLD = 3.5  # ΔE00; clean data sets peaked at 3.05 (gamut corners), real disturbances at 5–60
NEIGHBOURS = 6


@dataclass
class Ti3Patch:
    index: int                              # position in the file = measurement order (0-based)
    sample_id: str
    rgb: tuple[float, float, float]         # 0..100
    xyz: tuple[float, float, float]         # as stored (normalised to Y=100 when NORMALIZED_TO_Y_100)


@dataclass
class Ti3Data:
    patches: list[Ti3Patch]
    keywords: dict[str, str] = field(default_factory=dict)

    @property
    def normalised(self) -> bool:
        return self.keywords.get("NORMALIZED_TO_Y_100", "").upper() == "YES"

    @property
    def white_luminance(self) -> float | None:
        """Absolute Y of white in cd/m² (LUMINANCE_XYZ_CDM2), needed to scale re-measurements."""
        parts = self.keywords.get("LUMINANCE_XYZ_CDM2", "").split()
        try:
            return float(parts[1])
        except (IndexError, ValueError):
            return None


@dataclass
class Outlier:
    patch: Ti3Patch
    delta_e: float


@dataclass
class MeasurementCheck:
    scores: list[float]          # ΔE00 per patch, in measurement order
    outliers: list[Outlier]      # sorted by measurement order
    threshold: float

    @property
    def ok(self) -> bool:
        return not self.outliers


_KEYWORD = re.compile(r'^([A-Z_][A-Z0-9_]*)\s+"(.*)"\s*$')


def parse_ti3(text: str) -> Ti3Data:
    fields: list[str] = []
    keywords: dict[str, str] = {}
    patches: list[Ti3Patch] = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line in ("BEGIN_DATA_FORMAT", "BEGIN_DATA"):
            section = line
            continue
        if line in ("END_DATA_FORMAT", "END_DATA"):
            if line == "END_DATA":
                break  # only the first table (calibration tables may follow)
            section = ""
            continue
        if section == "BEGIN_DATA_FORMAT":
            fields.extend(line.split())
        elif section == "BEGIN_DATA" and line:
            row = dict(zip(fields, line.split()))
            try:
                patches.append(Ti3Patch(
                    index=len(patches),
                    sample_id=row.get("SAMPLE_ID", str(len(patches) + 1)),
                    rgb=(float(row["RGB_R"]), float(row["RGB_G"]), float(row["RGB_B"])),
                    xyz=(float(row["XYZ_X"]), float(row["XYZ_Y"]), float(row["XYZ_Z"])),
                ))
            except (KeyError, ValueError):
                continue
        else:
            m = _KEYWORD.match(line)
            if m:
                keywords[m.group(1)] = m.group(2)
    return Ti3Data(patches, keywords)


def replace_xyz(text: str, new_xyz: dict[str, tuple[float, float, float]]) -> str:
    """Returns `text` with the XYZ values of the given SAMPLE_IDs replaced (other columns untouched)."""
    out: list[str] = []
    fields: list[str] = []
    section = ""
    done = False
    for raw in text.splitlines(keepends=True):
        line = raw.strip()
        if not done and line in ("BEGIN_DATA_FORMAT", "BEGIN_DATA"):
            section = line
        elif not done and line == "END_DATA_FORMAT":
            section = ""
        elif not done and line == "END_DATA":
            section, done = "", True
        elif section == "BEGIN_DATA_FORMAT":
            fields.extend(line.split())
        elif section == "BEGIN_DATA" and line:
            parts = line.split()
            row = dict(zip(fields, parts))
            xyz = new_xyz.get(row.get("SAMPLE_ID", ""))
            if xyz is not None:
                for name, value in zip(("XYZ_X", "XYZ_Y", "XYZ_Z"), xyz):
                    parts[fields.index(name)] = f"{value:.6f}"
                raw = " ".join(parts) + "\n"
        out.append(raw)
    return "".join(out)


# ---------------------------------------------------------------------- model


def _solve3(a: list[list[float]], b: list[float]) -> list[float]:
    m = [row[:] + [bb] for row, bb in zip(a, b)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-12:
            raise ValueError("singular")
        for r in range(3):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, 4):
                    m[r][k] -= f * m[c][k]
    return [m[i][3] / m[i][i] for i in range(3)]


def _median_xyz(values: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    return tuple(statistics.median(v) for v in zip(*values))  # type: ignore[return-value]


def check_measurements(data: Ti3Data, threshold: float = DEFAULT_THRESHOLD) -> MeasurementCheck:
    """Scores every patch (ΔE00 against model + neighbourhood) and lists those above `threshold`."""
    patches = data.patches
    n = len(patches)
    blacks = [p.xyz for p in patches if max(p.rgb) <= 0.0]
    whites = [p.xyz for p in patches if min(p.rgb) >= 99.99]
    if n < 12 or not whites:
        return MeasurementCheck([0.0] * n, [], threshold)
    black = _median_xyz(blacks) if blacks else (0.0, 0.0, 0.0)
    white = _median_xyz(whites)

    # per-channel tone curves from the single-channel patches: a power law fitted with the Theil–Sen
    # estimator (median of pairwise slopes in log–log space), so that a single bad patch – even the
    # full-intensity primary – cannot bend the model. Smooth deviations from the power law are left
    # to the neighbourhood stage.
    curves: list[tuple[float, float]] = []  # (log a, gamma) per channel
    for c in range(3):
        pts = [(math.log(p.rgb[c] / 100), math.log(p.xyz[1] - black[1]))
               for p in patches
               if p.rgb[c] >= 5 and all(p.rgb[k] <= 0 for k in range(3) if k != c) and p.xyz[1] > black[1]]
        if len(pts) < 2:
            return MeasurementCheck([0.0] * n, [], threshold)
        slopes = [(y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(pts) for x2, y2 in pts[i + 1:] if x2 != x1]
        gamma = statistics.median(slopes) if slopes else 2.2
        curves.append((statistics.median(y - gamma * x for x, y in pts), gamma))
    feats = [[math.exp(curves[c][0]) * (p.rgb[c] / 100) ** curves[c][1] if p.rgb[c] > 0 else 0.0 for c in range(3)]
             for p in patches]

    def fit(idx: list[int]) -> list[list[float]]:
        ata = [[sum(feats[i][a] * feats[i][b] for i in idx) for b in range(3)] for a in range(3)]
        return [_solve3(ata, [sum(feats[i][a] * (patches[i].xyz[k] - black[k]) for i in idx) for a in range(3)])
                for k in range(3)]

    def predict(m: list[list[float]]) -> list[tuple[float, float, float]]:
        return [tuple(black[k] + sum(m[k][a] * feats[i][a] for a in range(3)) for k in range(3))  # type: ignore[misc]
                for i in range(n)]

    lab_meas = [xyz_to_lab(p.xyz, white) for p in patches]
    try:
        model = fit(list(range(n)))
        first = [delta_e2000(lab_meas[i], xyz_to_lab(xyz, white)) for i, xyz in enumerate(predict(model))]
        keep = sorted(range(n), key=lambda i: first[i])[: max(12, int(n * 0.9))]  # robust refit
        model = fit(keep)
    except ValueError:
        return MeasurementCheck([0.0] * n, [], threshold)
    lab_pred = [xyz_to_lab(xyz, white) for xyz in predict(model)]
    resid = [[lab_meas[i][k] - lab_pred[i][k] for k in range(3)] for i in range(n)]

    scores: list[float] = []
    for i, p in enumerate(patches):
        by_distance = sorted((math.dist(p.rgb, q.rgb), j) for j, q in enumerate(patches) if j != i)
        repeats = [j for d, j in by_distance if d <= 1e-9]  # same RGB measured again: best reference
        near = [j for d, j in by_distance if d > 1e-9][:NEIGHBOURS]
        ref = repeats + near[: max(3, NEIGHBOURS - len(repeats))] if repeats else near
        expected = [statistics.median(resid[j][k] for j in ref) for k in range(3)]
        scores.append(delta_e2000(lab_meas[i], tuple(lab_pred[i][k] + expected[k] for k in range(3))))
    outliers = [Outlier(patches[i], s) for i, s in enumerate(scores) if s > threshold]
    return MeasurementCheck(scores, outliers, threshold)
