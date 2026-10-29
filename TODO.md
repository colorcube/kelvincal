# KelvinCal – Roadmap & TODO

## Planned Features

- [ ] **DisplayCAL Mathematical Reference Audit (`Code/displaycal`):**
  - Check out `displaycal-py3` alongside `Code/kelvincal` as a clean-room mathematical reference (ideas and parameters only, no code).
  - Verify and adopt Bradford chromatic adaptation (PCS D50 $\leftrightarrow$ native/D65 whitepoint), 3D cLUT (`A2B0`/`B2A0`) curve evaluation, and optimal `targen`/`colprof` parameter sets.
- [ ] **DisplayCAL-Style CIE 1931 / 1976 ($u'v'$) Gamut Viewer:**
  - Render a full spectral color-shaded CIE 1931 $(x, y)$ and CIE 1976 $(u', v')$ horseshoe diagram.
  - Allow selectable comparison color spaces (sRGB, AdobeRGB, DCI-P3, Rec.2020) with exact 2D/3D gamut coverage and volume calculation.
- [ ] **One-Click Full Calibration Pipeline (Phase 1a $\to$ 1b $\to$ 2 $\to$ 3):**
  - Run Contrast Binary Search, D65 Whitepoint & Luminance Regulation, `targen`/`dispread`/`colprof` measurement, and open the Profile Inspector & Live Preview dialog in a single uninterrupted workflow.
- [ ] **Simple vs. Expert Mode in `kcal-gui`:**
  - *Simple / Wizard Mode:* Guided step-by-step assistant with presets (*"Photography / Print – 120 cd/m² D65"*, *"Office / Web – 140 cd/m² D65"*, *"Evening – 90 cd/m²"*).
  - *Expert Mode:* Current technical view with direct access to VCP search bounds, patch counts, and raw measurement logs.
- [ ] **Post-Calibration Verification ($\Delta E_{2000}$ Check):**
  - Measure 24 ColorChecker patches with the new ICC profile active in the Wayland compositor to verify end-to-end color accuracy (mean/max $\Delta E_{2000}$).
- [ ] **GNOME / Mutter Wayland Backend (`MutterBackend`):**
  - Complete `org.gnome.Mutter.DisplayConfig` + `colord` integration alongside `KWinBackend`.
