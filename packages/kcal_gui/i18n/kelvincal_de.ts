<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="de_DE">
<context>
    <name>ContrastOptimizer</name>
    <message>
        <source>ΔL={delta_l:.2f} cd/m² &lt;= {limit:.2f} cd/m² (full clipping)</source>
        <translation>ΔL={delta_l:.2f} cd/m² &lt;= {limit:.2f} cd/m² (vollständiges Clipping)</translation>
    </message>
    <message>
        <source>Rel. step {gain:.2f}% &lt; {limit:.2f}% (highlight compression)</source>
        <translation>Rel. Stufe {gain:.2f} % &lt; {limit:.2f} % (Lichter-Kompression)</translation>
    </message>
    <message>
        <source>Δu&apos;v&apos;={delta_uv:.4f} &gt; {limit:.4f} (single-channel R/G/B clipping)</source>
        <translation>Δu&apos;v&apos;={delta_uv:.4f} &gt; {limit:.4f} (Clipping eines R/G/B-Kanals)</translation>
    </message>
    <message>
        <source>OK (no clipping)</source>
        <translation>OK (kein Clipping)</translation>
    </message>
</context>
<context>
    <name>Controller</name>
    <message>
        <source>Place the sensor centered on {connector} – [Space/Enter] start | [Esc] cancel</source>
        <translation>Sensor mittig auf {connector} legen – [Leertaste/Enter] Start | [Esc] Abbrechen</translation>
    </message>
    <message>
        <source>Phase 1a: binary contrast search on {display_label} [{min_contrast}..{max_contrast}]...</source>
        <translation>Phase 1a: Kontrast-Binärsuche auf {display_label} [{min_contrast}..{max_contrast}]...</translation>
    </message>
    <message>
        <source>✓ Optimal contrast: {optimal_contrast}% ({peak_luminance_cdm2:.1f} cd/m²)</source>
        <translation>✓ Optimaler Kontrast: {optimal_contrast}% ({peak_luminance_cdm2:.1f} cd/m²)</translation>
    </message>
    <message>
        <source>Phase 1b: whitepoint (x={x:.4f}, y={y:.4f}) &amp; luminance regulation ({target_luminance:.0f} cd/m²)...</source>
        <translation>Phase 1b: Weißpunkt- (x={x:.4f}, y={y:.4f}) &amp; Helligkeitsregelung ({target_luminance:.0f} cd/m²)...</translation>
    </message>
    <message>
        <source>✓ Whitepoint regulated: brightness {brightness}%, RGB ({red_gain}, {green_gain}, {blue_gain}), {Y:.1f} cd/m², {cct_kelvin:.0f} K</source>
        <translation>✓ Weißpunkt eingeregelt: Helligkeit {brightness}%, RGB ({red_gain}, {green_gain}, {blue_gain}), {Y:.1f} cd/m², {cct_kelvin:.0f} K</translation>
    </message>
    <message>
        <source>{connector} has no DDC/CI (I²C) bus; hardware phases are unavailable.</source>
        <translation>{connector} hat keinen DDC/CI-(I²C-)Bus; Hardware-Phasen sind nicht verfügbar.</translation>
    </message>
    <message>
        <source>Original DDC values restored.</source>
        <translation>Ursprüngliche DDC-Werte wiederhergestellt.</translation>
    </message>
    <message>
        <source>Could not restore DDC values: {exc}</source>
        <translation>DDC-Werte konnten nicht wiederhergestellt werden: {exc}</translation>
    </message>
</context>
<context>
    <name>ExpertPage</name>
    <message>
        <source>Outputs</source>
        <translation>Ausgänge</translation>
    </message>
    <message>
        <source>Bright.</source>
        <translation>Hell.</translation>
    </message>
    <message>
        <source>Contr.</source>
        <translation>Kontr.</translation>
    </message>
    <message>
        <source>Red</source>
        <translation>Rot</translation>
    </message>
    <message>
        <source>Green</source>
        <translation>Grün</translation>
    </message>
    <message>
        <source>Blue</source>
        <translation>Blau</translation>
    </message>
    <message>
        <source>Parameters</source>
        <translation>Parameter</translation>
    </message>
    <message>
        <source>Target template</source>
        <translation>Ziel-Vorlage</translation>
    </message>
    <message>
        <source>Target luminance</source>
        <translation>Ziel-Luminanz</translation>
    </message>
    <message>
        <source>Whitepoint</source>
        <translation>Weißpunkt</translation>
    </message>
    <message>
        <source>Reference curve for the profile check. Calibration curves are not generated yet.</source>
        <translation>Referenzkurve für die Profilprüfung. Kalibrierkurven werden noch nicht erzeugt.</translation>
    </message>
    <message>
        <source>Tone curve</source>
        <translation>Tonwertkurve</translation>
    </message>
    <message>
        <source>cLUT + Matrix</source>
        <translation>cLUT + Matrix</translation>
    </message>
    <message>
        <source>Matrix</source>
        <translation>Matrix</translation>
    </message>
    <message>
        <source>Profile type</source>
        <translation>Profiltyp</translation>
    </message>
    <message>
        <source>Min </source>
        <translation>Min </translation>
    </message>
    <message>
        <source>Max </source>
        <translation>Max </translation>
    </message>
    <message>
        <source>Contrast search range</source>
        <translation>Kontrast-Suchbereich</translation>
    </message>
    <message>
        <source>ΔY ratio </source>
        <translation>ΔY-Anteil </translation>
    </message>
    <message>
        <source>Minimum share of the ideal luminance step between 248 and 255 (highlight compression).</source>
        <translation>Mindestanteil der idealen Helligkeitsstufe zwischen 248 und 255 (Lichter-Kompression).</translation>
    </message>
    <message>
        <source>Clipping thresholds</source>
        <translation>Schwellwerte</translation>
    </message>
    <message>
        <source>Patch count (targen)</source>
        <translation>Patch-Anzahl (targen)</translation>
    </message>
    <message>
        <source>3D-LUT quality</source>
        <translation>3D-LUT-Qualität</translation>
    </message>
    <message>
        <source>Single phases</source>
        <translation>Phasen einzeln</translation>
    </message>
    <message>
        <source>Test patch window</source>
        <translation>Patch-Fenster testen</translation>
    </message>
    <message>
        <source>Check placement on the display</source>
        <translation>Platzierung auf dem Monitor prüfen</translation>
    </message>
    <message>
        <source>Phase 1a · Contrast binary search</source>
        <translation>Phase 1a · Kontrast-Binärsuche</translation>
    </message>
    <message>
        <source>6–7 measurements · approx. 20 s</source>
        <translation>6–7 Messungen · ca. 20 s</translation>
    </message>
    <message>
        <source>Phase 1b · Whitepoint &amp; luminance</source>
        <translation>Phase 1b · Weißpunkt &amp; Helligkeit</translation>
    </message>
    <message>
        <source>RGB gains + backlight via DDC</source>
        <translation>RGB-Gains + Backlight per DDC</translation>
    </message>
    <message>
        <source>Phase 2+3 · Profiling</source>
        <translation>Phase 2+3 · Profilierung</translation>
    </message>
    <message>
        <source>DDC values stay unchanged</source>
        <translation>DDC-Werte bleiben unverändert</translation>
    </message>
    <message>
        <source>Run All Phases</source>
        <translation>Alle Phasen ausführen</translation>
    </message>
    <message>
        <source>DDC/CI live · {connector}</source>
        <translation>DDC/CI live · {connector}</translation>
    </message>
</context>
<context>
    <name>LogPanel</name>
    <message>
        <source>Measurement &amp; Diagnostic Log</source>
        <translation>Mess- &amp; Diagnoseprotokoll</translation>
    </message>
    <message>
        <source>Copy</source>
        <translation>Kopieren</translation>
    </message>
    <message>
        <source>Export…</source>
        <translation>Exportieren…</translation>
    </message>
    <message>
        <source>Measurement and diagnostic log...</source>
        <translation>Mess- und Diagnoseprotokoll...</translation>
    </message>
    <message>
        <source>Export Log</source>
        <translation>Protokoll exportieren</translation>
    </message>
    <message>
        <source>Log files (*.log *.txt)</source>
        <translation>Protokolldateien (*.log *.txt)</translation>
    </message>
</context>
<context>
    <name>MainWindow</name>
    <message>
        <source>Refresh Displays</source>
        <translation>Monitore neu einlesen</translation>
    </message>
    <message>
        <source>Test Patch Window</source>
        <translation>Patch-Fenster testen</translation>
    </message>
    <message>
        <source>Reading displays via DRM sysfs, ddcutil, and compositor...</source>
        <translation>Lese Monitore über DRM-sysfs, ddcutil und KWin aus...</translation>
    </message>
    <message>
        <source>Display Detection Error</source>
        <translation>Fehler bei der Monitorerkennung</translation>
    </message>
    <message>
        <source>Opening Wayland fullscreen patch window on {display_label}...</source>
        <translation>Öffne Wayland-Vollbild-Patchfenster auf {display_label}...</translation>
    </message>
    <message>
        <source>Test Window on {display_label} – [Space/Esc] to close</source>
        <translation>Testfenster auf {display_label} – [Leertaste/Esc] zum Schließen</translation>
    </message>
    <message>
        <source>Contrast Optimizer Error</source>
        <translation>Fehler beim Kontrast-Optimizer</translation>
    </message>
    <message>
        <source>Whitepoint Optimizer Error</source>
        <translation>Fehler bei Weißpunkt-Regelung</translation>
    </message>
    <message>
        <source>Profiling Error</source>
        <translation>Fehler bei der Profilierung</translation>
    </message>
    <message>
        <source>Calibration Error</source>
        <translation>Fehler bei der Kalibrierung</translation>
    </message>
    <message>
        <source>Save Preset</source>
        <translation>Preset speichern</translation>
    </message>
    <message>
        <source>Name for the new/updated preset:</source>
        <translation>Name für das neue/aktualisierte Preset:</translation>
    </message>
    <message>
        <source>Preset Error</source>
        <translation>Preset-Fehler</translation>
    </message>
    <message>
        <source>Calibration running</source>
        <translation>Kalibrierung läuft</translation>
    </message>
    <message>
        <source>A measurement is still running. Cancel it and quit?</source>
        <translation>Eine Messung läuft noch. Abbrechen und beenden?</translation>
    </message>
    <message>
        <source>Displays detected: {count}</source>
        <translation>Erkannte Monitore: {count}</translation>
    </message>
    <message>
        <source>Cancelling...</source>
        <translation>Breche ab...</translation>
    </message>
    <message>
        <source>✓ ICC profile saved and activated in compositor: {saved_profile_path}</source>
        <translation>✓ ICC-Profil gespeichert und im Compositor aktiviert: {saved_profile_path}</translation>
    </message>
    <message>
        <source>ICC profile discarded; previous profile restored.</source>
        <translation>ICC-Profil verworfen; vorheriges Profil wiederhergestellt.</translation>
    </message>
    <message>
        <source>Select ICC Profile to Inspect</source>
        <translation>Zu prüfendes ICC-Profil auswählen</translation>
    </message>
    <message>
        <source>Preset &apos;{name}&apos; saved.</source>
        <translation>Preset &apos;{name}&apos; gespeichert.</translation>
    </message>
    <message>
        <source>&amp;File</source>
        <translation>&amp;Datei</translation>
    </message>
    <message>
        <source>Open ICC Profile…</source>
        <translation>ICC-Profil öffnen…</translation>
    </message>
    <message>
        <source>&amp;Quit</source>
        <translation>&amp;Beenden</translation>
    </message>
    <message>
        <source>&amp;View</source>
        <translation>&amp;Ansicht</translation>
    </message>
    <message>
        <source>Simple Mode</source>
        <translation>Einfacher Modus</translation>
    </message>
    <message>
        <source>Expert Mode</source>
        <translation>Expertenmodus</translation>
    </message>
    <message>
        <source>&amp;Calibration</source>
        <translation>&amp;Kalibrierung</translation>
    </message>
    <message>
        <source>Cancel Measurement</source>
        <translation>Messung abbrechen</translation>
    </message>
    <message>
        <source>&amp;Settings</source>
        <translation>&amp;Einstellungen</translation>
    </message>
    <message>
        <source>&amp;Help</source>
        <translation>&amp;Hilfe</translation>
    </message>
    <message>
        <source>About KelvinCal</source>
        <translation>Über KelvinCal</translation>
    </message>
    <message>
        <source>About Qt</source>
        <translation>Über Qt</translation>
    </message>
    <message>
        <source>Displays</source>
        <translation>Monitore</translation>
    </message>
    <message>
        <source>Presets</source>
        <translation>Presets</translation>
    </message>
    <message>
        <source>Profiles</source>
        <translation>Profile</translation>
    </message>
    <message>
        <source>Looking for sensor…</source>
        <translation>Suche Sensor…</translation>
    </message>
    <message>
        <source>Active preset</source>
        <translation>Aktives Preset</translation>
    </message>
    <message>
        <source>Simple</source>
        <translation>Einfach</translation>
    </message>
    <message>
        <source>Expert</source>
        <translation>Experte</translation>
    </message>
    <message>
        <source>Calibrate Display</source>
        <translation>Monitor kalibrieren</translation>
    </message>
    <message>
        <source>ArgyllCMS not found</source>
        <translation>ArgyllCMS nicht gefunden</translation>
    </message>
    <message>
        <source>{sensor} ready · Argyll {version}</source>
        <translation>{sensor} bereit · Argyll {version}</translation>
    </message>
    <message>
        <source>No sensor connected · Argyll {version}</source>
        <translation>Kein Sensor angeschlossen · Argyll {version}</translation>
    </message>
    <message>
        <source>{compositor} · {count} outputs</source>
        <translation>{compositor} · {count} Ausgänge</translation>
    </message>
    <message>
        <source>– none –</source>
        <translation>– keines –</translation>
    </message>
    <message>
        <source>Preset &apos;{name}&apos; activated.</source>
        <translation>Preset &apos;{name}&apos; aktiviert.</translation>
    </message>
    <message>
        <source>Duplicate Preset</source>
        <translation>Preset duplizieren</translation>
    </message>
    <message>
        <source>Name of the copy:</source>
        <translation>Name der Kopie:</translation>
    </message>
    <message>
        <source>{name} (copy)</source>
        <translation>{name} (Kopie)</translation>
    </message>
    <message>
        <source>Rename Preset</source>
        <translation>Preset umbenennen</translation>
    </message>
    <message>
        <source>New name:</source>
        <translation>Neuer Name:</translation>
    </message>
    <message>
        <source>Delete Preset</source>
        <translation>Preset löschen</translation>
    </message>
    <message>
        <source>Delete preset &apos;{name}&apos;?</source>
        <translation>Preset „{name}“ löschen?</translation>
    </message>
    <message>
        <source>Cancelled by user.</source>
        <translation>Vom Benutzer abgebrochen.</translation>
    </message>
    <message>
        <source>Calibration</source>
        <translation>Kalibrierung</translation>
    </message>
    <message>
        <source>Paused after the current measurement.</source>
        <translation>Pausiert nach der laufenden Messung.</translation>
    </message>
    <message>
        <source>Resumed.</source>
        <translation>Fortgesetzt.</translation>
    </message>
    <message>
        <source>Phase 1a</source>
        <translation>Phase 1a</translation>
    </message>
    <message>
        <source>Phase 1b</source>
        <translation>Phase 1b</translation>
    </message>
    <message>
        <source>Phase 2+3</source>
        <translation>Phase 2+3</translation>
    </message>
    <message>
        <source>All phases</source>
        <translation>Alle Phasen</translation>
    </message>
    <message>
        <source>Patch Window</source>
        <translation>Patch-Fenster</translation>
    </message>
    <message>
        <source>ICC Profiles (*.icc *.icm)</source>
        <translation>ICC-Profile (*.icc *.icm)</translation>
    </message>
    <message>
        <source>Profile Inspector Error</source>
        <translation>Fehler beim Profil-Inspektor</translation>
    </message>
    <message>
        <source>&lt;h3&gt;KelvinCal&lt;/h3&gt;&lt;p&gt;Wayland-native display calibration: DDC/CI hardware optimizer, ArgyllCMS profiling and multi-monitor presets.&lt;/p&gt;&lt;p&gt;License: GPL-3.0-or-later · Uses ArgyllCMS (AGPL) as external tools.&lt;/p&gt;</source>
        <translation>&lt;h3&gt;KelvinCal&lt;/h3&gt;&lt;p&gt;Wayland-native Monitorkalibrierung: DDC/CI-Hardware-Optimierung, ArgyllCMS-Profilierung und Multi-Monitor-Presets.&lt;/p&gt;&lt;p&gt;Lizenz: GPL-3.0-or-later · Nutzt ArgyllCMS (AGPL) als externe Werkzeuge.&lt;/p&gt;</translation>
    </message>
</context>
<context>
    <name>MonitorsPage</name>
    <message>
        <source>{source} (uncalibrated)</source>
        <translation>{source} (unkalibriert)</translation>
    </message>
    <message>
        <source>No DDC/CI values</source>
        <translation>Keine DDC/CI-Werte</translation>
    </message>
    <message>
        <source>Brightness {b} · Contrast {c} · RGB gain {g}</source>
        <translation>Helligkeit {b} · Kontrast {c} · RGB-Gain {g}</translation>
    </message>
    <message>
        <source>Drift</source>
        <translation>Drift</translation>
    </message>
    <message>
        <source>Live DDC values differ from the active preset.</source>
        <translation>Die aktuellen DDC-Werte weichen vom aktiven Preset ab.</translation>
    </message>
    <message>
        <source>Unknown model</source>
        <translation>Unbekanntes Modell</translation>
    </message>
    <message>
        <source>no DDC/CI</source>
        <translation>kein DDC/CI</translation>
    </message>
    <message>
        <source>ICC active</source>
        <translation>ICC aktiv</translation>
    </message>
    <message>
        <source>Show profile</source>
        <translation>Profil anzeigen</translation>
    </message>
    <message>
        <source>{patches} patches · approx. {minutes} min</source>
        <translation>{patches} Felder · ca. {minutes} min</translation>
    </message>
    <message>
        <source>Select display</source>
        <translation>Monitor wählen</translation>
    </message>
    <message>
        <source>Detecting displays…</source>
        <translation>Erkenne Monitore…</translation>
    </message>
    <message>
        <source>Purpose</source>
        <translation>Einsatzzweck</translation>
    </message>
    <message>
        <source>Calibration</source>
        <translation>Kalibrierung</translation>
    </message>
    <message>
        <source>Start Full Calibration</source>
        <translation>Komplett-Kalibrierung starten</translation>
    </message>
    <message>
        <source>No displays detected.</source>
        <translation>Keine Monitore erkannt.</translation>
    </message>
    <message>
        <source>No display selected</source>
        <translation>Kein Monitor gewählt</translation>
    </message>
    <message>
        <source>This display has no DDC/CI. Contrast, whitepoint and luminance cannot be set in hardware.</source>
        <translation>Dieser Monitor hat kein DDC/CI. Kontrast, Weißpunkt und Helligkeit lassen sich nicht in der Hardware einstellen.</translation>
    </message>
    <message>
        <source>Place the sensor once in the centre. Contrast, whitepoint, luminance and profile then run automatically, approx. {minutes} minutes.</source>
        <translation>Sensor einmal mittig auflegen. Kontrast, Weißpunkt, Helligkeit und Profil laufen danach automatisch durch, ca. {minutes} Minuten.</translation>
    </message>
</context>
<context>
    <name>PatchWindow</name>
    <message>
        <source>No screen found for connector {connector} (available: {available}).</source>
        <translation>Kein Bildschirm für Anschluss {connector} gefunden (verfügbar: {available}).</translation>
    </message>
</context>
<context>
    <name>Pipeline</name>
    <message>
        <source>Generating {count} test patches with targen...</source>
        <translation>Erzeuge {count} Messfelder mit targen...</translation>
    </message>
    <message>
        <source>Starting measurement ({count} patches, -g {gray} -m {multi}) with dispread...</source>
        <translation>Starte Messung ({count} Messfelder, -g {gray} -m {multi}) mit dispread...</translation>
    </message>
    <message>
        <source>  Measuring patch {index}/{total} ({pct}%) – RGB{rgb}</source>
        <translation>  Messe Feld {index}/{total} ({pct} %) – RGB{rgb}</translation>
    </message>
    <message>
        <source>Computing 3D-LUT / Matrix ICC profile with colprof ({name})...</source>
        <translation>Berechne 3D-LUT-/Matrix-ICC-Profil mit colprof ({name})...</translation>
    </message>
</context>
<context>
    <name>PresetsPage</name>
    <message>
        <source>Presets</source>
        <translation>Presets</translation>
    </message>
    <message>
        <source>Ctrl+1–9</source>
        <translation>Strg+1–9</translation>
    </message>
    <message>
        <source>Save Current State as Preset…</source>
        <translation>Aktuellen Zustand als Preset sichern…</translation>
    </message>
    <message>
        <source>Duplicate</source>
        <translation>Duplizieren</translation>
    </message>
    <message>
        <source>Rename…</source>
        <translation>Umbenennen…</translation>
    </message>
    <message>
        <source>Delete</source>
        <translation>Löschen</translation>
    </message>
    <message>
        <source>Activate</source>
        <translation>Aktivieren</translation>
    </message>
    <message>
        <source>Recalibrate this display…</source>
        <translation>Diesen Monitor neu kalibrieren…</translation>
    </message>
    <message>
        <source>Recalibrate…</source>
        <translation>Neu kalibrieren…</translation>
    </message>
    <message>
        <source>Show Profile</source>
        <translation>Profil anzeigen</translation>
    </message>
    <message>
        <source>Selected display:</source>
        <translation>Gewählter Monitor:</translation>
    </message>
    <message>
        <source>Displays are matched by EDID hash (connector as fallback). Values in brackets are the live values if they differ from the preset.</source>
        <translation>Monitore werden über den EDID-Hash zugeordnet (Anschluss als Rückfall). Werte in Klammern sind die aktuellen Werte, wenn sie vom Preset abweichen.</translation>
    </message>
    <message>
        <source>active</source>
        <translation>aktiv</translation>
    </message>
    <message>
        <source>{count} displays</source>
        <translation>{count} Monitore</translation>
    </message>
    <message>
        <source>No preset</source>
        <translation>Kein Preset</translation>
    </message>
    <message>
        <source>Save the current display state to switch back to it later with one click.</source>
        <translation>Sichere den aktuellen Monitorzustand, um später mit einem Klick dorthin zurückzuschalten.</translation>
    </message>
    <message>
        <source>Active · </source>
        <translation>Aktiv · </translation>
    </message>
    <message>
        <source>Active</source>
        <translation>Aktiv</translation>
    </message>
    <message>
        <source>&lt;b&gt;{connector} differs from the preset:&lt;/b&gt; {fields}.</source>
        <translation>&lt;b&gt;{connector} weicht vom Preset ab:&lt;/b&gt; {fields}.</translation>
    </message>
    <message>
        <source>Brightness</source>
        <translation>Helligkeit</translation>
    </message>
    <message>
        <source>Contrast</source>
        <translation>Kontrast</translation>
    </message>
    <message>
        <source>Gain red</source>
        <translation>Gain Rot</translation>
    </message>
    <message>
        <source>Gain green</source>
        <translation>Gain Grün</translation>
    </message>
    <message>
        <source>Gain blue</source>
        <translation>Gain Blau</translation>
    </message>
    <message>
        <source>ICC profile</source>
        <translation>ICC-Profil</translation>
    </message>
    <message>
        <source>(live {value})</source>
        <translation>(live {value})</translation>
    </message>
</context>
<context>
    <name>ProfileInspector</name>
    <message>
        <source>{channel} TRC reversal at {pct:.1f}% input (output drops by {drop:.2f}%).</source>
        <translation>{channel}-Kurvenknick (Rückläufigkeit) bei {pct:.1f}% Signalpegel (Ausgang fällt um {drop:.2f}% ab).</translation>
    </message>
    <message>
        <source>{channel} TRC slope discontinuity (&apos;kink&apos;) near {pct:.0f}% input.</source>
        <translation>{channel}-Tonwertkurve zeigt einen Steigungsknick nahe {pct:.0f}%.</translation>
    </message>
    <message>
        <source>Luminance reversal between {from_pct:.1f}% ({from_y:.2f} cd/m²) and {to_pct:.1f}% ({to_y:.2f} cd/m²). Possible measurement glitch.</source>
        <translation>Helligkeitsabfall (Knick) zwischen {from_pct:.1f}% ({from_y:.2f} cd/m²) und {to_pct:.1f}% ({to_y:.2f} cd/m²). Möglicher Messfehler.</translation>
    </message>
    <message>
        <source>Tone curve kink at {input_pct:.1f}% (local deviation spike of {spike:.1f}%).</source>
        <translation>Knick in der gemessenen Tonwertkurve bei {input_pct:.1f}% (lokaler Ausreißer von {spike:.1f}%).</translation>
    </message>
    <message>
        <source>Grayscale color shift spike at {input_pct:.1f}% (Δu&apos;v&apos; step = {duv_jump:.4f}).</source>
        <translation>Farbsprung in der Graubalance bei {input_pct:.1f}% (Δu&apos;v&apos;-Sprung = {duv_jump:.4f}).</translation>
    </message>
    <message>
        <source>Measured {ch} channel reversal between {p0:.1f}% and {p1:.1f}%.</source>
        <translation>Gemessener {ch}-Kanal-Knick (Rückläufigkeit) zwischen {p0:.1f}% und {p1:.1f}%.</translation>
    </message>
    <message>
        <source>Measured {ch} channel kink at {p_spike:.1f}% ({spike:.1f}% spike).</source>
        <translation>Gemessener {ch}-Kanal-Knick bei {p_spike:.1f}% ({spike:.1f}% Ausreißer).</translation>
    </message>
</context>
<context>
    <name>ProfileReview</name>
    <message>
        <source>KelvinCal – ICC Profile Inspector &amp; Live Preview</source>
        <translation>KelvinCal – ICC-Profil-Inspektor &amp; Live-Vorschau</translation>
    </message>
    <message>
        <source>1. Tone Response Curves (RGB TRC &amp; .ti3 vs. γ=2.2)</source>
        <translation>1. Tonwertübertragungskurven (RGB-TRC &amp; .ti3 ggü. γ=2.2)</translation>
    </message>
    <message>
        <source>2. Gamma Curve γ(x) across Signal Level (DisplayCAL Style)</source>
        <translation>2. Gamma-Verlauf γ(x) über Signalpegel (DisplayCAL-Ansicht)</translation>
    </message>
    <message>
        <source>3. Kink Magnifier (Deviation Δ% from Ideal γ=2.2)</source>
        <translation>3. Knick-Lupe (Abweichung Δ% von Ideal γ=2.2)</translation>
    </message>
    <message>
        <source>4. Gamut (CIE 1931 xy vs. sRGB)</source>
        <translation>4. Farbraum (CIE 1931 xy ggü. sRGB)</translation>
    </message>
    <message>
        <source>Red</source>
        <translation>Rot</translation>
    </message>
    <message>
        <source>Green</source>
        <translation>Grün</translation>
    </message>
    <message>
        <source>Blue</source>
        <translation>Blau</translation>
    </message>
    <message>
        <source>Measured .ti3 Points</source>
        <translation>Messpunkte (.ti3)</translation>
    </message>
    <message>
        <source>Ideal γ=2.2 Reference</source>
        <translation>Referenzkurve γ=2.2</translation>
    </message>
    <message>
        <source>Hover over graph to inspect exact RGB &amp; gamma values</source>
        <translation>Maus über den Graphen bewegen für exakte RGB- &amp; Gamma-Werte</translation>
    </message>
    <message>
        <source>&lt;b&gt;White Level:&lt;/b&gt; {w_str}</source>
        <translation>&lt;b&gt;Weißwert:&lt;/b&gt; {w_str}</translation>
    </message>
    <message>
        <source>&lt;b&gt;Black Level:&lt;/b&gt; {b_str}</source>
        <translation>&lt;b&gt;Schwarzwert:&lt;/b&gt; {b_str}</translation>
    </message>
    <message>
        <source>&lt;b&gt;Static Contrast:&lt;/b&gt; {c_str}</source>
        <translation>&lt;b&gt;Statischer Kontrast:&lt;/b&gt; {c_str}</translation>
    </message>
    <message>
        <source>&lt;b&gt;Whitepoint:&lt;/b&gt; {wp_str}</source>
        <translation>&lt;b&gt;Weißpunkt:&lt;/b&gt; {wp_str}</translation>
    </message>
    <message>
        <source>&lt;b&gt;Gamma &amp; Gamut:&lt;/b&gt; {g_str} ({total_measured_patches} patches)</source>
        <translation>&lt;b&gt;Gamma &amp; Farbraum:&lt;/b&gt; {g_str} ({total_measured_patches} Messfelder)</translation>
    </message>
    <message>
        <source>Open ICC Profile</source>
        <translation>ICC-Profil öffnen</translation>
    </message>
    <message>
        <source>Save ICC Profile As</source>
        <translation>ICC-Profil speichern unter</translation>
    </message>
    <message>
        <source>Input Signal Level RGB (%)</source>
        <translation>Eingangssignal RGB (%)</translation>
    </message>
    <message>
        <source>Load Another .icc File...</source>
        <translation>Andere .icc-Datei öffnen...</translation>
    </message>
    <message>
        <source>Channels:</source>
        <translation>Kanäle:</translation>
    </message>
    <message>
        <source>Live Monitor Preview on {connector} (Instant Switching)</source>
        <translation>Live-Monitor-Vorschau auf {connector} (Sofort-Umschaltung)</translation>
    </message>
    <message>
        <source>New / Inspected ICC Profile</source>
        <translation>Neues / Geprüftes ICC-Profil</translation>
    </message>
    <message>
        <source>Previous Profile ({prev_name})</source>
        <translation>Vorheriges Profil ({prev_name})</translation>
    </message>
    <message>
        <source>Uncalibrated (Compositor sRGB)</source>
        <translation>Unkalibriert (KWin sRGB)</translation>
    </message>
    <message>
        <source>Discard &amp; Restore Previous Profile</source>
        <translation>Verwerfen &amp; vorheriges Profil wiederherstellen</translation>
    </message>
    <message>
        <source>Save Profile As...</source>
        <translation>Profil speichern unter...</translation>
    </message>
    <message>
        <source>Save &amp; Activate ({name})</source>
        <translation>Speichern &amp; Aktivieren ({name})</translation>
    </message>
    <message>
        <source>Close</source>
        <translation>Schließen</translation>
    </message>
    <message>
        <source>&lt;b&gt;Curve Check:&lt;/b&gt; &lt;span style=&apos;background-color:#15803d; color:#ffffff; padding:2px 6px;&apos;&gt; ✓ Smooth &amp;amp; monotonic (no kinks) &lt;/span&gt;</source>
        <translation>&lt;b&gt;Knick-Check:&lt;/b&gt; &lt;span style=&apos;background-color:#15803d; color:#ffffff; padding:2px 6px;&apos;&gt; ✓ Glatt &amp;amp; monoton (keine Knicke) &lt;/span&gt;</translation>
    </message>
    <message>
        <source>No discontinuities, reversals, or grayscale balance spikes were detected.</source>
        <translation>Keine Unstetigkeiten, Rückläufigkeiten oder Graubalance-Ausreißer erkannt.</translation>
    </message>
    <message>
        <source>&lt;b&gt;Curve Check:&lt;/b&gt; &lt;span style=&apos;background-color:{bg_color}; color:#ffffff; padding:2px 6px;&apos;&gt; ⚠ {count} anomaly/kink(s) found &lt;/span&gt;</source>
        <translation>&lt;b&gt;Knick-Check:&lt;/b&gt; &lt;span style=&apos;background-color:{bg_color}; color:#ffffff; padding:2px 6px;&apos;&gt; ⚠ {count} Auffälligkeit(en) gefunden &lt;/span&gt;</translation>
    </message>
    <message>
        <source>Preview Switch Error</source>
        <translation>Fehler beim Vorschau-Umschalten</translation>
    </message>
    <message>
        <source>Profile Load Error</source>
        <translation>Fehler beim Laden des Profils</translation>
    </message>
</context>
<context>
    <name>ProfilesPage</name>
    <message>
        <source>Description</source>
        <translation>Beschreibung</translation>
    </message>
    <message>
        <source>In use on</source>
        <translation>Aktiv auf</translation>
    </message>
    <message>
        <source>Type</source>
        <translation>Typ</translation>
    </message>
    <message>
        <source>Created</source>
        <translation>Erstellt</translation>
    </message>
    <message>
        <source>File</source>
        <translation>Datei</translation>
    </message>
    <message>
        <source>Open in Inspector</source>
        <translation>Im Inspektor öffnen</translation>
    </message>
    <message>
        <source>Open Other File…</source>
        <translation>Andere Datei öffnen…</translation>
    </message>
    <message>
        <source>Show Folder</source>
        <translation>Ordner anzeigen</translation>
    </message>
</context>
<context>
    <name>RunningPage</name>
    <message>
        <source>Calibration running</source>
        <translation>Kalibrierung läuft</translation>
    </message>
    <message>
        <source>Pause</source>
        <translation>Pausieren</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>Abbrechen</translation>
    </message>
    <message>
        <source>Back to Overview</source>
        <translation>Zurück zur Übersicht</translation>
    </message>
    <message>
        <source>Contrast</source>
        <translation>Kontrast</translation>
    </message>
    <message>
        <source>Whitepoint &amp; luminance</source>
        <translation>Weißpunkt &amp; Helligkeit</translation>
    </message>
    <message>
        <source>Patch measurement</source>
        <translation>Patch-Messung</translation>
    </message>
    <message>
        <source>Profile computation</source>
        <translation>Profilberechnung</translation>
    </message>
    <message>
        <source>Waiting for sensor placement…</source>
        <translation>Warte auf Sensor-Platzierung…</translation>
    </message>
    <message>
        <source>Last measured</source>
        <translation>Zuletzt gemessen</translation>
    </message>
    <message>
        <source>Do not move the sensor. The patch window shows only a dim progress line.</source>
        <translation>Sensor nicht bewegen. Das Patch-Fenster zeigt nur eine dezente Fortschrittszeile.</translation>
    </message>
    <message>
        <source>1a · Contrast binary search</source>
        <translation>1a · Binärsuche Kontrast</translation>
    </message>
    <message>
        <source>green: no clipping · red: clipping</source>
        <translation>grün: kein Clipping · rot: Clipping</translation>
    </message>
    <message>
        <source>1b · Control loop</source>
        <translation>1b · Regelschleife</translation>
    </message>
    <message>
        <source>Bright.</source>
        <translation>Hell.</translation>
    </message>
    <message>
        <source>&lt;b&gt;ColorGuard active.&lt;/b&gt; {connector} runs as uncalibrated sRGB during the measurement, HDR/WCG off. The previous state is restored after completion or cancellation.</source>
        <translation>&lt;b&gt;ColorGuard aktiv.&lt;/b&gt; {connector} läuft während der Messung als unkalibriertes sRGB, HDR/WCG aus. Der vorherige Zustand wird nach Abschluss oder Abbruch wiederhergestellt.</translation>
    </message>
    <message>
        <source>skipped</source>
        <translation>übersprungen</translation>
    </message>
    <message>
        <source>[Space/Enter] start · [Esc] cancel in the patch window</source>
        <translation>[Leertaste/Enter] Start · [Esc] Abbrechen im Patch-Fenster</translation>
    </message>
    <message>
        <source>Calibration finished</source>
        <translation>Kalibrierung abgeschlossen</translation>
    </message>
    <message>
        <source>Calibration cancelled</source>
        <translation>Kalibrierung abgebrochen</translation>
    </message>
    <message>
        <source>Calibration failed</source>
        <translation>Kalibrierung fehlgeschlagen</translation>
    </message>
    <message>
        <source>All phases completed.</source>
        <translation>Alle Phasen abgeschlossen.</translation>
    </message>
    <message>
        <source>Cancelled. The previous display state was restored.</source>
        <translation>Abgebrochen. Der vorherige Monitorzustand wurde wiederhergestellt.</translation>
    </message>
    <message>
        <source>Resume</source>
        <translation>Fortsetzen</translation>
    </message>
    <message>
        <source>Phase 3 · Profile computation (colprof)</source>
        <translation>Phase 3 · Profilberechnung (colprof)</translation>
    </message>
    <message>
        <source>approx. {minutes} min left</source>
        <translation>noch ca. {minutes} min</translation>
    </message>
    <message>
        <source>measurements</source>
        <translation>Messungen</translation>
    </message>
    <message>
        <source>Phase 2 · Patch measurement</source>
        <translation>Phase 2 · Patch-Messung</translation>
    </message>
    <message>
        <source>Patch {index} / {total}   Target RGB {r} {g} {b}</source>
        <translation>Feld {index} / {total}   Soll-RGB {r} {g} {b}</translation>
    </message>
</context>
<context>
    <name>Targets</name>
    <message>
        <source>sRGB curve</source>
        <translation>sRGB-Kurve</translation>
    </message>
    <message>
        <source>L* curve</source>
        <translation>L*-Kurve</translation>
    </message>
    <message>
        <source>Photography &amp; Prepress</source>
        <translation>Fotografie &amp; Druckvorstufe</translation>
    </message>
    <message>
        <source>Office, Web &amp; Everyday</source>
        <translation>Büro, Web &amp; Alltag</translation>
    </message>
    <message>
        <source>sRGB</source>
        <translation>sRGB</translation>
    </message>
    <message>
        <source>Softproof</source>
        <translation>Softproof</translation>
    </message>
    <message>
        <source>Video / Rec.709</source>
        <translation>Video / Rec.709</translation>
    </message>
    <message>
        <source>Evening / Dark Room</source>
        <translation>Abend / Dunkelraum</translation>
    </message>
    <message>
        <source>Custom Luminance</source>
        <translation>Eigene Helligkeit</translation>
    </message>
</context>
<context>
    <name>Theme</name>
    <message>
        <source>Color Scheme</source>
        <translation>Farbschema</translation>
    </message>
    <message>
        <source>Default (System)</source>
        <translation>Standard (System)</translation>
    </message>
</context>
</TS>
