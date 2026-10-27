#!/usr/bin/env python3
"""Configure an isolated TagoClip V1.2 product from the prepared Mojave source."""
from pathlib import Path
import json
import re
import sys

root = Path(sys.argv[1]).resolve()

# Unique JUCE target, product name, component bundle ID and plugin code:
# this leaves an already-installed TagoClip V1.1 untouched in REAPER.
cmake_path = root / "CMakeLists.txt"
c = cmake_path.read_text(encoding="utf-8")
changes = [
    ("project(TagoClip VERSION 1.1.3)", "project(TagoClipV12 VERSION 1.2.0)", "project version"),
    ("juce_add_plugin(TagoClip\n", "juce_add_plugin(TagoClipV12\n", "plugin target"),
    ("BUNDLE_ID com.tagobeats.tagoclip\n", "BUNDLE_ID com.tagobeats.tagoclip.v12\n", "unique bundle ID"),
    ("PLUGIN_CODE TgCl\n", "PLUGIN_CODE TgVt\n", "unique plugin code"),
    ('PRODUCT_NAME "TagoClip"\n', 'PRODUCT_NAME "TagoClip V1.2"\n', "product name"),
    ("target_sources(TagoClip PRIVATE\n", "target_sources(TagoClipV12 PRIVATE\n", "source target"),
    ("juce_add_binary_data(TagoClipAssets SOURCES", "juce_add_binary_data(TagoClipV12Assets SOURCES", "binary data target"),
    ("target_compile_definitions(TagoClip PRIVATE\n", "target_compile_definitions(TagoClipV12 PRIVATE\n", "compile definitions"),
    ("target_compile_definitions(TagoClip PRIVATE JUCE_USE_WIN_WEBVIEW2", "target_compile_definitions(TagoClipV12 PRIVATE JUCE_USE_WIN_WEBVIEW2", "WebView2 definitions"),
    ("target_compile_options(TagoClip PRIVATE", "target_compile_options(TagoClipV12 PRIVATE", "MSVC compile options"),
    ("target_link_options(TagoClip_VST3", "target_link_options(TagoClipV12_VST3", "MSVC link options"),
    ("target_link_libraries(TagoClip\n", "target_link_libraries(TagoClipV12\n", "plugin link target"),
]
for old, new, label in changes:
    if old in c:
        c = c.replace(old, new, 1)
    elif new not in c:
        raise SystemExit("Could not apply V1.2 CMake change: " + label)
# Update all binary-data target references, including the optional StateProbe.
c = c.replace("juce_add_binary_data(TagoClipAssets", "juce_add_binary_data(TagoClipV12Assets")
c = c.replace("        TagoClipAssets\n", "        TagoClipV12Assets\n")
cmake_path.write_text(c, encoding="utf-8")

# Compile and validate a different bundle path. Find the executable because
# JUCE may preserve a space in the V1.2 PRODUCT_NAME inside Contents/MacOS.
build_path = root / "scripts/build_mojave.sh"
b = build_path.read_text(encoding="utf-8")
b = b.replace("# Build TagoClip 1.1.3 for Intel x86_64", "# Build TagoClip V1.2 for Intel x86_64", 1)
# Limit build concurrency on hosted Intel runners to avoid memory pressure/stalls.
b = b.replace('-j "$(sysctl -n hw.ncpu)"', '-j 4', 1)

b = b.replace("--target TagoClip_VST3 TagoClip_AU", "--target TagoClipV12_VST3 TagoClipV12_AU", 1)
b = b.replace('ART="$ROOT/build-mojave/TagoClip_artefacts/Release"', 'ART="$ROOT/build-mojave/TagoClipV12_artefacts/Release"', 1)
b = b.replace('VST3="$ART/VST3/TagoClip.vst3"', 'VST3="$ART/VST3/TagoClip V1.2.vst3"', 1)
b = b.replace('AU="$ART/AU/TagoClip.component"', 'AU="$ART/AU/TagoClip V1.2.component"', 1)
b = b.replace('BIN="$BUNDLE/Contents/MacOS/TagoClip"\n    [[ -f "$BIN" ]] || fail "Plugin executable missing: $BIN"',
              'BIN="$(find "$BUNDLE/Contents/MacOS" -maxdepth 1 -type f -print -quit)"\n    [[ -n "$BIN" && -f "$BIN" ]] || fail "Plugin executable missing in: $BUNDLE/Contents/MacOS"', 1)
if "TagoClipV12_VST3 TagoClipV12_AU" not in b or "TagoClip V1.2.vst3" not in b or "-j 4" not in b:
    raise SystemExit("Could not fully update V1.2 build paths")
build_path.write_text(b, encoding="utf-8")

# Isolate custom presets and diagnostic logs per plugin version.
editor_path = root / "plugin/PluginEditor.cpp"
e = editor_path.read_text(encoding="utf-8")
old_store = '''                         .getChildFile ("TagoBeats")
                         .getChildFile ("TagoClip");
    directory.createDirectory();
    return directory.getChildFile ("CustomPresets.json");'''
new_store = '''                         .getChildFile ("TagoBeats")
                         .getChildFile ("TagoClip")
                         .getChildFile ("V1.2");
    directory.createDirectory();
    return directory.getChildFile ("CustomPresets.json");'''
if old_store in e:
    e = e.replace(old_store, new_store, 1)
elif '.getChildFile ("V1.2");' not in e:
    raise SystemExit("Could not isolate V1.2 custom preset storage")
e = e.replace('.getChildFile ("TagoClip");\n    directory.createDirectory();\n    return directory.getChildFile ("TagoClip-WebView.log");',
              '.getChildFile ("TagoClip");\n    directory.createDirectory();\n    return directory.getChildFile ("TagoClip-V1.2-WebView.log");', 1)
e = e.replace("constexpr int    designWidth  = 620;", "constexpr int    designWidth  = 650;", 1)
e = e.replace("constexpr int    designHeight = 380;", "constexpr int    designHeight = 398;", 1)
if "designWidth  = 650" not in e or "designHeight = 398" not in e:
    raise SystemExit("Could not expand native editor canvas for the GR meter")
editor_path.write_text(e, encoding="utf-8")

# Version header, User Presets label and key routing for the save-name field.
app_path = root / "ui/src/App.tsx"
a = app_path.read_text(encoding="utf-8")
a = a.replace("Stereo&nbsp;·&nbsp;V1.1", "Stereo&nbsp;·&nbsp;V1.2", 1)
a = a.replace("SAVED ON THIS COMPUTER", "USER PRESETS", 1)
button_match = re.search(r'<button\b(?=[^>]*className="preset-save-action")[^>]*>[\s\S]*?</button>', a)
if not button_match:
    raise SystemExit("Could not find the V1.2 save-preset button")
save_button = button_match.group(0)
save_button = re.sub(r'\s+title="[^"]*"', "", save_button)
if 'aria-label="Save current settings as a named preset"' not in save_button:
    save_button = save_button.replace(
        'className="preset-save-action"',
        'className="preset-save-action" aria-label="Save current settings as a named preset"',
        1
    )
a = a[:button_match.start()] + save_button + a[button_match.end():]
# Stop bubbling key events from the preset-name input so REAPER's spacebar
# transport shortcut cannot consume a typed space. Do not modify the form tag:
# JSX arrow attributes contain "=>" and are not safely parsed by a simple regex.
input_change = 'onChange={(event) => setSaveName(event.target.value)}'
if input_change not in a:
    raise SystemExit("Could not find the preset-name input change handler")
if 'onKeyDown={(event) => event.stopPropagation()}' not in a[a.find('aria-label="Custom preset name"'):a.find('aria-label="Custom preset name"') + 800]:
    a = a.replace(
        input_change,
        'onKeyDown={(event) => event.stopPropagation()} onKeyUp={(event) => event.stopPropagation()} ' + input_change,
        1
    )
app_path.write_text(a, encoding="utf-8")

# Browser preview storage is version specific; real plugin storage is file-backed.
bridge_path = root / "ui/src/bridge.ts"
br = bridge_path.read_text(encoding="utf-8")
br = br.replace('const CUSTOM_PRESET_STORAGE_KEY = "tagoclip-v1-custom-presets";',
                'const CUSTOM_PRESET_STORAGE_KEY = "tagoclip-v1-2-custom-presets";', 1)
bridge_path.write_text(br, encoding="utf-8")

# Add a GR bar fed by the same reported processor dB metric as GrReadout.tsx.
meters_path = root / "ui/src/Meters.tsx"
m = meters_path.read_text(encoding="utf-8")
m = m.replace('''  const outBar = useRef<HTMLDivElement>(null);
  const outPeak = useRef<HTMLDivElement>(null);''', '''  const outBar = useRef<HTMLDivElement>(null);
  const outPeak = useRef<HTMLDivElement>(null);
  const grBar = useRef<HTMLDivElement>(null);
  const grValue = useRef<HTMLDivElement>(null);''', 1)
m = m.replace('const levels = useRef({ in: 0, out: 0 });', 'const levels = useRef({ in: 0, out: 0, gr: 0 });', 1)
m = m.replace('''    let shownIn = 0;
    let shownOut = 0;''', '''    let shownIn = 0;
    let shownOut = 0;
    let shownGrDb = 0;''', 1)
old_tick = '''        shownIn = ballistics(shownIn, Math.min(1, levels.current.in));
        shownOut = ballistics(shownOut, Math.min(1, levels.current.out));
        drawMeter(mIn, shownIn);
        drawMeter(mOut, shownOut);'''
new_tick = '''        shownIn = ballistics(shownIn, Math.min(1, levels.current.in));
        shownOut = ballistics(shownOut, Math.min(1, levels.current.out));
        drawMeter(mIn, shownIn);
        drawMeter(mOut, shownOut);
        // Same processor GR value and ballistics as GrReadout.tsx. The number
        // and the red bar derive from one smoothed dB value.
        const grTarget = stateRef.current.bypassed ? 0 : Math.min(0, levels.current.gr);
        shownGrDb += (grTarget - shownGrDb) * (grTarget < shownGrDb ? 0.6 : 0.06);
        if (grBar.current) grBar.current.style.height = (Math.min(24, Math.abs(shownGrDb)) / 24 * 100).toFixed(1) + "%";
        if (grValue.current) grValue.current.textContent = (shownGrDb < -0.05 ? "−" + Math.abs(shownGrDb).toFixed(1) : "0.0");'''
if old_tick in m:
    m = m.replace(old_tick, new_tick, 1)
elif "const grTarget = stateRef.current.bypassed" not in m:
    raise SystemExit("Could not add GR value update")
old_mock = '''        const { bypassed, driveDb, thresholdSteps, outputDb } = stateRef.current;
        lvl += (0.35 + 0.35 * Math.random() - lvl) * 0.07;'''
new_mock = '''        const { bypassed, driveDb, thresholdSteps, outputDb } = stateRef.current;
        const threshold = thresholdSteps / 128;
        const driven = 0.45 * Math.pow(10, driveDb / 20);
        const grTarget = !bypassed && driven > threshold
          ? -Math.min(24, 20 * Math.log10(driven / threshold) * 0.8) : 0;
        shownGrDb += (grTarget - shownGrDb) * (grTarget < shownGrDb ? 0.6 : 0.06);
        if (grBar.current) grBar.current.style.height = (Math.min(24, Math.abs(shownGrDb)) / 24 * 100).toFixed(1) + "%";
        if (grValue.current) grValue.current.textContent = (shownGrDb < -0.05 ? "−" + Math.abs(shownGrDb).toFixed(1) : "0.0");
        lvl += (0.35 + 0.35 * Math.random() - lvl) * 0.07;'''
if old_mock in m:
    m = m.replace(old_mock, new_mock, 1)
elif "const grTarget = !bypassed && driven > threshold" not in m:
    raise SystemExit("Could not add GR mock-preview behavior")
old_return = '''  return (
    <div className="meter-unit">
      <div className="meter-pair">'''
new_return = '''  return (
    <div className="meter-unit">
      <div className="gr-meter-col" aria-label="Gain reduction meter">
        <div className="gr-meter-value" ref={grValue}>0.0</div>
        <div className="meter gr-meter" id="meter-gr" title="Gain reduction in dB">
          <div className="gr-bar" ref={grBar} />
        </div>
        <div className="meter-label gr-meter-label">GR</div>
      </div>
      <div className="meter-pair">'''
if old_return in m:
    m = m.replace(old_return, new_return, 1)
elif 'className="gr-meter-col"' not in m:
    raise SystemExit("Could not insert GR meter")
meters_path.write_text(m, encoding="utf-8")

# Expanded V1.2 canvas: its aspect ratio remains almost unchanged, and this
# width is needed to keep a visible gap between GR and the IN/OUT meter group.
fit_path = root / "ui/src/fit.ts"
fit = fit_path.read_text(encoding="utf-8")
fit = fit.replace('export const DESIGN = { width: 620, height: 380 } as const;',
                  'export const DESIGN = { width: 650, height: 398 } as const;', 1)
fit_path.write_text(fit, encoding="utf-8")
css_path = root / "ui/src/App.css"
css = css_path.read_text(encoding="utf-8")
css = css.replace('width: 620px; height: 380px;', 'width: 650px; height: 398px;', 1)
css = css.replace('grid-template-columns: 288px 1fr auto 58px;',
                  'grid-template-columns: 288px 1fr auto 82px;', 1)
css += r'''
/* V1.2 only: a separate GR lane, followed by the grouped IN/OUT pair. */
.meter-unit {
  height: 82%;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  justify-content: center;
  gap: 10px;
}
.gr-meter-col {
  flex: 0 0 16px;
  min-width: 16px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.gr-meter-value {
  width: 30px;
  min-height: 10px;
  overflow: visible;
  text-align: center;
  white-space: nowrap;
  color: #ff5c64;
  font: 700 6px/10px "Martian Mono", monospace;
  letter-spacing: 0.015em;
}
.gr-meter-col .gr-meter {
  flex: 1 1 auto;
  width: 7px;
  min-height: 0;
}
.gr-meter .gr-bar {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 0%;
  background: linear-gradient(to bottom, #ff6868, #d52e42);
  box-shadow: 0 0 7px rgba(255, 61, 75, 0.42);
}
.gr-meter-label {
  text-align: center;
  white-space: nowrap;
  letter-spacing: 0.08em;
  font-size: 8px;
}
.meter-pair {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  justify-content: center;
  gap: 7px;
}
.meter-pair .meter-col { flex: 1 1 0; min-width: 0; }
.meter-pair .meter-label {
  font-size: 8px;
  letter-spacing: 0.08em;
  white-space: nowrap;
}
/* Use the extra V1.2 canvas height for clearer parameter grouping. */
.knob-col { gap: 14px; }
.stack { padding-top: 10px; }
.stack #monolow { margin-top: 32px; }
'''
css_path.write_text(css, encoding="utf-8")


# V1.2 meter readouts/reset controls and lower-overhead knob dragging.
# Keep the version and JUCE product identifiers unchanged.
meters_path = root / "ui/src/Meters.tsx"
meters_content = r'''import { memo, useEffect, useRef } from "react";
import { inJuce, onLevels } from "./bridge";

type MeterKind = "in" | "out" | "gr";

interface MeterState {
  bar: HTMLDivElement | null;
  peakEl: HTMLDivElement | null;
  valueEl: HTMLButtonElement | null;
  peak: number;
  age: number;
}

function formatDbfs(level: number): string {
  if (level <= 1e-6) return "0.0";
  const db = 20 * Math.log10(level);
  if (db <= -60) return "−60.0";
  if (db < -0.05) return "−" + Math.abs(db).toFixed(1);
  if (db > 0.05) return "+" + db.toFixed(1);
  return "0.0";
}

function formatGr(db: number): string {
  if (db < -0.05) return "−" + Math.abs(db).toFixed(1) + " dB";
  return "0.0 dB";
}

function drawMeter(m: MeterState, shown: number, peakSample: number) {
  if (m.bar) m.bar.style.height = (Math.max(0, Math.min(1, shown)) * 100).toFixed(1) + "%";
  if (peakSample >= 0) {
    if (peakSample >= m.peak) {
      m.peak = peakSample;
      m.age = 0;
    } else if (++m.age > 90) {
      m.peak *= 0.985;
    }
  } else if (++m.age > 90) {
    m.peak *= 0.985;
  }
  if (m.peakEl) m.peakEl.style.bottom = (Math.max(0, Math.min(1, m.peak)) * 100).toFixed(1) + "%";
  if (m.valueEl) m.valueEl.textContent = m.peak <= 1e-6 ? "0.0" : formatDbfs(m.peak);
}

function Meters({
  bypassed,
  driveDb,
  thresholdSteps,
  outputDb,
}: {
  bypassed: boolean;
  driveDb: number;
  thresholdSteps: number;
  outputDb: number;
}) {
  const inBar = useRef<HTMLDivElement>(null);
  const inPeak = useRef<HTMLDivElement>(null);
  const inPeakValue = useRef<HTMLButtonElement>(null);
  const outBar = useRef<HTMLDivElement>(null);
  const outPeak = useRef<HTMLDivElement>(null);
  const outPeakValue = useRef<HTMLButtonElement>(null);
  const grBar = useRef<HTMLDivElement>(null);
  const grValue = useRef<HTMLButtonElement>(null);
  const levels = useRef({ in: 0, out: 0, gr: 0 });
  const levelSerial = useRef(0);
  const meterStates = useRef<{ in: MeterState | null; out: MeterState | null }>({ in: null, out: null });
  const resetSerial = useRef({ in: 0, out: 0, gr: 0 });
  const resetBaseline = useRef({ in: 0, out: 0, gr: 0 });
  const stateRef = useRef({ bypassed, driveDb, thresholdSteps, outputDb });
  stateRef.current = { bypassed, driveDb, thresholdSteps, outputDb };

  const resetMeter = (kind: MeterKind) => {
    resetBaseline.current[kind] = levelSerial.current;
    levels.current[kind] = 0;
    resetSerial.current[kind] += 1;
    if (kind === "in" || kind === "out") {
      const state = meterStates.current[kind];
      if (state) {
        state.peak = 0;
        state.age = 0;
        if (state.bar) state.bar.style.height = "0%";
        if (state.peakEl) state.peakEl.style.bottom = "0%";
        if (state.valueEl) state.valueEl.textContent = "0.0";
      }
    } else {
      if (grBar.current) grBar.current.style.height = "0%";
      if (grValue.current) grValue.current.textContent = "0.0 dB";
    }
  };

  useEffect(() => {
    const mIn: MeterState = { bar: inBar.current, peakEl: inPeak.current, valueEl: inPeakValue.current, peak: 0, age: 0 };
    const mOut: MeterState = { bar: outBar.current, peakEl: outPeak.current, valueEl: outPeakValue.current, peak: 0, age: 0 };
    meterStates.current = { in: mIn, out: mOut };
    const unsub = onLevels((l) => {
      levels.current = l;
      levelSerial.current += 1;
    });

    const seenReset = { in: 0, out: 0, gr: 0 };
    let seenLevelSerial = -1;
    let raf = 0;
    let lvl = 0.4;
    let shownIn = 0;
    let shownOut = 0;
    let shownGrDb = 0;
    const ballistics = (shown: number, target: number) =>
      target > shown ? shown + (target - shown) * 0.5 : shown * 0.88;

    const tick = () => {
      const serial = resetSerial.current;
      if (seenReset.in !== serial.in) {
        seenReset.in = serial.in;
        shownIn = 0;
        mIn.peak = 0; mIn.age = 0;
      }
      if (seenReset.out !== serial.out) {
        seenReset.out = serial.out;
        shownOut = 0;
        mOut.peak = 0; mOut.age = 0;
      }
      if (seenReset.gr !== serial.gr) {
        seenReset.gr = serial.gr;
        shownGrDb = 0;
      }

      if (inJuce) {
        const currentSerial = levelSerial.current;
        const freshLevels = currentSerial !== seenLevelSerial;
        seenLevelSerial = currentSerial;
        const inputSampleIsNew = currentSerial > resetBaseline.current.in;
        const outputSampleIsNew = currentSerial > resetBaseline.current.out;
        const grSampleIsNew = currentSerial > resetBaseline.current.gr;
        const rawIn = inputSampleIsNew ? Math.max(0, levels.current.in) : 0;
        const rawOut = outputSampleIsNew ? Math.max(0, levels.current.out) : 0;
        shownIn = ballistics(shownIn, Math.min(1, rawIn));
        shownOut = ballistics(shownOut, Math.min(1, rawOut));
        drawMeter(mIn, shownIn, freshLevels && inputSampleIsNew ? rawIn : -1);
        drawMeter(mOut, shownOut, freshLevels && outputSampleIsNew ? rawOut : -1);

        // Single GR source: the native processor's last-block dB reading.
        // Use the same 0.6 attack / 0.06 release smoothing as the former
        // scope-corner readout so the bar/value preserve its exact metric.
        const grTarget = stateRef.current.bypassed || !grSampleIsNew
          ? 0 : Math.min(0, levels.current.gr);
        shownGrDb += (grTarget - shownGrDb) * (grTarget < shownGrDb ? 0.6 : 0.06);
      } else {
        const { bypassed: byp, driveDb: drive, thresholdSteps: steps, outputDb: output } = stateRef.current;
        lvl += (0.35 + 0.35 * Math.random() - lvl) * 0.07;
        const inShown = Math.max(0, lvl + 0.06 * Math.sin(Date.now() / 230));
        shownIn = ballistics(shownIn, Math.min(1, inShown));
        drawMeter(mIn, shownIn, inShown);
        if (byp) {
          shownOut = ballistics(shownOut, inShown);
          drawMeter(mOut, shownOut, inShown);
        } else {
          const threshold = steps / 128;
          const driven = inShown * Math.pow(10, (drive / 20) * 0.5);
          const clipped = Math.min(driven, Math.max(threshold, Math.min(1, driven * 0.85)));
          const outGain = Math.pow(10, (output / 20) * 0.5);
          const outTarget = Math.min(1, clipped * outGain);
          shownOut = ballistics(shownOut, outTarget);
          drawMeter(mOut, shownOut, outTarget);
        }
        const threshold = steps / 128;
        const driven = 0.45 * Math.pow(10, drive / 20);
        const grTarget = !byp && driven > threshold
          ? -Math.min(24, 20 * Math.log10(driven / threshold) * 0.8) : 0;
        shownGrDb += (grTarget - shownGrDb) * (grTarget < shownGrDb ? 0.6 : 0.06);
      }

      if (grBar.current)
        grBar.current.style.height = (Math.min(24, Math.abs(shownGrDb)) / 24 * 100).toFixed(1) + "%";
      if (grValue.current) grValue.current.textContent = formatGr(shownGrDb);
      raf = requestAnimationFrame(tick);
    };

    tick();
    return () => {
      cancelAnimationFrame(raf);
      unsub();
      meterStates.current = { in: null, out: null };
    };
  }, []);

  return (
    <div className="meter-unit" aria-label="Audio level meters">
      <div className="meter-col gr-meter-col">
        <button type="button" className="meter-value gr-meter-value" ref={grValue}
          title="Gain reduction in dB; click to reset this meter"
          aria-label="Reset gain reduction meter" onClick={() => resetMeter("gr")}>0.0 dB</button>
        <div className="meter gr-meter" id="meter-gr" title="Gain reduction">
          <div className="gr-bar" ref={grBar} />
        </div>
        <div className="meter-label gr-meter-label">GR</div>
      </div>
      <div className="meter-col">
        <button type="button" className="meter-value" ref={inPeakValue}
          title="Input peak in dBFS; click to reset this meter"
          aria-label="Reset input peak meter" onClick={() => resetMeter("in")}>0.0</button>
        <div className="meter" id="meter-in">
          <div className="bar" ref={inBar} />
          <div className="peak" ref={inPeak} />
        </div>
        <div className="meter-label">In</div>
      </div>
      <div className="meter-col">
        <button type="button" className="meter-value" ref={outPeakValue}
          title="Output peak in dBFS; click to reset this meter"
          aria-label="Reset output peak meter" onClick={() => resetMeter("out")}>0.0</button>
        <div className="meter" id="meter-out">
          <div className="bar" ref={outBar} />
          <div className="peak" ref={outPeak} />
        </div>
        <div className="meter-label">Out</div>
      </div>
    </div>
  );
}

export default memo(Meters, (prev, next) => {
  if (inJuce) return prev.bypassed === next.bypassed;
  return prev.bypassed === next.bypassed
    && prev.driveDb === next.driveDb
    && prev.thresholdSteps === next.thresholdSteps
    && prev.outputDb === next.outputDb;
});
'''
meters_path.write_text(meters_content, encoding="utf-8")

# The dedicated GR meter is now the only numeric GR display in V1.2.
app_path = root / "ui/src/App.tsx"
a = app_path.read_text(encoding="utf-8")
a = a.replace('import GrReadout from "./GrReadout";\n', "", 1)
a = a.replace('            <GrReadout bypassed={bypassed} driveDb={driveDb} thresholdSteps={thresholdSteps} />\n', "", 1)

# Use the threshold knob's current frame value for the curve immediately,
# without waiting for the asynchronous JUCE valueChangedEvent round-trip.
old_threshold = '  const thresholdSteps = useScaled(params.threshold);'
new_threshold = '''  const thresholdFromHost = useScaled(params.threshold);
  const [thresholdOptimistic, setThresholdOptimistic] = useState<number | null>(null);
  const [thresholdIsDragging, setThresholdIsDragging] = useState(false);
  const thresholdSteps = thresholdOptimistic ?? thresholdFromHost;
  useEffect(() => {
    if (!thresholdIsDragging && thresholdOptimistic !== null
        && Math.round(thresholdFromHost) === Math.round(thresholdOptimistic))
      setThresholdOptimistic(null);
  }, [thresholdFromHost, thresholdOptimistic, thresholdIsDragging]);'''
if old_threshold in a:
    a = a.replace(old_threshold, new_threshold, 1)
elif 'const thresholdFromHost = useScaled(params.threshold);' not in a:
    raise SystemExit("Could not add optimistic threshold state")

factory_from = '''    const [, vals, curve, osFactor] = PRESETS[idx];
    for (const [key, v] of Object.entries(vals)) params[key].setScaled(v);'''
factory_to = '''    const [, vals, curve, osFactor] = PRESETS[idx];
    setThresholdOptimistic(vals.threshold);
    setThresholdIsDragging(false);
    for (const [key, v] of Object.entries(vals)) params[key].setScaled(v);'''
if factory_from in a:
    a = a.replace(factory_from, factory_to, 1)
custom_from = '''  const applyCustomPreset = (preset: StoredPreset) => {
    for (const key of Object.keys(PARAMS)) params[key].setScaled(preset.values[key]);'''
custom_to = '''  const applyCustomPreset = (preset: StoredPreset) => {
    setThresholdOptimistic(preset.values.threshold);
    setThresholdIsDragging(false);
    for (const key of Object.keys(PARAMS)) params[key].setScaled(preset.values[key]);'''
if custom_from in a:
    a = a.replace(custom_from, custom_to, 1)
knob_from = '<Knob spec={PARAMS.threshold} param={params.threshold} />'
knob_to = '''<Knob spec={PARAMS.threshold} param={params.threshold}
            onValueChange={setThresholdOptimistic}
            onDragStateChange={setThresholdIsDragging} />'''
if knob_from in a:
    a = a.replace(knob_from, knob_to, 1)
elif 'onValueChange={setThresholdOptimistic}' not in a:
    raise SystemExit("Could not wire the threshold knob to live curve updates")
if "<GrReadout" in a or 'import GrReadout from "./GrReadout";' in a:
    raise SystemExit("Duplicate scope GR metric remains")
app_path.write_text(a, encoding="utf-8")


# Make the knob's visual position update on the input event immediately while
# limiting host relay writes to at most one per display frame. This keeps the
# UI responsive without queuing redundant JUCE parameter messages.
knob_path = root / "ui/src/Knob.tsx"
knob = knob_path.read_text(encoding="utf-8")
knob = knob.replace('import { useEffect, useMemo, useRef, useState } from "react";',
                    'import { memo, useEffect, useMemo, useRef, useState } from "react";', 1)
knob = knob.replace("export default function Knob(", "function Knob(", 1)
const oldKnobSignature = "function Knob({ spec, param }: { spec: ParamSpec; param: ParamHandle }) {";
const newKnobSignature = "function Knob({ spec, param, onValueChange, onDragStateChange }: { spec: ParamSpec; param: ParamHandle; onValueChange?: (value: number) => void; onDragStateChange?: (active: boolean) => void }) {";
if (knob.includes(oldKnobSignature))
  knob = knob.replace(oldKnobSignature, newKnobSignature, 1);
else if (!knob.includes("onValueChange, onDragStateChange"))
  raise SystemExit("Could not extend Knob props for live threshold graph updates");

old_commit = '''  const commitValue = (v: number, fine: boolean) => {
    v = Math.min(spec.max, Math.max(spec.min, v));
    if (spec.step) v = Math.round(v / spec.step) * spec.step;
    else if (!fine) v = Math.round(v * 100) / 100;
    setValue(v);
    if (Math.abs(v - lastCommitted.current) < 1e-7) return;
    lastCommitted.current = v;
    param.setScaled(v);
  };
  const set = commitValue;
  const scheduleValue = (v: number, fine: boolean) => {
    pendingValue.current = { value: v, fine };
    if (frameRequest.current !== null) return;
    frameRequest.current = window.requestAnimationFrame(() => {
      frameRequest.current = null;
      const pending = pendingValue.current;
      pendingValue.current = null;
      if (pending) commitValue(pending.value, pending.fine);
    });
  };'''
new_commit = '''  const normaliseValue = (v: number, fine: boolean) => {
    v = Math.min(spec.max, Math.max(spec.min, v));
    if (spec.step) v = Math.round(v / spec.step) * spec.step;
    else if (!fine) v = Math.round(v * 100) / 100;
    return v;
  };
  const commitValue = (v: number, fine: boolean, updateLocal = true) => {
    v = normaliseValue(v, fine);
    if (updateLocal) setValue(v);
    onValueChange?.(v);
    if (Math.abs(v - lastCommitted.current) < 1e-7) return;
    lastCommitted.current = v;
    param.setScaled(v);
  };
  const set = (v: number, fine: boolean) => commitValue(v, fine, true);
  const scheduleValue = (v: number, fine: boolean) => {
    const immediate = normaliseValue(v, fine);
    // Update the knob artwork immediately; only native parameter writes wait
    // for the next animation frame.
    setValue(immediate);
    pendingValue.current = { value: immediate, fine };
    if (frameRequest.current !== null) return;
    frameRequest.current = window.requestAnimationFrame(() => {
      frameRequest.current = null;
      const pending = pendingValue.current;
      pendingValue.current = null;
      if (pending) commitValue(pending.value, pending.fine, false);
    });
  };'''
if old_commit in knob:
    knob = knob.replace(old_commit, new_commit, 1)
elif "const normaliseValue = (v: number, fine: boolean)" not in knob:
    raise SystemExit("Could not locate V1.2 knob commit/schedule block")
knob = knob.replace("if (pending) commitValue(pending.value, pending.fine);",
                    "if (pending) commitValue(pending.value, pending.fine, false);", 1)
if "export default memo(Knob);" not in knob:
    knob += "\n\nexport default memo(Knob);\n"
# Forward threshold drag state so the optimistic curve value is kept until host acknowledgement.
mouse_start = 'drag.current = { startY: e.clientY, startVal: value, active: true };\n    setIsDragging(true);\n    param.dragStarted();'
if mouse_start in knob:
    knob = knob.replace(mouse_start,
        'drag.current = { startY: e.clientY, startVal: value, active: true };\n    setIsDragging(true);\n    onDragStateChange?.(true);\n    param.dragStarted();', 1)
touch_start = 'drag.current = { startY: first.clientY, startVal: value, active: true };\n    setIsDragging(true);\n    const touchId = first.identifier;'
if touch_start in knob:
    knob = knob.replace(touch_start,
        'drag.current = { startY: first.clientY, startVal: value, active: true };\n    setIsDragging(true);\n    onDragStateChange?.(true);\n    const touchId = first.identifier;', 1)
mouse_finish = 'drag.current.active = false;\n      setIsDragging(false);\n      window.removeEventListener("mousemove", onMove);'
if mouse_finish in knob:
    knob = knob.replace(mouse_finish,
        'drag.current.active = false;\n      setIsDragging(false);\n      onDragStateChange?.(false);\n      window.removeEventListener("mousemove", onMove);', 1)
touch_finish = 'drag.current.active = false;\n          setIsDragging(false);\n          window.removeEventListener("touchmove", onMove);'
if touch_finish in knob:
    knob = knob.replace(touch_finish,
        'drag.current.active = false;\n          setIsDragging(false);\n          onDragStateChange?.(false);\n          window.removeEventListener("touchmove", onMove);', 1)
knob_path.write_text(knob, encoding="utf-8")

# Keep the curved transfer scope from rebuilding 160-point SVG strings for
# unrelated control changes. Memoise the path geometry, then memoise its child.
scope_path = root / "ui/src/Scope.tsx"
scope = scope_path.read_text(encoding="utf-8")
scope = scope.replace('import { useEffect, useRef } from "react";',
                      'import { memo, useEffect, useMemo, useRef } from "react";', 1)
scope = scope.replace("export default function Scope(", "function Scope(", 1)
path_marker = "  const fn = CURVE_FN[curve];"
path_insert = path_marker + '''
  const curveD = useMemo(() => curvePath(fn, t), [fn, t]);
  const deltaD = useMemo(() => deltaPath(fn, t), [fn, t]);'''
if path_marker in scope and "const curveD = useMemo" not in scope:
    scope = scope.replace(path_marker, path_insert, 1)
scope = scope.replace("d={deltaPath(fn, t)}", "d={deltaD}", 1)
scope = scope.replace("d={curvePath(fn, t)}", "d={curveD}", 1)
if "export default memo(Scope);" not in scope:
    scope += "\n\nexport default memo(Scope);\n"
scope_path.write_text(scope, encoding="utf-8")

# The scope-corner numeric GR display also needs no React parent render on every
# knob move in the native plugin. Its own RAF reads the native levels stream.
gr_path = root / "ui/src/GrReadout.tsx"
gr = gr_path.read_text(encoding="utf-8")
gr = gr.replace('import { useEffect, useRef } from "react";',
                'import { memo, useEffect, useRef } from "react";', 1)
gr = gr.replace("export default function GrReadout(", "function GrReadout(", 1)
if "export default memo(GrReadout" not in gr:
    gr += '''
 
export default memo(GrReadout, (prev, next) => {
  if (inJuce) return prev.bypassed === next.bypassed;
  return prev.bypassed === next.bypassed
    && prev.driveDb === next.driveDb
    && prev.thresholdSteps === next.thresholdSteps;
});
'''
gr_path.write_text(gr, encoding="utf-8")

# Expand V1.2 just enough to fit three equally-spaced meters and numeric readouts.
fit_path = root / "ui/src/fit.ts"
fit = fit_path.read_text(encoding="utf-8")
fit = fit.replace("width: 650, height: 398", "width: 680, height: 398", 1)
fit_path.write_text(fit, encoding="utf-8")
css_path = root / "ui/src/App.css"
css = css_path.read_text(encoding="utf-8")
css = css.replace("width: 650px; height: 398px;", "width: 680px; height: 398px;", 1)
css = css.replace("grid-template-columns: 288px 1fr auto 82px;",
                  "grid-template-columns: 288px 1fr auto 116px;", 1)
css += r'''
/* V1.2 meter refinements: identical spacing between all three meter bars. */
.header-right { gap: 16px; }
#power { margin-left: 5px; }
.meter-unit {
  height: 82%;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  justify-content: center;
  gap: 22px;
}
.meter-col, .gr-meter-col {
  flex: 0 0 20px;
  min-width: 20px;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}
.meter-value {
  appearance: none;
  -webkit-appearance: none;
  flex: 0 0 12px;
  width: 38px;
  min-width: 38px;
  height: 12px;
  min-height: 12px;
  margin: 0 0 8px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--accent);
  font: 700 6.5px/12px "Martian Mono", monospace;
  letter-spacing: 0;
  text-align: center;
  white-space: nowrap;
  cursor: pointer;
  overflow: visible;
}
.meter-value:hover { color: var(--text-hi); }
.meter-value:active { opacity: 0.6; }
.meter-value:focus { outline: none; }
.meter-value:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
.meter-col .meter, .gr-meter-col .meter {
  flex: 1 1 auto;
  width: 7px;
  min-width: 7px;
  min-height: 0;
  align-self: center;
}
.meter-label, .gr-meter-label {
  flex: 0 0 auto;
  margin-top: 9px;
  font-size: 8px;
  line-height: 10px;
  letter-spacing: 0.08em;
  text-align: center;
  white-space: nowrap;
}
.gr-meter-value { color: #ff626b; }
.gr-meter-value:hover { color: #ff9aa0; }
.gr-meter .gr-bar {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  bottom: auto;
  height: 0%;
  background: linear-gradient(to bottom, #ff6868, #d52e42);
  box-shadow: 0 0 7px rgba(255, 61, 75, 0.42);
}
.knob-col { gap: 14px; }
.stack { padding-top: 10px; }
.stack #monolow { margin-top: 32px; }
'''
css_path.write_text(css, encoding="utf-8")

# Keep the JUCE editor canvas, viewport design size, and CSS canvas in agreement.
editor_path = root / "plugin/PluginEditor.cpp"
e = editor_path.read_text(encoding="utf-8")
e = e.replace("designWidth  = 650;", "designWidth  = 680;", 1)
if "designWidth  = 680;" not in e:
    raise SystemExit("Could not update V1.2 native editor width")
editor_path.write_text(e, encoding="utf-8")

print("Applied V1.2 meter peak readouts/reset controls and low-overhead knob responsiveness.")

index_path = root / "ui/index.html"
index_path.write_text(index_path.read_text(encoding="utf-8").replace(
    "<title>TagoClip</title>", "<title>TagoClip V1.2</title>", 1
), encoding="utf-8")
package_path = root / "ui/package.json"
package = json.loads(package_path.read_text(encoding="utf-8"))
package["name"] = "tagoclip-v12"
package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
lock_path = root / "ui/package-lock.json"
if lock_path.exists():
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["name"] = "tagoclip-v12"
    if isinstance(lock.get("packages"), dict) and isinstance(lock["packages"].get(""), dict):
        lock["packages"][""]["name"] = "tagoclip-v12"
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

print("Configured TagoClip V1.2: unique bundle identity, version-specific presets, GR meter and save-input fixes.")
