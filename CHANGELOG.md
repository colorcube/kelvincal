# Changelog

All notable changes to KelvinCal are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## 0.3.0 – 2026-11-21

- **Verification reference curve & black point compensation:**
  - Automatically match KWin 6's `gamma22` sRGB surface decoding (`ColorDescription::sRGB`) vs. piecewise `IEC 61966-2-1 sRGB` on other compositors, with a live reference-curve selector and optional **Black Point Compensation (`BPC`)** toggle in the Inspector Verification tab (recalculates $\Delta E_{00}$ without re-measuring) plus `--eotf` and `--bpc` options in `kelvincal-cli verify` and HTML report metadata
- **KWin Night Light & software dimming guard:**
  - Automatically inhibit KWin Night Light (`org.kde.KWin.NightLight`) over D-Bus during calibration, verification and spot checks, polling `currentTemperature` until the colour-temperature transition ramp back to daylight ($\approx 6500\text{ K}$) completes
  - Temporarily reset KWin software dimming (`brightness < 1.0`) to `100 %` on external monitors without working DDC/CI (or with `allowDdcCi = false`) and restore it afterwards with status/log notices, while keeping internal laptop backlights (`eDP`/`LVDS`/`DSI`) untouched
- **Colorimetric observers & software calibration:**
  - Adapt D65/D50 target whitepoint chromaticities to the active colorimetric observer (`2015_2`, `2015_10`, `1964_10`) across hardware regulation (1b), software calibration (`dispcal`), interactive adjustment and verification
  - Raised default `dispcal` quality from `-qv` (*Very Low*) to `-qm` (*Medium*), updated duration estimates, and pass target luminance (`-b <cd/m²>`) in software batch runs and unattended CLI runs (`--auto-start`)
- **DDC/CI hardware controls & state safety:**
  - Honour monitor-reported `max_brightness`, `max_contrast` (inclusive binary-search bounds and scaled Phase 1c step size) and `max_rgb_gain` across optimizers and visual whitepoint matching
  - Snapshot pre-calibration DDC state (`ddc_before`) before starting jobs for accurate Inspector A/B preview and profile discard, restore initial DDC values on Phase 2/3 cancel or error, preserve original pre-batch DDC state in crash recovery, wait `WHITE_SETTLE_S` after brightness steps, verify DDC readback on all exit paths of Phase 1c, and restore raw register values safely if a gain probe aborts
- **Internal cleanup:** centralised CIE $u'v'$, $\Delta u'v'$ and McCamy CCT helpers in `core/color.py` and unified the PTY/Unix-socket patch-hook runner for `dispread` and `dispcal`

## 0.2.2 – 2026-11-20

- **Software calibration patch measurement & outlier re-measuring:**
  - Pass `-K` (instead of `-k`) to `dispread` when running with `-d dummy -C hook` so that the 1D calibration curves (`.cal`) are actively applied to the RGB patch values displayed during profiling while still embedding the `CAL` table into the `.ti3` for the ICC `vcgt` tag
  - Parse the embedded `CAL` table from `.ti3` files and apply the 1D calibration curves when re-measuring outlier patches with `spotread`
- **Outlier check & slower colorimeters (e.g. Datacolor Spyder):**
  - Added a dark-floor stabilisation and adaptive baseline noise threshold in `ti3_check` so low-light quantization noise on dark patches and a single disturbed black patch no longer trigger false-positive outlier storms
  - Increased `spotread` measurement timeout (45 s) and startup timeout (25 s), and automatically confirm mid-session dark-calibration prompts so slower colorimeters do not time out during outlier re-measurement

## 0.2.1 – 2026-11-19

- **DDC/CI gain readback & write scaling for 0–255-register panels (PR #12 by `@patcarter883`):** automatically probes and normalises RGB gain channels (`0x16`/`0x18`/`0x1A`) on monitors whose firmware exposes raw 0–255 registers while advertising `max = 100` (scaled readback and passthrough raw channels), persisted per display EDID across presets, recovery and live inspector switching
- **openSUSE Tumbleweed packages (Issue #13):** added native openSUSE Tumbleweed RPM builds (`kelvincal-*.opensuse.noarch.rpm` and `kelvincal-plasmoid-*.opensuse.noarch.rpm`), updated `kscreen-doctor` package hints (`libkscreen6-plugin`) in the setup check and fixed Qt shutdown order under PySide6 6.12

## 0.2.0 – 2026-11-17

- **Three calibration workflows** in Simple Mode, Expert Mode and CLI (`--workflow ddc|software|profile`):
  - **Hardware DDC/CI + Profile (`ddc`):** hardware contrast (1a), RGB gain & luminance control loop (1b/1c) and ICC profile (2+3)
  - **Software calibration + Profile (`software`):** 1D `vcgt` calibration curves via `dispcal` (Phase 1s), applied during patch measurement (`dispread -k`) and embedded into the ICC profile (`vcgt` tag) for laptop panels (`eDP-*`) and monitors without DDC/CI
  - **Profile only (`profile`):** characterises the current display state without changing DDC registers or `vcgt` curves
- **Interactive display adjustment (Phase 1s)** before software calibration: live white point and luminance measurement loop in the Wayland patch window with target bars for R/G/B balance (`%`), luminance (`cd/m²`), CCT and $\Delta u'v'$ so brightness and OSD controls can be adjusted manually before `dispcal` starts
- **Patch count presets** in Simple Mode (Step 4) and CLI (`--patches fast|standard|high|<N>`): *Fast* (79), *Standard* (175), *High* (403) and *Custom* (50–2000) with target-based recommendation indicator and sensor-aware duration estimates (fast colorimeters vs. slower sensors)
- **CIE 2015 2° colorimetric observer (`-Q 2015_2`)** in Expert Mode and CLI (`--observer 1931_2|2015_2`) for improved visual white point agreement on wide-gamut LED and OLED displays
- **Profile types & `colprof` fit check (PR #9 by `@patcarter883`):** fixed Matrix profile option (`-a m` instead of `-a M`), added **Shaper + Matrix (`-a s`)** for OLED and wide-gamut displays, and added a fit-quality warning when `colprof`'s average error exceeds 3.0 ΔE00
- **Tone curve & $\gamma$ 2.4 handling (Issue #8):** added plain $\gamma$ 2.4 tone curve option in Expert Mode and stored target `gamma` and `tone_curve` in `.kelvincal.json` sidecars so saved 2.4 profiles keep their target reference in the inspector
- **Sensor USB settle & retry (Issue #2):** USB settle delay and exponential backoff retry when opening `spotread` for outlier re-measurement after `dispread`
- **Extended profile metadata & inspector:** sidecar `.kelvincal.json`, profile inspector KPIs and verification reports now record and display `workflow`, `observer`, `vcgt_active`, `patch_count`, `gamma` and `tone_curve`
- **Standalone CLI command `kelvincal-cli software-calibrate`** to measure `.cal` 1D calibration curves independently

## 0.1.0 – 2026-11-01

First public version, licensed under the GPL-3.0-or-later.

- Full calibration in one run: contrast search (1a), white point and luminance control loop over the display's
  RGB gains and brightness (1b), patch measurement with `dispread` (2) and profile with `colprof` (3); outlier
  check of the measurements before the profile is computed
- Targets for photo (D65/D50), office, sRGB, soft proof, video (BT.1886), evening and custom brightness; batch
  calibration of several targets with the sensor placed once
- Simple and expert mode; single phases, patch count, profile type, colorimeter correction and measurement mode
- Inspector: tone curves, effective gamma, kink check, gamut coverage, live switch between new profile, previous
  profile and uncalibrated, together with the matching hardware state
- ΔE2000 verification with 40 test patches, gray balance and HTML report
- Presets of DDC/CI values and ICC profiles for all displays; drift detection; Ctrl+1–9, Plasma panel widget,
  D-Bus interface and `kelvincal-cli`
- Colorimeter corrections (.ccss/.ccmx) per display, own corrections measured with a spectrometer; visual white
  point offset
- Setup check with fixes per distribution; recovery of the display state after an interrupted measurement
- KDE integration: Breeze style, system or chosen colour scheme, notifications, single instance
- English and German
- rpm (Fedora) and deb (Debian 13, Ubuntu) packages, the panel widget as a separate package
