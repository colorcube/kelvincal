# Changelog

All notable changes to KelvinCal are listed here. Versions follow [Semantic Versioning](https://semver.org/).

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
