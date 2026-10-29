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
        <source>Phase 1b: D65 whitepoint &amp; luminance regulation ({target_luminance:.0f} cd/m²)...</source>
        <translation>Phase 1b: D65-Weißpunkt- &amp; Helligkeitsregelung ({target_luminance:.0f} cd/m²)...</translation>
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
    <name>MainWindow</name>
    <message>
        <source>KelvinCal – Wayland Color Management &amp; Hardware Calibration</source>
        <translation>KelvinCal – Wayland Farbmanagement &amp; Hardware-Kalibrierung</translation>
    </message>
    <message>
        <source>Inspect ICC Profile (Curves)...</source>
        <translation>ICC-Profil prüfen (Kurven)...</translation>
    </message>
    <message>
        <source>Refresh Displays</source>
        <translation>Monitore neu einlesen</translation>
    </message>
    <message>
        <source>Calibration &amp; Optimizer Parameters</source>
        <translation>Kalibrierungs- &amp; Optimizer-Parameter</translation>
    </message>
    <message>
        <source>Target Luminance (D65):</source>
        <translation>Ziel-Luminanz (D65):</translation>
    </message>
    <message>
        <source>Contrast Search Range (Min %):</source>
        <translation>Kontrast-Suchbereich (Min %):</translation>
    </message>
    <message>
        <source>Contrast Search Range (Max %):</source>
        <translation>Kontrast-Suchbereich (Max %):</translation>
    </message>
    <message>
        <source>Patch Count (targen):</source>
        <translation>Anzahl Messfelder (targen):</translation>
    </message>
    <message>
        <source>Test Patch Window</source>
        <translation>Patch-Fenster testen</translation>
    </message>
    <message>
        <source>Phase 1a: Contrast Optimizer (Binary Search)</source>
        <translation>Phase 1a: Kontrast-Optimizer (Binärsuche)</translation>
    </message>
    <message>
        <source>Phase 1b: D65 Whitepoint &amp; Brightness (DDC)</source>
        <translation>Phase 1b: D65 Weißpunkt &amp; Helligkeit (DDC)</translation>
    </message>
    <message>
        <source>Phase 2+3: Start ArgyllCMS Profiling</source>
        <translation>Phase 2+3: ArgyllCMS Profilierung starten</translation>
    </message>
    <message>
        <source>Run All Phases</source>
        <translation>Alle Phasen ausführen</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>Abbrechen</translation>
    </message>
    <message>
        <source>1. Hardware Optimizer &amp; Calibration</source>
        <translation>1. Hardware-Optimizer &amp; Kalibrierung</translation>
    </message>
    <message>
        <source>Save Current State as Preset...</source>
        <translation>Aktuellen Ist-Zustand als Preset speichern...</translation>
    </message>
    <message>
        <source>Activate Selected Preset</source>
        <translation>Ausgewähltes Preset aktivieren</translation>
    </message>
    <message>
        <source>2. Display Presets (Multi-Monitor)</source>
        <translation>2. Display-Presets (Multi-Monitor)</translation>
    </message>
    <message>
        <source>Measurement and diagnostic log...</source>
        <translation>Mess- und Diagnoseprotokoll...</translation>
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
        <source>Target Display:</source>
        <translation>Ziel-Monitor:</translation>
    </message>
    <message>
        <source>Model &amp; S/N</source>
        <translation>Modell &amp; S/N</translation>
    </message>
    <message>
        <source>DDC Brightness</source>
        <translation>DDC Helligkeit</translation>
    </message>
    <message>
        <source>DDC Contrast</source>
        <translation>DDC Kontrast</translation>
    </message>
    <message>
        <source>DDC RGB Gains</source>
        <translation>DDC RGB-Gains</translation>
    </message>
    <message>
        <source>Active ICC Profile</source>
        <translation>Aktives ICC-Profil (KWin)</translation>
    </message>
    <message>
        <source>Preset Name</source>
        <translation>Preset-Name</translation>
    </message>
    <message>
        <source>Configured Displays</source>
        <translation>Konfigurierte Monitore</translation>
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
        <source>● Active</source>
        <translation>● Aktiv</translation>
    </message>
    <message>
        <source>○ Ready</source>
        <translation>○ Bereit</translation>
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
        <source>Preset &apos;{name}&apos; activated.</source>
        <translation>Preset &apos;{name}&apos; aktiviert.</translation>
    </message>
    <message>
        <source>Cancelled by user.</source>
        <translation>Vom Benutzer abgebrochen.</translation>
    </message>
    <message>
        <source>Patch Window</source>
        <translation>Patch-Fenster</translation>
    </message>
    <message>
        <source>Profile Inspector Error</source>
        <translation>Fehler beim Profil-Inspektor</translation>
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
</TS>
