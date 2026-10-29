# KelvinCal (`kcal_*`)

Modular, Wayland-native display calibration, DDC/CI hardware optimizer, and multi-monitor preset switcher for Linux desktops (built for **KDE Plasma 6 / KWin**, extensible to **GNOME / Mutter**).

## Features

- **Sub-Millisecond Hardware Discovery (`kcal_core`):** Links DRM sysfs (`/sys/class/drm/card*-*/edid` MD5 hash, model, ASCII serial number, and `/dev/i2c-*` bus) directly with the Wayland compositor (`kscreen-doctor` / `kwinoutputconfig.json`). Differentiates identical monitor models even when numeric EDID serial headers are generic.
- **Double-Profiling Protection (`CalibrationColorGuard`):** Automatically switches the target monitor to uncalibrated `sRGB` and disables HDR/WCG in KWin during measurements, restoring or activating the target ICC profile afterwards.
- **Fast Binary-Search Contrast Optimizer (`kcal_ddc`):** Finds the highest unclipped hardware DDC contrast (`VCP 0x12`) in 6–7 steps (~20 seconds) by evaluating both relative luminance step ratios ($\Delta Y / Y$) and CIE 1976 $\Delta u'v'$ chromaticity shifts (reliably catching single-channel R/G/B clipping).
- **Automated D65 Whitepoint & Luminance Controller (`kcal_ddc`):** Regulates hardware RGB gains (`VCP 0x16, 0x18, 0x1A` with the dominant channel anchored at `100` to preserve contrast) and backlight brightness (`VCP 0x10`) to hit target D65 ($6500\text{ K}$) and luminance (e.g. $140\text{ cd/m}^2$).
- **Wayland-Native ArgyllCMS Integration (`kcal_argyll`, `kcal_gui`):**
  - Persistent PTY session for `spotread -e` (initializes the USB colorimeter only once).
  - Synchronous `dispread -d dummy -C` Unix Domain Socket bridge driving a frameless fullscreen Qt 6 Wayland patch window (`QWindow.setScreen()`) on the exact target monitor.
- **ICC Profile Inspector ("Knick-Check") & Live A/B Preview (`kcal_argyll`, `kcal_gui`):**
  - Interactive curve viewer displaying RGB Tone Response Curves (`rTRC`, `gTRC`, `bTRC`), `.ti3` grayscale measurements vs. ideal $\gamma = 2.2$, a magnified deviation mode (`Δ%`), static contrast ratio ($Y_{\text{max}} : Y_{\text{min}}$), and automatic kink/discontinuity detection.
  - Allows instant live A/B switching (*New Profile* $\leftrightarrow$ *Previous Profile* $\leftrightarrow$ *Uncalibrated sRGB*) on the monitor before deciding whether to save or discard a newly generated profile.
- **250 ms Multi-Monitor Preset Switcher (`kcal_presets` & KDE Plasma 6 Plasmoid):** Switches DDC/CI brightness, contrast, RGB gains, and KWin ICC profiles across multiple monitors in parallel.

## Architecture (`packages/`)

| Package | Responsibility |
| :--- | :--- |
| **`kcal_core`** | Data models, colorimetry math ($\text{XYZ} \leftrightarrow xyY \leftrightarrow u'v'$, CCT), sysfs EDID/I²C discovery, the `translate()` wrapper for Qt translations, and `CompositorBackend` (`KWinBackend`, `colord`, `MutterBackend` stub). |
| **`kcal_ddc`** | Fast `ddcutil` client (`--sleep-multiplier 0.2`), binary-search `ContrastOptimizer`, and 2-DoF tristimulus `WhitepointOptimizer`. |
| **`kcal_argyll`** | Persistent `SpotreadSession` PTY controller, `CalibrationPipeline` (`targen` $\to$ `dispread` $\to$ `colprof`), and `profile_inspector` (ICC / `.ti3` parser & kink detector). |
| **`kcal_presets`** | Preset manager (`~/.config/kelvincal/presets.json`) with delta-checking and parallel I²C updates. |
| **`kcal_gui`** | CLI (`kcal-cli`), Qt 6 / PySide6 GUI (`kcal-gui`), `WaylandPatchWindow`, and `ProfileReviewDialog`. |

## Quick Start

```bash
# Show detected monitors, I²C buses, live DDC hardware values, and active ICC profiles:
./bin/kcal-cli status

# Inspect an ICC profile for tone curve smoothness, contrast ratio, and kinks:
./bin/kcal-cli inspect-profile ~/.local/share/icc/my_profile.icc

# Capture current setup across all connected monitors as a preset:
./bin/kcal-cli capture-preset "Photography (140 cd/m² D65)"

# List or apply saved presets:
./bin/kcal-cli list-presets
./bin/kcal-cli apply-preset "Photography (140 cd/m² D65)"

# Launch the Qt 6 GUI:
./bin/kcal-gui

# Run unit tests:
PYTHONPATH=packages python3 -m unittest discover -s tests -v
```

## Translations

The source language is English. User-visible strings use `translate("Context", "text")` (`kcal_core.i18n`) and are
translated with Qt Linguist files in `packages/kcal_gui/i18n/` (`kelvincal_<lang>.ts` → `.qm`). The GUI picks the
system locale; `KELVINCAL_LANG=en|de` overrides it. The CLI output stays English.

```bash
# After changing UI strings: update the .ts files and rebuild the .qm files (needs qt6-linguist):
./bin/update-translations
# Then translate new entries with Qt Linguist:
linguist-qt6 packages/kcal_gui/i18n/kelvincal_de.ts
```

## Roadmap

The detailed task list lives outside the repository (`Dokumente/TODO-KelvinCal.md`). Longer-term goals:

- **GNOME / Mutter backend (`MutterBackend`):** apply and read ICC profiles via `org.gnome.Mutter.DisplayConfig` and `colord` (currently a stub).
- **Deeper KDE integration:** `KNotification`, `KAboutData`, a D-Bus interface used by the Plasmoid.

## License

GNU General Public License v3.0 or later – see [LICENSE](LICENSE).
