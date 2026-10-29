# KelvinCal – Roadmap & TODO

## Completed Clean-Room Improvements
- [x] **DisplayCAL `targen` & `colprof` Parameter Alignment (`profile_pipeline.py`):**
  - Adopted high-density neutral gray axis sampling (`-g 52` at 175 patches), 3D cube grid (`-m 5`), single-channel steps (`-s 5`), explicit white/black anchors (`-e 4 -B 1`), and high-quality 3D-cLUT generation (`colprof -qh -aX`).

## Planned Features (from DisplayCAL Clean-Room Analysis & Roadmap)

- [ ] **3D-cLUT (`A2B0`/`B2A0`) Curve Evaluation via `xicclu` & Bradford Adaptation (`profile_inspector.py`):**
  - Evaluate 3D-cLUT profiles (`A2B0`/`B2A0`) along a neutral $L^*$ axis via ArgyllCMS `xicclu` (in addition to 1D `rTRC`/`gTRC`/`bTRC` shaper tags) so 3D-LUT gray balance corrections are directly visible in the curve plot.
  - Apply Bradford chromatic adaptation (`wtpt` / `chad`) between PCS D50 and the measured whitepoint.
  - Add an `L* →` toggle in `ProfileReviewDialog` to switch the vertical axis between linear Luminance $Y$ and perceptual CIE $L^*$, and clamp gamma calculation to the $1\,\% \dots 99\,\%$ input range with black-offset compensation.
- [ ] **DisplayCAL-Style CIE 1931 ($xy$) / 1976 ($u'v'$) Gamut Viewer & 3D Gamut Volume:**
  - Sample $6 \times 40 = 240$ perimeter RGB points ($R \to Y \to G \to C \to B \to M \to R$) through `xicclu` (`-if -ff`) to draw curved, per-segment RGB-colored gamut contours on a neutral dark canvas (`#333333`) with whitepoint crosshairs.
  - Support switching between CIE 1976 $u'v'$ (perceptually uniform) and CIE 1931 $xy$.
  - Compute true 3D CIE $L^*a^*b^*$ gamut volume and intersection coverage (%) against sRGB, AdobeRGB, DCI-P3, and Rec.2020 using ArgyllCMS `iccgamut` and `viewgam`.
- [ ] **Post-Calibration Verification & Gray-Balance Report ($\Delta E_{2000}$ Check):**
  - Measure verification patches (e.g. 24-patch ColorChecker + neutral gray ramp) with the new ICC profile active in the Wayland compositor.
  - Evaluate against DisplayCAL's two-tier tolerances:
    - Mean $\Delta E_{2000} \le 1.0$ (recommended) / $\le 1.5$ (nominal)
    - Max $\Delta E_{2000} \le 3.0$ (recommended) / $\le 4.0$ (nominal)
    - Whitepoint $\Delta E_{2000} \le 1.0$ (recommended) / $\le 2.0$ (nominal)
    - Dedicated **Gray Balance Check** via pure chroma error $\Delta C'$ (excluding luminance error $\Delta L'$) and $\Delta a^*, \Delta b^*$ range ($\max - \min \le 1.5$).
- [ ] **Pre-`colprof` `.ti3` Measurement Outlier & Glitch Detector:**
  - Inspect `.ti3` patch measurements before calling `colprof` to detect sudden $\Delta E_{2000}$ spikes or non-monotonic jumps (e.g. caused by a desktop popup/notification covering the patch window or sensor movement during `dispread`).
- [ ] **Optional Perceptual / Saturation Gamut Mapping (`colprof -S sRGB.icm`):**
  - For wide-gamut displays, optionally pass a source gamut reference (`-S sRGB.icm`) to `colprof` so `B2A1` (Perceptual) and `B2A2` (Saturation) CIECAM02 gamut-mapping tables are generated alongside the colorimetric `A2B0`/`B2A0` tables.
- [ ] **Colorimeter Spectral Correction (`.ccss` / `.ccmx`) Picker:**
  - Provide a built-in selector and auto-discovery for ArgyllCMS / i1d3 spectral corrections (W-LED, PFS Phosphor / Wide-Gamut LED, GB-r-LED, OLED) passed via `-X` to `spotread` and `dispread`.
- [ ] **One-Click Full Calibration Pipeline (Phase 1a $\to$ 1b $\to$ 2 $\to$ 3):**
  - Run Contrast Binary Search, D65 Whitepoint & Luminance Regulation, `targen`/`dispread`/`colprof` measurement, and open the Profile Inspector & Live Preview dialog in a single uninterrupted workflow.
- [ ] **Simple vs. Expert Mode in `kcal-gui`:**
  - *Simple / Wizard Mode:* Guided step-by-step assistant with presets (*"Photography / Print – 120 cd/m² D65 / D50"*, *"Office / Web – 140 cd/m² D65"*, *"Video – 100 cd/m² D65"*).
  - *Expert Mode:* Current technical view with direct access to VCP search bounds, patch counts, and raw measurement logs.
- [ ] **GNOME / Mutter Wayland Backend (`MutterBackend`):**
  - Complete `org.gnome.Mutter.DisplayConfig` + `colord` integration alongside `KWinBackend`.
