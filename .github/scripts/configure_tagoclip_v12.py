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
b = b.replace("--target TagoClip_VST3 TagoClip_AU", "--target TagoClipV12_VST3 TagoClipV12_AU", 1)
b = b.replace('ART="$ROOT/build-mojave/TagoClip_artefacts/Release"', 'ART="$ROOT/build-mojave/TagoClipV12_artefacts/Release"', 1)
b = b.replace('VST3="$ART/VST3/TagoClip.vst3"', 'VST3="$ART/VST3/TagoClip V1.2.vst3"', 1)
b = b.replace('AU="$ART/AU/TagoClip.component"', 'AU="$ART/AU/TagoClip V1.2.component"', 1)
b = b.replace('BIN="$BUNDLE/Contents/MacOS/TagoClip"\n    [[ -f "$BIN" ]] || fail "Plugin executable missing: $BIN"',
              'BIN="$(find "$BUNDLE/Contents/MacOS" -maxdepth 1 -type f -print -quit)"\n    [[ -n "$BIN" && -f "$BIN" ]] || fail "Plugin executable missing in: $BUNDLE/Contents/MacOS"', 1)
if "TagoClipV12_VST3 TagoClipV12_AU" not in b or "TagoClip V1.2.vst3" not in b:
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
old_form = '<form className="preset-save-form" onSubmit={(event) => { event.preventDefault(); void saveCurrentPreset(); }}>'
new_form = '<form className="preset-save-form" onKeyDown={(event) => event.stopPropagation()} onKeyUp={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); void saveCurrentPreset(); }}>'
if old_form in a:
    a = a.replace(old_form, new_form, 1)
elif 'className="preset-save-form" onKeyDown=' not in a:
    raise SystemExit("Could not isolate keyboard shortcuts inside the preset form")
old_input = 'value={saveName} autoFocus onChange={(event) => setSaveName(event.target.value)} />'
new_input = 'value={saveName} autoFocus\n                    onKeyDown={(event) => event.stopPropagation()}\n                    onKeyUp={(event) => event.stopPropagation()}\n                    onChange={(event) => setSaveName(event.target.value)} />'
if old_input in a:
    a = a.replace(old_input, new_input, 1)
elif 'onKeyDown={(event) => event.stopPropagation()}' not in a:
    raise SystemExit("Could not route Spacebar and keyboard events inside save-name input")
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
