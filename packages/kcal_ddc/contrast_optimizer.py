"""Component 1: Binary contrast search (interval halving) with single-channel clipping detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from kcal_core.models import ColorMeasurement, ContrastStepResult


@dataclass
class ContrastOptimizationConfig:
    """Configuration parameters for binary contrast search."""

    min_contrast: int = 40
    max_contrast: int = 90
    low_level: int = 248                # Near-white patch (248 for high SNR, or 254)
    high_level: int = 255               # Peak white patch
    gamma_reference: float = 2.2
    min_delta_l_cdm2: float = 0.30      # Absolute minimum ΔL (cd/m²)
    min_relative_step_ratio: float = 0.72  # At least 72% of ideal gamma-2.2 luminance step
    max_delta_uv: float = 0.0020        # Max allowed chromaticity shift Δu'v' (catches single R/G/B channel clipping)


@dataclass
class ContrastOptimizationResult:
    """Complete result of the contrast optimizer including all binary search steps."""

    optimal_contrast: int
    steps: list[ContrastStepResult] = field(default_factory=list)
    peak_luminance_cdm2: float = 0.0


class ContrastOptimizer:
    """Finds the highest unclipped hardware DDC contrast in 6-7 steps via binary search."""

    def __init__(self, config: ContrastOptimizationConfig | None = None) -> None:
        self.config = config or ContrastOptimizationConfig()

    def expected_relative_gain(self) -> float:
        """Computes theoretical relative luminance gain (Y_high - Y_low) / Y_high for ideal gamma."""
        low_norm = self.config.low_level / float(self.config.high_level)
        return 1.0 - (low_norm ** self.config.gamma_reference)

    def evaluate_contrast(
        self,
        contrast: int,
        set_contrast_fn: Callable[[int], None],
        measure_patch_fn: Callable[[tuple[int, int, int]], ColorMeasurement],
    ) -> ContrastStepResult:
        """Sets contrast K, measures near-white & peak white, and checks for luminance & chromaticity clipping."""
        set_contrast_fn(contrast)

        low_rgb = (self.config.low_level, self.config.low_level, self.config.low_level)
        high_rgb = (self.config.high_level, self.config.high_level, self.config.high_level)

        m_low = measure_patch_fn(low_rgb)
        m_high = measure_patch_fn(high_rgb)

        delta_l = m_high.Y - m_low.Y
        rel_gain = delta_l / m_high.Y if m_high.Y > 1e-6 else 0.0
        delta_uv = m_low.delta_uv_to(m_high)

        min_rel_expected = self.expected_relative_gain() * self.config.min_relative_step_ratio

        reasons: list[str] = []
        if delta_l <= self.config.min_delta_l_cdm2:
            reasons.append(
                f"ΔL={delta_l:.2f} cd/m² <= {self.config.min_delta_l_cdm2:.2f} cd/m² (full clipping)"
            )
        if rel_gain < min_rel_expected:
            reasons.append(
                f"Rel. step {rel_gain * 100:.2f}% < {min_rel_expected * 100:.2f}% (highlight compression)"
            )
        if delta_uv > self.config.max_delta_uv:
            reasons.append(
                f"Δu'v'={delta_uv:.4f} > {self.config.max_delta_uv:.4f} (single-channel R/G/B clipping)"
            )

        clipped = len(reasons) > 0
        reason_str = "; ".join(reasons) if clipped else "OK (no clipping)"

        return ContrastStepResult(
            contrast=contrast,
            m_low=m_low,
            m_high=m_high,
            delta_l_cdm2=delta_l,
            rel_gain=rel_gain,
            delta_uv=delta_uv,
            clipped=clipped,
            reason=reason_str,
        )

    def run(
        self,
        set_contrast_fn: Callable[[int], None],
        measure_patch_fn: Callable[[tuple[int, int, int]], ColorMeasurement],
        on_step: Callable[[ContrastStepResult], None] | None = None,
    ) -> ContrastOptimizationResult:
        """Executes the binary search over [min_contrast, max_contrast]."""
        low = self.config.min_contrast
        high = self.config.max_contrast
        best_contrast = low
        best_luminance = 0.0
        steps: list[ContrastStepResult] = []

        while (high - low) > 1:
            mid = (low + high) // 2
            step_res = self.evaluate_contrast(mid, set_contrast_fn, measure_patch_fn)
            steps.append(step_res)
            if on_step is not None:
                on_step(step_res)

            if not step_res.clipped:
                best_contrast = mid
                best_luminance = step_res.m_high.Y
                low = mid
            else:
                high = mid

        set_contrast_fn(best_contrast)
        return ContrastOptimizationResult(
            optimal_contrast=best_contrast,
            steps=steps,
            peak_luminance_cdm2=best_luminance,
        )
