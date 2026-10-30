<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="de_DE">
<context>
    <name>BatchDialog</name>
    <message>
        <source>Batch Calibration</source>
        <translation>Batch-Kalibrierung</translation>
    </message>
    <message>
        <source>Calibrate several targets on {display}</source>
        <translation>Mehrere Ziele auf {display} kalibrieren</translation>
    </message>
    <message>
        <source>The sensor is placed once; the targets then run one after another without any questions (contrast search once, then whitepoint, patches, profile and verification per target). Every profile is saved with its hardware settings. Afterwards the display returns to its previous state, ready to combine the profiles into presets.</source>
        <translation>Das Messgerät wird einmal angesetzt; danach laufen die Ziele ohne Rückfragen nacheinander (Kontrastsuche einmal, dann je Ziel Weißpunkt, Messfelder, Profil und Verifikation). Jedes Profil wird mit seinen Hardware-Einstellungen gespeichert. Anschließend kehrt der Monitor in seinen vorherigen Zustand zurück – bereit, die Profile zu Presets zusammenzustellen.</translation>
    </message>
    <message>
        <source>Target</source>
        <translation>Ziel</translation>
    </message>
    <message>
        <source>Luminance</source>
        <translation>Helligkeit</translation>
    </message>
    <message>
        <source>Whitepoint</source>
        <translation>Weißpunkt</translation>
    </message>
    <message>
        <source>Tone curve</source>
        <translation>Tonwertkurve</translation>
    </message>
    <message>
        <source>Patches</source>
        <translation>Felder</translation>
    </message>
    <message>
        <source>Duration</source>
        <translation>Dauer</translation>
    </message>
    <message>
        <source>{minutes} min</source>
        <translation>{minutes} min</translation>
    </message>
    <message>
        <source>Verify every profile (ΔE00, approx. 1 min each)</source>
        <translation>Jedes Profil verifizieren (ΔE00, je ca. 1 min)</translation>
    </message>
    <message>
        <source>Start Batch</source>
        <translation>Batch starten</translation>
    </message>
    <message>
        <source>{count} targets · approx. {hours} h {minutes} min in total</source>
        <translation>{count} Ziele · insgesamt ca. {hours} h {minutes} min</translation>
    </message>
    <message>
        <source>{ok} of {total} targets calibrated · {display}</source>
        <translation>{ok} von {total} Zielen kalibriert · {display}</translation>
    </message>
    <message>
        <source>White</source>
        <translation>Weiß</translation>
    </message>
    <message>
        <source>DDC B/C/R/G/B</source>
        <translation>DDC H/K/R/G/B</translation>
    </message>
    <message>
        <source>Profile</source>
        <translation>Profil</translation>
    </message>
    <message>
        <source>The profiles are in the profile library; their hardware settings are stored next to them, so the inspector can switch the display to them.</source>
        <translation>Die Profile liegen in der Profilbibliothek; ihre Hardware-Einstellungen sind daneben gespeichert, sodass der Inspektor den Monitor darauf umschalten kann.</translation>
    </message>
    <message>
        <source>Open Profile Folder</source>
        <translation>Profilordner öffnen</translation>
    </message>
    <message>
        <source>Create Presets…</source>
        <translation>Presets erstellen…</translation>
    </message>
</context>
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
        <source>Place the sensor in the centre of the crosshair</source>
        <translation>Sensor mittig auf das Fadenkreuz legen</translation>
    </message>
    <message>
        <source>ColorGuard active</source>
        <translation>ColorGuard aktiv</translation>
    </message>
    <message>
        <source>Original DDC values restored.</source>
        <translation>Ursprüngliche DDC-Werte wiederhergestellt.</translation>
    </message>
    <message>
        <source>Could not restore DDC values: {exc}</source>
        <translation>DDC-Werte konnten nicht wiederhergestellt werden: {exc}</translation>
    </message>
    <message>
        <source>Compositor brightness of {connector} set to {brightness} % (= DDC).</source>
        <translation>Compositor-Helligkeit von {connector} auf {brightness} % gesetzt (= DDC).</translation>
    </message>
    <message>
        <source>Could not set the compositor brightness: {exc}</source>
        <translation>Compositor-Helligkeit konnte nicht gesetzt werden: {exc}</translation>
    </message>
    <message>
        <source>✓ Phase 1c: no clipping with the final settings (contrast {contrast}, brightness {brightness}, RGB {r}/{g}/{b}).</source>
        <translation>✓ Phase 1c: kein Clipping mit den endgültigen Werten (Kontrast {contrast}, Helligkeit {brightness}, RGB {r}/{g}/{b}).</translation>
    </message>
    <message>
        <source>⚠ Phase 1c: clipping at contrast {contrast} ({reason}); cannot lower further.</source>
        <translation>⚠ Phase 1c: Clipping bei Kontrast {contrast} ({reason}); weiter absenken ist nicht möglich.</translation>
    </message>
    <message>
        <source>Phase 1c: clipping at contrast {contrast} ({reason}) – lowering to {lowered} and re-regulating whitepoint/luminance.</source>
        <translation>Phase 1c: Clipping bei Kontrast {contrast} ({reason}) – senke auf {lowered} und regle Weißpunkt/Helligkeit nach.</translation>
    </message>
    <message>
        <source>⚠ Phase 1c: still clipping after {n} corrections.</source>
        <translation>⚠ Phase 1c: nach {n} Korrekturen weiterhin Clipping.</translation>
    </message>
    <message>
        <source>Re-measured patches are plausible now.</source>
        <translation>Nachgemessene Felder sind jetzt plausibel.</translation>
    </message>
    <message>
        <source>Plausibility check: {count} of {total} patches deviate (ΔE00 &gt; {threshold}).</source>
        <translation>Plausibilitätsprüfung: {count} von {total} Feldern weichen ab (ΔE00 &gt; {threshold}).</translation>
    </message>
    <message>
        <source>Outliers kept; computing the profile anyway.</source>
        <translation>Ausreißer übernommen; Profil wird trotzdem berechnet.</translation>
    </message>
    <message>
        <source>Patches still deviate after re-measuring; continuing.</source>
        <translation>Felder weichen nach dem Nachmessen weiterhin ab; es geht trotzdem weiter.</translation>
    </message>
    <message>
        <source>Re-measuring patch {id} ({n}/{total})</source>
        <translation>Feld {id} wird nachgemessen ({n}/{total})</translation>
    </message>
    <message>
        <source>Phase 2 · Patch {index}/{total} ({percent} %)</source>
        <translation>Phase 2 · Feld {index}/{total} ({percent} %)</translation>
    </message>
    <message>
        <source>Diagnostics · {connector}</source>
        <translation>Diagnose · {connector}</translation>
    </message>
    <message>
        <source>Calibrate the spectrometer: put it on its calibration tile (or cap it), then press Space</source>
        <translation>Spektralfotometer kalibrieren: auf die Kalibrierkachel setzen (bzw. Deckel aufsetzen), dann Leertaste drücken</translation>
    </message>
    <message>
        <source>Place the spectrometer in the centre of the crosshair, then press Space</source>
        <translation>Spektralfotometer mittig auf das Fadenkreuz setzen, dann Leertaste drücken</translation>
    </message>
    <message>
        <source>Spectral correction · Patch {index}/{total}</source>
        <translation>Spektralkorrektur · Feld {index}/{total}</translation>
    </message>
    <message>
        <source>Verification · {name} ({index}/{total})</source>
        <translation>Verifikation · {name} ({index}/{total})</translation>
    </message>
    <message>
        <source>Verification: mean ΔE00 {mean}, max ΔE00 {max} ({name}).</source>
        <translation>Verifikation: ΔE00 Ø {mean}, max {max} ({name}).</translation>
    </message>
    <message>
        <source>Batch {index}/{total}: {label}</source>
        <translation>Batch {index}/{total}: {label}</translation>
    </message>
    <message>
        <source>✓ Batch {index}/{total}: {label} → {file}</source>
        <translation>✓ Batch {index}/{total}: {label} → {file}</translation>
    </message>
    <message>
        <source>⚠ Batch {index}/{total}: {label} failed: {error}</source>
        <translation>⚠ Batch {index}/{total}: {label} fehlgeschlagen: {error}</translation>
    </message>
</context>
<context>
    <name>Corrections</name>
    <message>
        <source>Standard white LED (W-LED)</source>
        <translation>Standard-Weiß-LED (W-LED)</translation>
    </message>
    <message>
        <source>Wide-gamut LED / PFS (KSF) phosphor</source>
        <translation>Wide-Gamut-LED / PFS-(KSF-)Phosphor</translation>
    </message>
    <message>
        <source>GB-r-LED</source>
        <translation>GB-r-LED</translation>
    </message>
    <message>
        <source>RGB LED</source>
        <translation>RGB-LED</translation>
    </message>
    <message>
        <source>Quantum dot (QD)</source>
        <translation>Quantum Dot (QD)</translation>
    </message>
    <message>
        <source>OLED</source>
        <translation>OLED</translation>
    </message>
    <message>
        <source>CCFL</source>
        <translation>CCFL</translation>
    </message>
    <message>
        <source>Spectral correction</source>
        <translation>Spektralkorrektur</translation>
    </message>
    <message>
        <source>Import…</source>
        <translation>Importieren…</translation>
    </message>
    <message>
        <source>No correction files installed. Import a .ccss/.ccmx file, or install the manufacturer&apos;s corrections with ArgyllCMS “oeminst”.</source>
        <translation>Keine Korrekturdateien installiert. Eine .ccss/.ccmx-Datei importieren oder die Korrekturen des Herstellers mit ArgyllCMS „oeminst“ installieren.</translation>
    </message>
    <message>
        <source>Colorimeter correction for the backlight of this display (.ccss for a technology, .ccmx for a display/instrument pair). Without a file the instrument uses its default calibration.</source>
        <translation>Colorimeter-Korrektur für die Hintergrundbeleuchtung dieses Monitors (.ccss für eine Technologie, .ccmx für ein Paar aus Monitor und Messgerät). Ohne Datei nutzt das Messgerät seine Standardkalibrierung.</translation>
    </message>
    <message>
        <source>None (instrument default)</source>
        <translation>Keine (Gerätestandard)</translation>
    </message>
    <message>
        <source>Import Correction</source>
        <translation>Korrektur importieren</translation>
    </message>
    <message>
        <source>Colorimeter corrections (*.ccss *.ccmx)</source>
        <translation>Colorimeter-Korrekturen (*.ccss *.ccmx)</translation>
    </message>
</context>
<context>
    <name>Errors</name>
    <message>
        <source>{name} is not a .ccss/.ccmx file (starts with &apos;{start}&apos;).</source>
        <translation>{name} ist keine .ccss/.ccmx-Datei (beginnt mit „{start}“).</translation>
    </message>
    <message>
        <source>{path} is not an ICC profile.</source>
        <translation>{path} ist kein ICC-Profil.</translation>
    </message>
    <message>
        <source>ArgyllCMS tool &apos;{tool}&apos; was not found in PATH.</source>
        <translation>Das ArgyllCMS-Programm „{tool}“ wurde nicht im PATH gefunden.</translation>
    </message>
    <message>
        <source>{tool} failed (exit code {code}):
{output}</source>
        <translation>{tool} ist fehlgeschlagen (Exit-Code {code}):
{output}</translation>
    </message>
    <message>
        <source>The ICC profile was not created at {path}.</source>
        <translation>Das ICC-Profil wurde nicht unter {path} erzeugt.</translation>
    </message>
    <message>
        <source>Could not read a measurement from spotread (is the sensor connected?). Output:
{output}</source>
        <translation>spotread hat keinen Messwert geliefert (ist das Messgerät angeschlossen?). Ausgabe:
{output}</translation>
    </message>
    <message>
        <source>kscreen-doctor was not found in PATH (package: kscreen).</source>
        <translation>kscreen-doctor wurde nicht im PATH gefunden (Paket: kscreen).</translation>
    </message>
    <message>
        <source>No access to the Wayland socket ($XDG_RUNTIME_DIR/$WAYLAND_DISPLAY). kscreen-doctor must be executed inside an active Wayland session.</source>
        <translation>Kein Zugriff auf den Wayland-Socket ($XDG_RUNTIME_DIR/$WAYLAND_DISPLAY). kscreen-doctor muss in einer aktiven Wayland-Sitzung laufen.</translation>
    </message>
    <message>
        <source>GNOME/Mutter is not supported yet; colour profiles can only be switched under KDE Plasma.</source>
        <translation>GNOME/Mutter wird noch nicht unterstützt; Farbprofile lassen sich nur unter KDE Plasma umschalten.</translation>
    </message>
    <message>
        <source>Preset &apos;{name}&apos; was not found in {path}.</source>
        <translation>Preset „{name}“ wurde in {path} nicht gefunden.</translation>
    </message>
    <message>
        <source>Preset &apos;{name}&apos; was not found.</source>
        <translation>Preset „{name}“ wurde nicht gefunden.</translation>
    </message>
    <message>
        <source>Preset name &apos;{name}&apos; is empty or already used.</source>
        <translation>Der Preset-Name „{name}“ ist leer oder schon vergeben.</translation>
    </message>
</context>
<context>
    <name>ExpertPage</name>
    <message>
        <source>Parameters</source>
        <translation>Parameter</translation>
    </message>
    <message>
        <source>Calibration</source>
        <translation>Kalibrierung</translation>
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
</context>
<context>
    <name>Inspector</name>
    <message>
        <source>Key {key}</source>
        <translation>Taste {key}</translation>
    </message>
    <message>
        <source>Profile Inspector – KelvinCal</source>
        <translation>Profil-Inspektor – KelvinCal</translation>
    </message>
    <message>
        <source>Profile</source>
        <translation>Profil</translation>
    </message>
    <message>
        <source>Verification</source>
        <translation>Verifikation</translation>
    </message>
    <message>
        <source>White Y max</source>
        <translation>Weiß Y max</translation>
    </message>
    <message>
        <source>Black Y min</source>
        <translation>Schwarz Y min</translation>
    </message>
    <message>
        <source>Contrast</source>
        <translation>Kontrast</translation>
    </message>
    <message>
        <source>Whitepoint (profile)</source>
        <translation>Weißpunkt (laut Profil)</translation>
    </message>
    <message>
        <source>Effective gamma</source>
        <translation>Gamma effektiv</translation>
    </message>
    <message>
        <source>Coverage (2D, u′v′)</source>
        <translation>Abdeckung (2D, u′v′)</translation>
    </message>
    <message>
        <source>Tone Curves</source>
        <translation>Tonwertkurven</translation>
    </message>
    <message>
        <source>Gamma γ(x)</source>
        <translation>Gamma γ(x)</translation>
    </message>
    <message>
        <source>Kink Magnifier Δ%</source>
        <translation>Knick-Lupe Δ%</translation>
    </message>
    <message>
        <source>Gamut</source>
        <translation>Farbraum</translation>
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
        <source>Measured points</source>
        <translation>Messpunkte</translation>
    </message>
    <message>
        <source>Reference</source>
        <translation>Referenz</translation>
    </message>
    <message>
        <source>Display</source>
        <translation>Monitor</translation>
    </message>
    <message>
        <source>Live preview on {connector}</source>
        <translation>Live-Vorschau auf {connector}</translation>
    </message>
    <message>
        <source>{source} · no ICC</source>
        <translation>{source} · ohne ICC</translation>
    </message>
    <message>
        <source>New profile</source>
        <translation>Neues Profil</translation>
    </message>
    <message>
        <source>Previous profile</source>
        <translation>Vorheriges Profil</translation>
    </message>
    <message>
        <source>This profile</source>
        <translation>Dieses Profil</translation>
    </message>
    <message>
        <source>Current profile</source>
        <translation>Aktuelles Profil</translation>
    </message>
    <message>
        <source>Uncalibrated</source>
        <translation>Unkalibriert</translation>
    </message>
    <message>
        <source>sRGB · no ICC</source>
        <translation>sRGB · ohne ICC</translation>
    </message>
    <message>
        <source>Visual A/B comparison: switches the profile on the real desktop of {connector}, e.g. to judge photos or gradients. The graphs always show the inspected profile.</source>
        <translation>Sichtvergleich A/B: schaltet das Profil auf dem echten Desktop von {connector} um, z. B. um Fotos oder Verläufe zu beurteilen. Die Graphen zeigen immer das geprüfte Profil.</translation>
    </message>
    <message>
        <source>1 and 3 use the display settings (DDC) the profile was measured with, 2 the previous ones.</source>
        <translation>1 und 3 nutzen die Monitoreinstellungen (DDC), mit denen das Profil gemessen wurde, 2 die vorherigen.</translation>
    </message>
    <message>
        <source>Save</source>
        <translation>Speichern</translation>
    </message>
    <message>
        <source>Activate in KWin for {connector}</source>
        <translation>In KWin für {connector} aktivieren</translation>
    </message>
    <message>
        <source>Also update in preset</source>
        <translation>Zusätzlich im Preset aktualisieren</translation>
    </message>
    <message>
        <source>Only {connector} is overwritten: its current DDC values and this ICC profile. Other displays in the preset stay unchanged.</source>
        <translation>Nur {connector} wird überschrieben: aktuelle DDC-Werte und dieses ICC-Profil. Die anderen Monitore im Preset bleiben unverändert.</translation>
    </message>
    <message>
        <source>Save As…</source>
        <translation>Speichern unter…</translation>
    </message>
    <message>
        <source>Discard &amp;&amp; Restore Previous Profile</source>
        <translation>Verwerfen &amp;&amp; vorheriges Profil wiederherstellen</translation>
    </message>
    <message>
        <source>Open Another Profile…</source>
        <translation>Anderes Profil öffnen…</translation>
    </message>
    <message>
        <source>Close</source>
        <translation>Schließen</translation>
    </message>
    <message>
        <source>Verification (ΔE2000)</source>
        <translation>Verifikation (ΔE2000)</translation>
    </message>
    <message>
        <source>Measure Verification</source>
        <translation>Verifikation messen</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>Abbrechen</translation>
    </message>
    <message>
        <source>Save Report…</source>
        <translation>Bericht speichern…</translation>
    </message>
    <message>
        <source>Mean ΔE00</source>
        <translation>ΔE00 Ø</translation>
    </message>
    <message>
        <source>Max ΔE00</source>
        <translation>ΔE00 max</translation>
    </message>
    <message>
        <source>Gray balance</source>
        <translation>Graubalance</translation>
    </message>
    <message>
        <source>Whitepoint (measured)</source>
        <translation>Weißpunkt (gemessen)</translation>
    </message>
    <message>
        <source>White / black</source>
        <translation>Weiß / Schwarz</translation>
    </message>
    <message>
        <source>Patch</source>
        <translation>Feld</translation>
    </message>
    <message>
        <source>Target / measured</source>
        <translation>Soll / Ist</translation>
    </message>
    <message>
        <source>Gray balance a*b*</source>
        <translation>Graubalance a*b*</translation>
    </message>
    <message>
        <source>Deviation of the gray patches from neutral; circles at 1.0 and 2.0.</source>
        <translation>Abweichung der Graufelder von neutral; Kreise bei 1,0 und 2,0.</translation>
    </message>
    <message>
        <source>Measuring needs the display this profile belongs to: open the inspector from the calibration or via the display (↗).</source>
        <translation>Zum Messen braucht der Inspektor den zugehörigen Monitor: nach der Kalibrierung oder über den Monitor (↗) öffnen.</translation>
    </message>
    <message>
        <source>Measures {count} sRGB test patches (ColorChecker, gray ramp, primaries) with the currently active profile – {profile}. Use the live preview to verify another state.</source>
        <translation>Misst {count} sRGB-Testfelder (ColorChecker, Graurampe, Grundfarben) mit dem gerade aktiven Profil – {profile}. Über die Live-Vorschau lässt sich auch ein anderer Zustand messen.</translation>
    </message>
    <message>
        <source>Measure Again</source>
        <translation>Erneut messen</translation>
    </message>
    <message>
        <source>Measured state: {state} · {time}</source>
        <translation>Gemessener Zustand: {state} · {time}</translation>
    </message>
    <message>
        <source>recommended ≤ {r}, nominal ≤ {n}</source>
        <translation>empfohlen ≤ {r}, nominal ≤ {n}</translation>
    </message>
    <message>
        <source>max Δa*b* of the grays</source>
        <translation>max. Δa*b* der Graufelder</translation>
    </message>
    <message>
        <source>Δu′v′ {duv} to target</source>
        <translation>Δu′v′ {duv} zum Ziel</translation>
    </message>
    <message>
        <source>Save Verification Report</source>
        <translation>Verifikationsbericht speichern</translation>
    </message>
    <message>
        <source>HTML files (*.html)</source>
        <translation>HTML-Dateien (*.html)</translation>
    </message>
    <message>
        <source>New profile for {connector}</source>
        <translation>Neues Profil für {connector}</translation>
    </message>
    <message>
        <source>{count} patches</source>
        <translation>{count} Felder</translation>
    </message>
    <message>
        <source>Target {value}</source>
        <translation>Ziel {value}</translation>
    </message>
    <message>
        <source>measured</source>
        <translation>gemessen</translation>
    </message>
    <message>
        <source>static</source>
        <translation>statisch</translation>
    </message>
    <message>
        <source>Δu′v′ {value} to {ref}</source>
        <translation>Δu′v′ {value} zu {ref}</translation>
    </message>
    <message>
        <source>&lt;b&gt;Kink check: no findings.&lt;/b&gt; Curves are smooth and monotonic, gray balance is continuous.</source>
        <translation>&lt;b&gt;Knick-Check: keine Auffälligkeiten.&lt;/b&gt; Kurven stetig und monoton, Graubalance stetig.</translation>
    </message>
    <message>
        <source>(+{count} more)</source>
        <translation>(+{count} weitere)</translation>
    </message>
    <message>
        <source>&lt;b&gt;Kink check: {count} finding(s).&lt;/b&gt; {details}</source>
        <translation>&lt;b&gt;Knick-Check: {count} Auffälligkeit(en).&lt;/b&gt; {details}</translation>
    </message>
    <message>
        <source>Target line</source>
        <translation>Ziellinie</translation>
    </message>
    <message>
        <source>Move the mouse over the graph for live values</source>
        <translation>Maus über den Graphen bewegen für Live-Werte</translation>
    </message>
    <message>
        <source>Source rTRC/gTRC/bTRC</source>
        <translation>Quelle rTRC/gTRC/bTRC</translation>
    </message>
    <message>
        <source>Preview Switch Error</source>
        <translation>Fehler beim Umschalten der Vorschau</translation>
    </message>
    <message>
        <source>Setting display hardware (DDC/CI)…</source>
        <translation>Monitor-Hardware wird gesetzt (DDC/CI)…</translation>
    </message>
    <message>
        <source>Hardware now: brightness {b} · contrast {c} · RGB {r}/{g}/{bl}</source>
        <translation>Hardware jetzt: Helligkeit {b} · Kontrast {c} · RGB {r}/{g}/{bl}</translation>
    </message>
    <message>
        <source>uncalibrated (sRGB, no ICC)</source>
        <translation>unkalibriert (sRGB, ohne ICC)</translation>
    </message>
    <message>
        <source>Save &amp;&amp; Activate</source>
        <translation>Speichern &amp;&amp; Aktivieren</translation>
    </message>
    <message>
        <source>Save ICC Profile As</source>
        <translation>ICC-Profil speichern unter</translation>
    </message>
    <message>
        <source>ICC Profiles (*.icc *.icm)</source>
        <translation>ICC-Profile (*.icc *.icm)</translation>
    </message>
    <message>
        <source>Open ICC Profile</source>
        <translation>ICC-Profil öffnen</translation>
    </message>
    <message>
        <source>Profile Load Error</source>
        <translation>Fehler beim Laden des Profils</translation>
    </message>
    <message>
        <source>Signal %</source>
        <translation>Signal %</translation>
    </message>
    <message>
        <source>The profile contains no TRC curves.</source>
        <translation>Das Profil enthält keine TRC-Kurven.</translation>
    </message>
    <message>
        <source>Signal {value} %</source>
        <translation>Signal {value} %</translation>
    </message>
    <message>
        <source>Ideal {value}</source>
        <translation>Ideal {value}</translation>
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
        <source>Refresh Displays &amp;&amp; Sensor</source>
        <translation>Monitore &amp;&amp; Sensor aktualisieren</translation>
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
        <source>Batch Calibration…</source>
        <translation>Batch-Kalibrierung…</translation>
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
        <source>ArgyllCMS was not found. Install it (package &quot;argyllcms&quot;) to measure.</source>
        <translation>ArgyllCMS wurde nicht gefunden. Zum Messen bitte installieren (Paket „argyllcms“).</translation>
    </message>
    <message>
        <source>No measuring instrument found. Connect the sensor and press F5.</source>
        <translation>Kein Messgerät gefunden. Sensor anschließen und F5 drücken.</translation>
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
        <source>Presets from Calibrations</source>
        <translation>Presets aus Kalibrierungen</translation>
    </message>
    <message>
        <source>No calibrated profiles with stored hardware settings were found for the connected displays. Profiles get them when they are saved after a calibration with a target (simple mode, batch).</source>
        <translation>Für die angeschlossenen Monitore wurden keine kalibrierten Profile mit gespeicherten Hardware-Einstellungen gefunden. Profile erhalten sie, wenn sie nach einer Kalibrierung mit Zielvorgabe gespeichert werden (einfacher Modus, Batch).</translation>
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
        <source>Screen locking, dimming and suspend are inhibited during the run.</source>
        <translation>Bildschirmsperre, Abdunkeln und Ruhezustand sind während des Laufs unterdrückt.</translation>
    </message>
    <message>
        <source>Spectral correction: {name}</source>
        <translation>Spektralkorrektur: {name}</translation>
    </message>
    <message>
        <source>none (instrument default)</source>
        <translation>keine (Gerätestandard)</translation>
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
        <source>Batch Calibration</source>
        <translation>Batch-Kalibrierung</translation>
    </message>
    <message>
        <source>This display has no DDC/CI. Contrast, whitepoint and luminance cannot be set in hardware.</source>
        <translation>Dieser Monitor hat kein DDC/CI. Kontrast, Weißpunkt und Helligkeit lassen sich nicht in der Hardware einstellen.</translation>
    </message>
    <message>
        <source>Batch · {count} targets</source>
        <translation>Batch · {count} Ziele</translation>
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
        <source>Test patch window</source>
        <translation>Patch-Fenster testen</translation>
    </message>
    <message>
        <source>Space / Esc</source>
        <translation>Leertaste / Esc</translation>
    </message>
    <message>
        <source>Close</source>
        <translation>Schließen</translation>
    </message>
    <message>
        <source>✓ ICC profile saved: {saved_profile_path}</source>
        <translation>✓ ICC-Profil gespeichert: {saved_profile_path}</translation>
    </message>
    <message>
        <source>Preview DDC on {connector}: set {set} → read back {read}</source>
        <translation>Vorschau-DDC an {connector}: gesetzt {set} → gelesen {read}</translation>
    </message>
    <message>
        <source>The display did not take over all DDC values (set {set}, read {read}).</source>
        <translation>Der Monitor hat nicht alle DDC-Werte übernommen (gesetzt {set}, gelesen {read}).</translation>
    </message>
    <message>
        <source>Preset &apos;{preset}&apos; updated for {connector}.</source>
        <translation>Preset „{preset}“ für {connector} aktualisiert.</translation>
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
        <source>DDC/CI</source>
        <translation>DDC/CI</translation>
    </message>
    <message>
        <source>no values</source>
        <translation>keine Werte</translation>
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
        <source>RGB gain</source>
        <translation>RGB-Gain</translation>
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
        <source>Show or hide DDC values and colour state</source>
        <translation>DDC-Werte und Farbzustand ein- oder ausblenden</translation>
    </message>
    <message>
        <source>DDC/CI live</source>
        <translation>DDC/CI live</translation>
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
        <source>No DDC/CI: contrast, whitepoint and luminance cannot be set in hardware.</source>
        <translation>Kein DDC/CI: Kontrast, Weißpunkt und Helligkeit lassen sich nicht in der Hardware einstellen.</translation>
    </message>
    <message>
        <source>Colour source</source>
        <translation>Farbquelle</translation>
    </message>
    <message>
        <source>Mode</source>
        <translation>Modus</translation>
    </message>
    <message>
        <source>on</source>
        <translation>an</translation>
    </message>
    <message>
        <source>off</source>
        <translation>aus</translation>
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
        <source>Spectral correction: {name} (can be changed in expert mode)</source>
        <translation>Spektralkorrektur: {name} (im Expertenmodus änderbar)</translation>
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
        <source>Several Targets…</source>
        <translation>Mehrere Ziele…</translation>
    </message>
    <message>
        <source>Batch: calibrate several targets one after another with the sensor placed once</source>
        <translation>Batch: mehrere Ziele nacheinander kalibrieren, Messgerät nur einmal ansetzen</translation>
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
    <name>OutlierDialog</name>
    <message>
        <source>Patch {id}</source>
        <translation>Feld {id}</translation>
    </message>
    <message>
        <source>measurement order</source>
        <translation>Messreihenfolge</translation>
    </message>
    <message>
        <source>Check Measurements – KelvinCal</source>
        <translation>Messdaten prüfen – KelvinCal</translation>
    </message>
    <message>
        <source>{count} measurement(s) deviate strongly</source>
        <translation>{count} Messwert(e) weichen stark ab</translation>
    </message>
    <message>
        <source>Found after the patch measurement, before the profile is computed. Possible causes: a notification briefly covered the patch window, or the sensor slipped.</source>
        <translation>Erkannt nach der Patch-Messung, bevor das Profil berechnet wird. Mögliche Ursachen: eine Benachrichtigung lag kurz über dem Messfenster oder der Sensor ist verrutscht.</translation>
    </message>
    <message>
        <source>These patches still deviate after re-measuring. If they stay off, the display may really behave like this there – then compute the profile anyway.</source>
        <translation>Diese Felder weichen auch nach dem Nachmessen ab. Bleibt das so, verhält sich der Monitor dort vermutlich wirklich so – dann das Profil trotzdem berechnen.</translation>
    </message>
    <message>
        <source>ΔE00 to the expected course, all {n} patches</source>
        <translation>ΔE00 zum erwarteten Verlauf, alle {n} Felder</translation>
    </message>
    <message>
        <source>Patch</source>
        <translation>Feld</translation>
    </message>
    <message>
        <source>Target</source>
        <translation>Soll</translation>
    </message>
    <message>
        <source>Patches {a} and {b} were measured directly one after the other – typical of a notification.</source>
        <translation>Feld {a} und {b} wurden direkt nacheinander gemessen – typisch für eine Benachrichtigung.</translation>
    </message>
    <message>
        <source>Cancel Calibration</source>
        <translation>Kalibrierung abbrechen</translation>
    </message>
    <message>
        <source>Compute Profile Anyway</source>
        <translation>Trotzdem Profil berechnen</translation>
    </message>
    <message>
        <source>Re-measure Patches</source>
        <translation>Messung wiederholen</translation>
    </message>
    <message>
        <source>Shows these patches again on the display and measures them with the sensor in place.</source>
        <translation>Zeigt diese Felder erneut auf dem Monitor und misst sie mit dem aufgelegten Sensor nach.</translation>
    </message>
</context>
<context>
    <name>PatchWindow</name>
    <message>
        <source>No screen found for connector {connector} (available: {available}).</source>
        <translation>Kein Bildschirm für Anschluss {connector} gefunden (verfügbar: {available}).</translation>
    </message>
    <message>
        <source>Space</source>
        <translation>Leertaste</translation>
    </message>
    <message>
        <source>Start measurement</source>
        <translation>Messung starten</translation>
    </message>
    <message>
        <source>Esc</source>
        <translation>Esc</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>Abbrechen</translation>
    </message>
    <message>
        <source>Esc Cancel</source>
        <translation>Esc Abbrechen</translation>
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
    <message>
        <source>Measuring the spectra of white, red, green and blue...</source>
        <translation>Spektren von Weiß, Rot, Grün und Blau werden gemessen …</translation>
    </message>
</context>
<context>
    <name>PresetsFromProfiles</name>
    <message>
        <source>Presets from Calibrations</source>
        <translation>Presets aus Kalibrierungen</translation>
    </message>
    <message>
        <source>Create presets from calibrated profiles</source>
        <translation>Presets aus kalibrierten Profilen erstellen</translation>
    </message>
    <message>
        <source>One preset per target with the newest profile of every display and the hardware settings it was measured with. Displays without a profile for a target are not changed by that preset; an existing preset of the same name keeps its entries for them.</source>
        <translation>Ein Preset pro Ziel mit dem neuesten Profil jedes Monitors und den Hardware-Einstellungen, mit denen es gemessen wurde. Monitore ohne Profil für ein Ziel werden von diesem Preset nicht verändert; ein vorhandenes Preset gleichen Namens behält seine Einträge für sie.</translation>
    </message>
    <message>
        <source>Preset</source>
        <translation>Preset</translation>
    </message>
    <message>
        <source>Action</source>
        <translation>Aktion</translation>
    </message>
    <message>
        <source>update</source>
        <translation>aktualisieren</translation>
    </message>
    <message>
        <source>new</source>
        <translation>neu</translation>
    </message>
    <message>
        <source>Create / Update</source>
        <translation>Erstellen / Aktualisieren</translation>
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
        <source>Create from Calibrations…</source>
        <translation>Aus Kalibrierungen erstellen…</translation>
    </message>
    <message>
        <source>One preset per target from the newest calibrated profile of every display</source>
        <translation>Ein Preset pro Ziel aus dem neuesten kalibrierten Profil jedes Monitors</translation>
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
        <source>Verification</source>
        <translation>Verifikation</translation>
    </message>
    <message>
        <source>Phase 2 · Patch measurement</source>
        <translation>Phase 2 · Patch-Messung</translation>
    </message>
    <message>
        <source>Patch {index} / {total}
Target RGB {r} {g} {b}</source>
        <translation>Feld {index} / {total}
Soll-RGB {r} {g} {b}</translation>
    </message>
    <message>
        <source>Batch {index} / {total} · {label}</source>
        <translation>Batch {index} / {total} · {label}</translation>
    </message>
    <message>
        <source>from target 1</source>
        <translation>aus Ziel 1</translation>
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
<context>
    <name>Verification</name>
    <message>
        <source>Dark skin</source>
        <translation>Dunkle Haut</translation>
    </message>
    <message>
        <source>Light skin</source>
        <translation>Helle Haut</translation>
    </message>
    <message>
        <source>Blue sky</source>
        <translation>Blauer Himmel</translation>
    </message>
    <message>
        <source>Foliage</source>
        <translation>Blattgrün</translation>
    </message>
    <message>
        <source>Blue flower</source>
        <translation>Blaue Blüte</translation>
    </message>
    <message>
        <source>Bluish green</source>
        <translation>Blaugrün</translation>
    </message>
    <message>
        <source>Orange</source>
        <translation>Orange</translation>
    </message>
    <message>
        <source>Purplish blue</source>
        <translation>Violettblau</translation>
    </message>
    <message>
        <source>Moderate red</source>
        <translation>Mittelrot</translation>
    </message>
    <message>
        <source>Purple</source>
        <translation>Purpur</translation>
    </message>
    <message>
        <source>Yellow green</source>
        <translation>Gelbgrün</translation>
    </message>
    <message>
        <source>Orange yellow</source>
        <translation>Orangegelb</translation>
    </message>
    <message>
        <source>Blue</source>
        <translation>Blau</translation>
    </message>
    <message>
        <source>Green</source>
        <translation>Grün</translation>
    </message>
    <message>
        <source>Red</source>
        <translation>Rot</translation>
    </message>
    <message>
        <source>Yellow</source>
        <translation>Gelb</translation>
    </message>
    <message>
        <source>Magenta</source>
        <translation>Magenta</translation>
    </message>
    <message>
        <source>Cyan</source>
        <translation>Cyan</translation>
    </message>
    <message>
        <source>White 9.5</source>
        <translation>Weiß 9,5</translation>
    </message>
    <message>
        <source>Neutral 8</source>
        <translation>Neutral 8</translation>
    </message>
    <message>
        <source>Neutral 6.5</source>
        <translation>Neutral 6,5</translation>
    </message>
    <message>
        <source>Neutral 5</source>
        <translation>Neutral 5</translation>
    </message>
    <message>
        <source>Neutral 3.5</source>
        <translation>Neutral 3,5</translation>
    </message>
    <message>
        <source>Black 2</source>
        <translation>Schwarz 2</translation>
    </message>
    <message>
        <source>Red 100 %</source>
        <translation>Rot 100 %</translation>
    </message>
    <message>
        <source>Green 100 %</source>
        <translation>Grün 100 %</translation>
    </message>
    <message>
        <source>Blue 100 %</source>
        <translation>Blau 100 %</translation>
    </message>
    <message>
        <source>Cyan 100 %</source>
        <translation>Cyan 100 %</translation>
    </message>
    <message>
        <source>Magenta 100 %</source>
        <translation>Magenta 100 %</translation>
    </message>
    <message>
        <source>Yellow 100 %</source>
        <translation>Gelb 100 %</translation>
    </message>
    <message>
        <source>Gray {level} %</source>
        <translation>Grau {level} %</translation>
    </message>
    <message>
        <source>KelvinCal verification report</source>
        <translation>KelvinCal-Verifikationsbericht</translation>
    </message>
    <message>
        <source>Display</source>
        <translation>Monitor</translation>
    </message>
    <message>
        <source>Profile</source>
        <translation>Profil</translation>
    </message>
    <message>
        <source>Date</source>
        <translation>Datum</translation>
    </message>
    <message>
        <source>Mean ΔE00</source>
        <translation>ΔE00 Ø</translation>
    </message>
    <message>
        <source>Max ΔE00</source>
        <translation>ΔE00 max</translation>
    </message>
    <message>
        <source>Gray balance (max Δa*b*)</source>
        <translation>Graubalance (max. Δa*b*)</translation>
    </message>
    <message>
        <source>Whitepoint Δu′v′</source>
        <translation>Weißpunkt Δu′v′</translation>
    </message>
    <message>
        <source>White / black</source>
        <translation>Weiß / Schwarz</translation>
    </message>
    <message>
        <source>Patch</source>
        <translation>Feld</translation>
    </message>
    <message>
        <source>sRGB (8 bit)</source>
        <translation>sRGB (8 Bit)</translation>
    </message>
    <message>
        <source>Lab expected</source>
        <translation>Lab Soll</translation>
    </message>
    <message>
        <source>Lab measured</source>
        <translation>Lab Ist</translation>
    </message>
    <message>
        <source>Patches shown as sRGB with the profile active in the compositor; ΔE00 relative to the measured white. Green: recommended, orange: nominal tolerance.</source>
        <translation>Felder als sRGB angezeigt, Profil im Compositor aktiv; ΔE00 relativ zum gemessenen Weiß. Grün: empfohlen, Orange: nominale Toleranz.</translation>
    </message>
    <message>
        <source>White</source>
        <translation>Weiß</translation>
    </message>
    <message>
        <source>Black</source>
        <translation>Schwarz</translation>
    </message>
</context>
</TS>
