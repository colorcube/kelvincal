# Contributing to KelvinCal

Bug reports, test reports with other displays and instruments, translations and pull requests are welcome.

## Reporting a problem

Please open an [issue](https://github.com/colorcube/kelvincal/issues) and add:

- the output of `kelvincal-cli check` (setup) and `kelvincal-cli diag` (colour state of the displays),
- distribution, Plasma/KWin version, display model(s) and measuring instrument,
- what you did, what you expected and what happened; for a failed calibration the log from the expert mode
  ("Measurement & Diagnostic Log").

`kelvincal-cli diag` lists display models, connectors and EDID hashes; remove anything you do not want to share.

## Development

```bash
PYTHONPATH=packages python3 -m unittest discover -s tests   # runs offscreen, no hardware needed
```

- Code lives in `packages/kelvincal/` (see the README for the package layout). Keep new code close to the style of
  the surrounding code; type hints, short docstrings that say why.
- User-visible strings go through `translate("Context", "text")`; afterwards run `./bin/update-translations` and
  translate the new entries in `packages/kelvincal/gui/i18n/kelvincal_de.ts` (Qt Linguist).
- Changes to the GUI: regenerate the screenshots with `tools/screenshots.py`.
- Contributions are licensed under the GPL-3.0-or-later like KelvinCal itself. ArgyllCMS is only used as external
  programs.

## Translations

Copy `packages/kelvincal/gui/i18n/kelvincal_de.ts` to `kelvincal_<lang>.ts`, translate it with Qt Linguist and run
`./bin/update-translations`. The panel widget's texts are in `plasmoid/de.colorcube.kelvincal.applet/`.
