# KelvinCal

Modular, Wayland-native display calibration, DDC/CI hardware optimizer, and multi-monitor preset switcher for Linux desktops (built for **KDE Plasma 6 / KWin**, extensible to **GNOME / Mutter**).

## Features

- **Sub-Millisecond Hardware Discovery (`kelvincal.core`):** Links DRM sysfs (`/sys/class/drm/card*-*/edid` MD5 hash, model, ASCII serial number, and `/dev/i2c-*` bus) directly with the Wayland compositor (`kscreen-doctor` / `kwinoutputconfig.json`). Differentiates identical monitor models even when numeric EDID serial headers are generic.
- **Double-Profiling Protection (`CalibrationColorGuard`):** Automatically switches the target monitor to uncalibrated `sRGB` and disables HDR/WCG in KWin during measurements, restoring or activating the target ICC profile afterwards.
- **Fast Binary-Search Contrast Optimizer (`kelvincal.ddc`):** Finds the highest unclipped hardware DDC contrast (`VCP 0x12`) in 6–7 steps (~20 seconds) by evaluating both relative luminance step ratios ($\Delta Y / Y$) and CIE 1976 $\Delta u'v'$ chromaticity shifts (reliably catching single-channel R/G/B clipping).
- **Automated D65 Whitepoint & Luminance Controller (`kelvincal.ddc`):** Regulates hardware RGB gains (`VCP 0x16, 0x18, 0x1A` with the dominant channel anchored at `100` to preserve contrast) and backlight brightness (`VCP 0x10`) to hit target D65 ($6500\text{ K}$) and luminance (e.g. $140\text{ cd/m}^2$).
- **Wayland-Native ArgyllCMS Integration (`kelvincal.argyll`, `kelvincal.gui`):**
  - Persistent PTY session for `spotread -e` (initializes the USB colorimeter only once).
  - Synchronous `dispread -d dummy -C` Unix Domain Socket bridge driving a frameless fullscreen Qt 6 Wayland patch window (`QWindow.setScreen()`) on the exact target monitor.
- **ICC Profile Inspector ("Knick-Check") & Live A/B Preview (`kelvincal.argyll`, `kelvincal.gui`):**
  - Interactive curve viewer displaying RGB Tone Response Curves (`rTRC`, `gTRC`, `bTRC`), `.ti3` grayscale measurements vs. ideal $\gamma = 2.2$, a magnified deviation mode (`Δ%`), static contrast ratio ($Y_{\text{max}} : Y_{\text{min}}$), and automatic kink/discontinuity detection.
  - Allows instant live A/B switching (*New Profile* $\leftrightarrow$ *Previous Profile* $\leftrightarrow$ *Uncalibrated sRGB*) on the monitor before deciding whether to save or discard a newly generated profile.
- **250 ms Multi-Monitor Preset Switcher (`kelvincal.presets` & KDE Plasma 6 Plasmoid):** Switches DDC/CI brightness, contrast, RGB gains, and KWin ICC profiles across multiple monitors in parallel.

## Architecture (`packages/`)

| Package | Responsibility |
| :--- | :--- |
| **`kelvincal.core`** | Data models, colorimetry math ($\text{XYZ} \leftrightarrow xyY \leftrightarrow u'v'$, CCT), sysfs EDID/I²C discovery, the `translate()` wrapper for Qt translations, and `CompositorBackend` (`KWinBackend`, `colord`, `MutterBackend` stub). |
| **`kelvincal.ddc`** | Fast `ddcutil` client (`--sleep-multiplier 0.2`), binary-search `ContrastOptimizer`, and 2-DoF tristimulus `WhitepointOptimizer`. |
| **`kelvincal.argyll`** | Persistent `SpotreadSession` PTY controller, `CalibrationPipeline` (`targen` $\to$ `dispread` $\to$ `colprof`), and `profile_inspector` (ICC / `.ti3` parser & kink detector). |
| **`kelvincal.presets`** | Preset manager (`~/.config/kelvincal/presets.json`) with delta-checking and parallel I²C updates. |
| **`kelvincal.gui`** | CLI (`kelvincal-cli`), Qt 6 / PySide6 GUI (`kelvincal`), `WaylandPatchWindow`, and `ProfileReviewDialog`. |

## Quick Start

```bash
# Show detected monitors, I²C buses, live DDC hardware values, and active ICC profiles:
./bin/kelvincal-cli status

# Inspect an ICC profile for tone curve smoothness, contrast ratio, and kinks:
./bin/kelvincal-cli inspect-profile ~/.local/share/icc/my_profile.icc

# Capture current setup across all connected monitors as a preset:
./bin/kelvincal-cli capture-preset "Photography (140 cd/m² D65)"

# List or apply saved presets:
./bin/kelvincal-cli list-presets
./bin/kelvincal-cli apply-preset "Photography (140 cd/m² D65)"

# Once: link kelvincal/kelvincal-cli into ~/.local/bin and install the desktop entry
# (the app ID must be known to the XDG portal, otherwise Qt warns "App info not found"):
./bin/install-desktop

# Diagnostics snapshot (read-only): KWin colour settings, live DDC values, active ICC profile
# (white point, vcgt curves, stored KelvinCal hardware state), active preset and drift:
./bin/kelvincal-cli diag
# … plus a sensor measurement of white/black in the current state, saved to a file:
./bin/kelvincal-cli diag --measure DP-2 -o diag-dp2.txt

# Batch: several targets one after another with the sensor placed once (profiles + DDC sidecars are
# saved, the display is restored afterwards; screen locking/suspend are inhibited during the run).
# Like the GUI it uses the correction file and the visual whitepoint offset stored for the display
# (override with --ccss FILE|none and --white-offset DX,DY):
./bin/kelvincal-cli batch -c DP-2 -t office,photo,evening

# ΔE00 verification of the active profile; unattended (sensor already placed) with --auto-start:
./bin/kelvincal-cli verify -c DP-2 --auto-start 3 -o verification.html
# White/black of the bare hardware state (ColorGuard, no ICC profile):
./bin/kelvincal-cli diag --measure DP-2 --raw --auto-start 3

# Own colorimeter correction for a display, measured with a spectrometer (e.g. i1 Pro); the patch
# window asks for the calibration (tile/cap) and for placing the instrument. Assign it to the display in
# the GUI (expert mode; or measure it there: "Measure Own…") or pass it with --ccss:
./bin/kelvincal-cli make-ccss -c DP-2
./bin/kelvincal-cli batch -c DP-2 -t office --ccss ~/.local/share/ArgyllCMS/KelvinCal_DP-2_<model>_<date>.ccss

# Presets, display states and drift from the active preset (also used by the plasmoid):
./bin/kelvincal-cli overview

# Launch the Qt 6 GUI (a second start, e.g. with --display DP-2, raises the running window):
./bin/kelvincal

# Run unit tests:
PYTHONPATH=packages python3 -m unittest discover -s tests -v
```

## Translations

The source language is English. User-visible strings use `translate("Context", "text")` (`kelvincal.core.i18n`) and are
translated with Qt Linguist files in `packages/kelvincal/gui/i18n/` (`kelvincal_<lang>.ts` → `.qm`). The GUI picks the
system locale; `KELVINCAL_LANG=en|de` overrides it. The CLI output stays English.

```bash
# After changing UI strings: update the .ts files and rebuild the .qm files (needs qt6-linguist):
./bin/update-translations
# Then translate new entries with Qt Linguist:
linguist-qt6 packages/kelvincal/gui/i18n/kelvincal_de.ts
```

## Roadmap

The detailed task list lives outside the repository (`Dokumente/TODO-KelvinCal.md`). Longer-term goals:

- **GNOME / Mutter backend (`MutterBackend`):** apply and read ICC profiles via `org.gnome.Mutter.DisplayConfig` and `colord` (currently a stub).
- **Deeper KDE integration:** `KNotification`, `KAboutData`, a D-Bus interface used by the Plasmoid.

## License

GNU General Public License v3.0 or later – see [LICENSE](LICENSE).
