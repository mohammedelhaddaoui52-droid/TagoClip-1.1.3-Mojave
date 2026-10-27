#!/usr/bin/env python3
"""Apply Mojave WebView diagnostics and safe UI fallbacks to a prepared TagoClip tree."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve()
editor = root / "plugin/PluginEditor.cpp"
s = editor.read_text()
if "RESOURCE_MISSING url=" not in s:
    old = '''const char* mimeForExtension (const juce::String& ext)
{
    if (ext == "html") return "text/html";
    if (ext == "js")   return "text/javascript";
    if (ext == "css")  return "text/css";
    if (ext == "svg")  return "image/svg+xml";
    if (ext == "json") return "application/json";
    if (ext == "png")  return "image/png";
    if (ext == "woff2") return "font/woff2";
    return "application/octet-stream";
}
} // namespace

std::optional<juce::WebBrowserComponent::Resource> TagoClipEditor::lookupResource (const juce::String& url)
{
    // The Vite build is bundled as a zip in BinaryData; entries are stored
    // relative to dist/ (index.html, assets/...).
    static juce::MemoryInputStream zipStream (BinaryData::webui_zip, BinaryData::webui_zipSize, false);
    static juce::ZipFile zip (zipStream);

    const auto path = url == "/" ? juce::String ("index.html") : url.fromFirstOccurrenceOf ("/", false, false);

    if (const auto* entry = zip.getEntry (path))
    {
        std::unique_ptr<juce::InputStream> stream (zip.createStreamForEntry (*entry));
        if (stream == nullptr)
            return std::nullopt;

        std::vector<std::byte> data ((size_t) stream->getTotalLength());
        stream->read (data.data(), (int) data.size());
        return juce::WebBrowserComponent::Resource { std::move (data),
                                                     mimeForExtension (path.fromLastOccurrenceOf (".", false, false)) };
    }
    return std::nullopt;
}
'''
    new = '''const char* mimeForExtension (juce::String ext)
{
    ext = ext.toLowerCase();
    if (ext == "html") return "text/html; charset=utf-8";
    if (ext == "js" || ext == "mjs") return "text/javascript; charset=utf-8";
    if (ext == "css")  return "text/css; charset=utf-8";
    if (ext == "svg")  return "image/svg+xml";
    if (ext == "json") return "application/json";
    if (ext == "png")  return "image/png";
    if (ext == "woff2") return "font/woff2";
    return "application/octet-stream";
}

juce::File diagnosticLogFile()
{
    auto directory = juce::File::getSpecialLocation (juce::File::userHomeDirectory)
                         .getChildFile ("Library")
                         .getChildFile ("Logs")
                         .getChildFile ("TagoClip");
    directory.createDirectory();
    return directory.getChildFile ("TagoClip-WebView.log");
}

void writeUiDiagnostic (juce::String message)
{
    static juce::CriticalSection lock;
    const juce::ScopedLock scopedLock (lock);
    message = message.replaceCharacters ("\\r\\n", "  ");
    diagnosticLogFile().appendText (juce::Time::getCurrentTime().toISO8601 (true) + " " + message + "\\n",
                                    false, false, "\\n");
}

juce::String resourcePathFromUrl (juce::String url)
{
    // JUCE normally supplies a path such as "/assets/index-xxxx.js". Also
    // accept full URLs defensively, and remove query/fragment suffixes.
    if (url.contains ("://"))
    {
        const auto schemeEnd = url.indexOf ("://") + 3;
        const auto pathOffset = url.substring (schemeEnd).indexOfChar ('/');
        const auto pathStart = pathOffset >= 0 ? schemeEnd + pathOffset : -1;
        url = pathStart >= 0 ? url.substring (pathStart) : juce::String ("/");
    }
    url = url.upToFirstOccurrenceOf ("?", false, false)
             .upToFirstOccurrenceOf ("#", false, false);
    if (url.isEmpty() || url == "/")
        return "index.html";
    while (url.startsWithChar ('/'))
        url = url.substring (1);
    return url;
}
} // namespace

std::optional<juce::WebBrowserComponent::Resource> TagoClipEditor::lookupResource (const juce::String& url)
{
    // Log requests to distinguish missing embedded resources from JavaScript errors.
    static juce::MemoryInputStream zipStream (BinaryData::webui_zip, BinaryData::webui_zipSize, false);
    static juce::ZipFile zip (zipStream);

    const auto path = resourcePathFromUrl (url);
    if (const auto* entry = zip.getEntry (path))
    {
        std::unique_ptr<juce::InputStream> stream (zip.createStreamForEntry (*entry));
        if (stream == nullptr)
        {
            writeUiDiagnostic ("RESOURCE_STREAM_FAIL url=" + url + " path=" + path);
            return std::nullopt;
        }

        std::vector<std::byte> data ((size_t) stream->getTotalLength());
        const auto bytesRead = stream->read (data.data(), (int) data.size());
        if (bytesRead != (int) data.size())
        {
            writeUiDiagnostic ("RESOURCE_SHORT_READ url=" + url + " path=" + path
                               + " expected=" + juce::String ((int) data.size())
                               + " got=" + juce::String (bytesRead));
            return std::nullopt;
        }
        writeUiDiagnostic ("RESOURCE_OK url=" + url + " path=" + path
                           + " bytes=" + juce::String ((int) data.size()));
        return juce::WebBrowserComponent::Resource { std::move (data),
                                                     mimeForExtension (path.fromLastOccurrenceOf (".", false, false)) };
    }

    writeUiDiagnostic ("RESOURCE_MISSING url=" + url + " path=" + path);
    return std::nullopt;
}
'''
    if old not in s:
        raise SystemExit("Could not locate original resource loader block in PluginEditor.cpp")
    s = s.replace(old, new)
    old2 = '''                   .withNativeFunction ("releaseFocus",
                                        [this] (const juce::Array<juce::var>&,
                                                juce::WebBrowserComponent::NativeFunctionCompletion done)
                                        {
#if JUCE_WINDOWS
                                            releaseWebViewFocus (*this);
#else
                                            (void) this;
#endif
                                            done (juce::var());
                                        })
                   .withOptionsFrom (driveRelay)
'''
    new2 = '''                   .withNativeFunction ("releaseFocus",
                                        [this] (const juce::Array<juce::var>&,
                                                juce::WebBrowserComponent::NativeFunctionCompletion done)
                                        {
#if JUCE_WINDOWS
                                            releaseWebViewFocus (*this);
#else
                                            (void) this;
#endif
                                            done (juce::var());
                                        })
                   .withEventListener ("uiDiagnostic", [] (juce::var event)
                                        {
                                            if (auto* object = event.getDynamicObject())
                                            {
                                                const auto type = object->getProperty ("type").toString();
                                                const auto message = object->getProperty ("message").toString();
                                                const auto detail = object->getProperty ("detail").toString();
                                                writeUiDiagnostic ("JS_" + type + " message=" + message + " detail=" + detail);
                                            }
                                            else
                                            {
                                                writeUiDiagnostic ("JS_DIAGNOSTIC " + event.toString());
                                            }
                                        })
                   .withUserScript (R"JS(
                       (function () {
                           function report(type, message, detail) {
                               try {
                                   window.__JUCE__.backend.emitEvent("uiDiagnostic", {
                                       type: String(type || "unknown"),
                                       message: String(message || ""),
                                       detail: String(detail || "")
                                   });
                               } catch (ignored) {}
                           }
                           window.addEventListener("error", function (event) {
                               var target = event && event.target;
                               var error = event && event.error;
                               var resource = target && target !== window && (target.src || target.href);
                               var targetInfo = target && target !== window
                                   ? (target.tagName || "element") + "; type="
                                     + (target.type || "") + "; src=" + (target.src || target.href || "")
                                     + "; html=" + String(target.outerHTML || "").slice(0, 180)
                                   : "window";
                               var stack = "";
                               try { stack = error && (error.stack || error.message) || ""; } catch (ignored) {}
                               var message = event && event.message || error && (error.message || String(error)) || "";
                               report(resource ? "resource-error" : "error",
                                   message || "Unspecified JavaScript error",
                                   "file=" + (event && event.filename || "")
                                   + "; line=" + (event && event.lineno || 0)
                                   + "; col=" + (event && event.colno || 0)
                                   + "; name=" + (error && error.name || "")
                                   + "; errorMessage=" + (error && error.message || "")
                                   + "; stack=" + stack
                                   + "; target=" + targetInfo);
                           }, true);
                           var originalConsoleError = console.error;
                           console.error = function () {
                               try {
                                   var args = Array.prototype.map.call(arguments, function (item) {
                                       if (item && item.stack) return String(item.stack);
                                       if (item && item.message) return String(item.message);
                                       return String(item);
                                   });
                                   report("console-error", args.join(" "), "console.error intercepted");
                               } catch (ignored) {}
                               return originalConsoleError.apply(console, arguments);
                           };
                           window.addEventListener("unhandledrejection", function (event) {
                               var reason = event && event.reason;
                               report("unhandled-rejection", reason && (reason.stack || reason.message) || reason);
                           });
                           document.addEventListener("DOMContentLoaded", function () {
                               report("dom-ready", "readyState=" + document.readyState,
                                   "root=" + !!document.getElementById("root"));
                           });
                           window.addEventListener("load", function () {
                               report("window-load", "readyState=" + document.readyState,
                                   "plugin=" + !!document.getElementById("plugin")
                                   + "; rootChildren=" + (document.getElementById("root")
                                       ? document.getElementById("root").children.length : -1));
                           });
                       })();
                   )JS")
                   .withOptionsFrom (driveRelay)
'''
    if old2 not in s:
        raise SystemExit("Could not locate native function insertion point in PluginEditor.cpp")
    s = s.replace(old2, new2)
    s = s.replace('''    addAndMakeVisible (browser);

#if TAGOCLIP_DEV_UI
''', '''    addAndMakeVisible (browser);
    writeUiDiagnostic ("EDITOR_OPEN root=" + juce::WebBrowserComponent::getResourceProviderRoot());

#if TAGOCLIP_DEV_UI
''')
    editor.write_text(s)

fit = root / "ui/src/fit.ts"
s = fit.read_text()
old_fit = '''  const observer = new ResizeObserver(apply);
  observer.observe(document.documentElement);
  window.addEventListener("resize", apply);

  return () => {
    observer.disconnect();
    window.removeEventListener("resize", apply);
  };
'''
new_fit = '''  // ResizeObserver is preferred, but keep the UI renderable if an older
  // embedded WebKit build does not expose it. The window resize fallback is
  // sufficient for the plugin editor and does not change the approved layout.
  const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(apply) : null;
  if (observer) observer.observe(document.documentElement);
  window.addEventListener("resize", apply);

  return () => {
    if (observer) observer.disconnect();
    window.removeEventListener("resize", apply);
  };
'''
if old_fit in s:
    fit.write_text(s.replace(old_fit, new_fit))
elif "typeof ResizeObserver" not in s:
    raise SystemExit("Could not locate original ResizeObserver code in fit.ts")

(root / "ui/vite.config.ts").write_text("""import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Use a conservative syntax target for embedded WKWebView versions on macOS Mojave.
export default defineConfig({
  plugins: [react()],
  build: {
    target: 'safari12.1',
    cssTarget: 'safari12.1',
  },
})
""")

# Inline the built JS/CSS into index.html to test whether WebKit rejects the
# external module-script request on JUCE's custom juce:// origin.
inline_helper = root / "scripts/inline_webui_assets.py"
inline_helper.write_text(r'''#!/usr/bin/env python3
"""Inline Vite JS/CSS/font assets into index.html for JUCE WebKit compatibility."""
from pathlib import Path
import base64
import re
import sys

dist = Path(sys.argv[1]).resolve()
index_file = dist / "index.html"
html = index_file.read_text(encoding="utf-8")

def asset_path(url: str, base: Path) -> Path:
    url = url.split("?", 1)[0].split("#", 1)[0]
    if url.startswith("/"):
        return (dist / url.lstrip("/")).resolve()
    return (base / url).resolve()

script_re = re.compile(
    r"""<script\b(?P<attrs>[^>]*)\bsrc=["'](?P<src>[^"']+)["'][^>]*>\s*</script>""",
    re.I | re.S,
)
script_count = 0
inline_script_html = ""

def inline_script(match):
    global script_count, inline_script_html
    tag = match.group(0)
    if not re.search(r"""\btype=["']module["']""", tag, re.I):
        return tag
    js_path = asset_path(match.group("src"), dist)
    if not js_path.is_file():
        raise SystemExit(f"JavaScript bundle not found: {js_path}")
    js = js_path.read_text(encoding="utf-8")
    # Prevent an embedded literal from prematurely closing the HTML script tag.
    js = re.sub(r"</script", r"<\/script", js, flags=re.I)
    script_count += 1
    inline_script_html = '<script>\n' + js + '\n</script>'
    # Vite injects its production script in <head>. A classic inline script
    # there executes before <body> and #root exist. Remove it here and append it
    # immediately before </body> below, preserving normal source order.
    return ""

html = script_re.sub(inline_script, html)
if script_count != 1:
    raise SystemExit(f"Expected exactly one external module script, inlined {script_count}")
if not re.search(r"</body\s*>", html, re.I):
    raise SystemExit("Could not find </body> to place the inline classic script after the mount container")
html = re.sub(
    r"</body\s*>",
    lambda match: inline_script_html + "\n" + match.group(0),
    html,
    count=1,
    flags=re.I,
)

link_re = re.compile(
    r"""<link\b(?=[^>]*\brel=["']stylesheet["'])[^>]*\bhref=["'](?P<href>[^"']+)["'][^>]*>""",
    re.I | re.S,
)
css_count = 0
font_pattern = re.compile(
    r"""url\(\s*["']?(?P<url>[^)"']+\.woff2(?:\?[^)"']*)?)["']?\s*\)""",
    re.I,
)

def inline_css_link(match):
    global css_count
    css_path = asset_path(match.group("href"), dist)
    if not css_path.is_file():
        raise SystemExit(f"Stylesheet not found: {css_path}")
    css = css_path.read_text(encoding="utf-8")
    def inline_font(font_match):
        font_url = font_match.group("url")
        if font_url.startswith(("data:", "http://", "https://")):
            return font_match.group(0)
        font_path = asset_path(font_url, css_path.parent)
        if not font_path.is_file():
            print(f"WARNING: font not found for inline: {font_url}", file=sys.stderr)
            return font_match.group(0)
        encoded = base64.b64encode(font_path.read_bytes()).decode("ascii")
        return f'url("data:font/woff2;base64,{encoded}")'
    css = font_pattern.sub(inline_font, css)
    css = re.sub(r"</style", r"<\/style", css, flags=re.I)
    css_count += 1
    return '<style>\n' + css + '\n</style>'

html = link_re.sub(inline_css_link, html)
if css_count != 1:
    raise SystemExit(f"Expected exactly one external stylesheet, inlined {css_count}")
if re.search(r'<script\b[^>]*\bsrc=', html, re.I):
    raise SystemExit("External script requests remain in index.html")
if re.search(r'<script\b[^>]*\btype=["\']module["\']', html, re.I):
    raise SystemExit("Module script remains in inline-asset build")
if re.search(r"""<link\b(?=[^>]*\brel=["']stylesheet["'])""", html, re.I):
    raise SystemExit("External stylesheet requests remain in index.html")

index_file.write_text(html, encoding="utf-8")
print(f"Inlined UI assets into {index_file} ({index_file.stat().st_size} bytes)")
''', encoding="utf-8")

build_ui = root / "scripts/build-ui.sh"
build_script = build_ui.read_text(encoding="utf-8")
if "inline_webui_assets.py" not in build_script:
    if "npm run build\n" not in build_script:
        raise SystemExit("Could not find npm build command in scripts/build-ui.sh")
    build_script = build_script.replace(
        "npm run build\n",
        "npm run build\npython3 ../scripts/inline_webui_assets.py dist\n",
        1,
    )
    build_ui.write_text(build_script, encoding="utf-8")


# Fix the actual UI interactions and header layout while preserving the approved theme.
app_path = root / "ui/src/App.tsx"
app = app_path.read_text()
old_import = 'import { useEffect, useMemo, useState } from "react";'
new_import = 'import { useEffect, useMemo, useRef, useState } from "react";'
if old_import in app:
    app = app.replace(old_import, new_import, 1)
elif new_import not in app:
    raise SystemExit("Could not locate React imports in App.tsx")

state_marker = '  const [heldIdx, setHeldIdx] = useState(0);\n  const applyPreset = (i: number) => {'
state_replacement = '''  const [heldIdx, setHeldIdx] = useState(0);
  const [presetOpen, setPresetOpen] = useState(false);
  const presetRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const closeOnOutside = (event: Event) => {
      if (!presetRef.current?.contains(event.target as Node)) setPresetOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPresetOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("touchstart", closeOnOutside, { passive: true });
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("touchstart", closeOnOutside);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  const applyPreset = (i: number) => {'''
if state_marker in app:
    app = app.replace(state_marker, state_replacement, 1)
elif "const [presetOpen, setPresetOpen]" not in app:
    raise SystemExit("Could not locate preset state insertion point in App.tsx")

old_preset = '''        <div className="preset">
          <button id="prev" title="Previous preset" onClick={() => applyPreset(stepBase - 1)}>
            ‹
          </button>
          <div className="name" id="preset-name">
            {presetName}
          </div>
          <button id="next" title="Next preset" onClick={() => applyPreset(stepBase + 1)}>
            ›
          </button>
        </div>'''
new_preset = '''        <div className={"preset" + (presetOpen ? " open" : "")} ref={presetRef}>
          <button type="button" id="prev" title="Previous preset" aria-label="Previous preset" onClick={() => applyPreset(stepBase - 1)}>
            ‹
          </button>
          <button
            type="button"
            className="name"
            id="preset-name"
            title="Choose preset"
            aria-haspopup="menu"
            aria-expanded={presetOpen}
            onClick={() => setPresetOpen((open) => !open)}
          >
            <span>{presetName}</span><span className="preset-caret" aria-hidden="true">▾</span>
          </button>
          <button type="button" id="next" title="Next preset" aria-label="Next preset" onClick={() => applyPreset(stepBase + 1)}>
            ›
          </button>
          {presetOpen && (
            <div className="preset-menu" role="menu" aria-label="Presets">
              {PRESETS.map(([name], i) => (
                <button
                  type="button"
                  role="menuitemradio"
                  aria-checked={i === matchedIdx}
                  className={i === matchedIdx ? "selected" : ""}
                  key={name + i}
                  onClick={() => {
                    applyPreset(i);
                    setPresetOpen(false);
                  }}
                >
                  <span>{name}</span>{i === matchedIdx && <span className="preset-check" aria-hidden="true">✓</span>}
                </button>
              ))}
            </div>
          )}
        </div>'''
if old_preset in app:
    app = app.replace(old_preset, new_preset, 1)
elif "className=\"preset-menu\"" not in app:
    raise SystemExit("Could not locate preset markup in App.tsx")

old_power = '''          <button id="power" title="Bypass" onClick={() => bypassToggle.set(!bypassed)}>'''
new_power = '''          <button
            type="button"
            id="power"
            title={bypassed ? "Turn processing on" : "Bypass processing"}
            aria-label={bypassed ? "Turn processing on" : "Bypass processing"}
            aria-pressed={bypassed}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              bypassToggle.set(!bypassed);
            }}
          >'''
if old_power in app:
    app = app.replace(old_power, new_power, 1)
elif 'aria-pressed={bypassed}' not in app:
    raise SystemExit("Could not locate power button markup in App.tsx")
app_path.write_text(app)

# Legacy WKWebView: knob drags use window-level mouse/touch listeners rather than
# relying on setPointerCapture on SVG descendants, which varied across WebKit.
knob_path = root / "ui/src/Knob.tsx"
knob = knob_path.read_text()
knob = knob.replace(
    'const drag = useRef({ startY: 0, startVal: 0 });',
    'const drag = useRef({ startY: 0, startVal: 0, active: false });',
    1
)
old_handlers = '''  const onPointerDown = (e: React.PointerEvent) => {
    drag.current = { startY: e.clientY, startVal: value };
    (e.target as Element).setPointerCapture(e.pointerId);
    param.dragStarted();
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!(e.target as Element).hasPointerCapture?.(e.pointerId)) return;
    const fine = e.shiftKey;
    const px = fine ? 900 : 220; // pixels for full sweep
    // Drag in knob space, not in value space, so the two halves of a centred
    // knob each get half the travel. Identical to before for linear knobs.
    const moved = toNorm(drag.current.startVal) + (drag.current.startY - e.clientY) / px;
    set(fromNorm(Math.min(1, Math.max(0, moved))), fine);
  };
  const onPointerUp = (e: React.PointerEvent) => {
    (e.target as Element).releasePointerCapture?.(e.pointerId);
    param.dragEnded();
  };
  const onDoubleClick = () => set(spec.def, false);'''
new_handlers = '''  const onMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0 || drag.current.active) return;
    e.preventDefault();
    drag.current = { startY: e.clientY, startVal: value, active: true };
    param.dragStarted();
    const onMove = (event: MouseEvent) => {
      if (!drag.current.active) return;
      event.preventDefault();
      const fine = event.shiftKey;
      const px = fine ? 900 : 160;
      const moved = toNorm(drag.current.startVal) + (drag.current.startY - event.clientY) / px;
      set(fromNorm(Math.min(1, Math.max(0, moved))), fine);
    };
    const finish = () => {
      if (!drag.current.active) return;
      drag.current.active = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", finish);
      window.removeEventListener("blur", finish);
      param.dragEnded();
    };
    window.addEventListener("mousemove", onMove, { passive: false });
    window.addEventListener("mouseup", finish);
    window.addEventListener("blur", finish);
  };
  const onTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
    const first = e.changedTouches.item(0);
    if (!first || drag.current.active) return;
    e.preventDefault();
    drag.current = { startY: first.clientY, startVal: value, active: true };
    const touchId = first.identifier;
    param.dragStarted();
    const onMove = (event: TouchEvent) => {
      if (!drag.current.active) return;
      for (let i = 0; i < event.touches.length; i++) {
        const touch = event.touches.item(i);
        if (!touch || touch.identifier !== touchId) continue;
        event.preventDefault();
        const moved = toNorm(drag.current.startVal) + (drag.current.startY - touch.clientY) / 160;
        set(fromNorm(Math.min(1, Math.max(0, moved))), false);
        break;
      }
    };
    const finish = (event: TouchEvent) => {
      for (let i = 0; i < event.changedTouches.length; i++) {
        const touch = event.changedTouches.item(i);
        if (touch && touch.identifier === touchId) {
          if (!drag.current.active) return;
          drag.current.active = false;
          window.removeEventListener("touchmove", onMove);
          window.removeEventListener("touchend", finish);
          window.removeEventListener("touchcancel", finish);
          param.dragEnded();
          return;
        }
      }
    };
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("touchend", finish);
    window.addEventListener("touchcancel", finish);
  };
  const onDoubleClick = () => set(spec.def, false);'''
if old_handlers in knob:
    knob = knob.replace(old_handlers, new_handlers, 1)
elif "const onMouseDown = (e: React.MouseEvent<HTMLDivElement>)" not in knob:
    raise SystemExit("Could not locate knob pointer-handler block in Knob.tsx")
knob = knob.replace(
    '''      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onDoubleClick={onDoubleClick}''',
    '''      onMouseDown={onMouseDown}
      onTouchStart={onTouchStart}
      onDoubleClick={onDoubleClick}''',
    1
)
if "onPointerMove={onPointerMove}" in knob:
    raise SystemExit("Knob pointer event props were not fully replaced")
knob_path.write_text(knob)

# Keep the compact header mix percentage highlighted for the entire drag
# gesture, then restore the idle grey state on mouse/touch release.
knob = knob_path.read_text()
value_state = '  const [value, setValue] = useState(param.getScaled());'
drag_state = value_state + '\n  const [isDragging, setIsDragging] = useState(false);'
if 'const [isDragging, setIsDragging] = useState(false);' not in knob:
    if value_state not in knob:
        raise SystemExit("Could not locate knob value state for drag highlighting")
    knob = knob.replace(value_state, drag_state, 1)

mouse_start = 'drag.current = { startY: e.clientY, startVal: value, active: true };\n    param.dragStarted();'
if mouse_start in knob:
    knob = knob.replace(mouse_start, 'drag.current = { startY: e.clientY, startVal: value, active: true };\n    setIsDragging(true);\n    param.dragStarted();', 1)
elif 'setIsDragging(true);' not in knob:
    raise SystemExit("Could not locate mouse drag start for highlight state")

touch_start = 'drag.current = { startY: first.clientY, startVal: value, active: true };\n    const touchId = first.identifier;'
if touch_start in knob:
    knob = knob.replace(touch_start, 'drag.current = { startY: first.clientY, startVal: value, active: true };\n    setIsDragging(true);\n    const touchId = first.identifier;', 1)
elif knob.count("setIsDragging(true);") < 2:
    raise SystemExit("Could not locate touch drag start for highlight state")

mouse_finish = 'drag.current.active = false;\n      window.removeEventListener("mousemove", onMove);'
if mouse_finish in knob:
    knob = knob.replace(mouse_finish, 'drag.current.active = false;\n      setIsDragging(false);\n      window.removeEventListener("mousemove", onMove);', 1)
elif 'setIsDragging(false);' not in knob:
    raise SystemExit("Could not locate mouse drag finish for highlight state")

touch_finish = 'drag.current.active = false;\n          window.removeEventListener("touchmove", onMove);'
if touch_finish in knob:
    knob = knob.replace(touch_finish, 'drag.current.active = false;\n          setIsDragging(false);\n          window.removeEventListener("touchmove", onMove);', 1)
elif knob.count("setIsDragging(false);") < 2:
    raise SystemExit("Could not locate touch drag finish for highlight state")

old_class = '      className="knob-unit"\n      id={spec.label}'
new_class = '      className={"knob-unit" + (isDragging ? " dragging" : "")}\n      id={spec.label}'
if old_class in knob:
    knob = knob.replace(old_class, new_class, 1)
elif 'className={"knob-unit" + (isDragging ? " dragging" : "")}' not in knob:
    raise SystemExit("Could not locate knob root class for drag highlighting")
knob_path.write_text(knob)

# CSS overrides keep the fixed design canvas but prevent flex shrink/overlap.
css_path = root / "ui/src/App.css"
css = css_path.read_text()
if "Mojave WebKit refinements: non-overlapping header" not in css:
    css += r'''
/* Mojave WebKit refinements: non-overlapping header, accessible preset menu,
   and crisp labels without changing the approved dark/accent visual language. */
#plugin {
  -webkit-font-smoothing: antialiased;
  text-rendering: geometricPrecision;
}
header {
  display: grid;
  grid-template-columns: max-content minmax(150px, 1fr) max-content;
  column-gap: 12px;
  align-items: center;
  padding: 11px 16px 10px;
  z-index: 5;
}
.wordmark { flex: 0 0 auto; font-size: 20px; letter-spacing: -0.035em; }
.preset {
  position: relative;
  width: 100%;
  max-width: 172px;
  min-width: 0;
  justify-self: center;
  z-index: 6;
}
.preset > button#prev, .preset > button#next {
  flex: 0 0 22px;
  width: 22px;
  padding: 2px 0;
  line-height: 1.1;
}
.preset .name {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  flex: 1 1 auto;
  width: 0;
  min-width: 0;
  overflow: hidden;
  padding: 3px 2px;
  border: 0;
  background: transparent;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 700 10px/1.2 "Martian Mono", monospace;
  letter-spacing: 0.13em;
  cursor: pointer;
}
.preset .name > span:first-child {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.preset-caret { flex: 0 0 auto; font-size: 9px; letter-spacing: 0; color: var(--dim); }
.preset .name:hover, .preset .name[aria-expanded="true"] { color: var(--accent); }
.preset-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: -1px;
  right: -1px;
  z-index: 20;
  max-height: 220px;
  overflow-y: auto;
  padding: 4px;
  background: #0A0908;
  border: 1px solid rgba(236, 231, 222, 0.22);
  border-radius: 6px;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.75), inset 0 1px 0 rgba(255, 255, 255, 0.03);
}
.preset-menu button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 9px;
  border: 1px solid transparent;
  border-radius: 3px;
  color: var(--dim);
  background: transparent;
  font: 700 9px/1.3 "Martian Mono", monospace;
  letter-spacing: 0.08em;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
}
.preset-menu button:hover, .preset-menu button:focus-visible {
  color: var(--text-hi);
  background: rgba(236, 231, 222, 0.06);
  outline: none;
}
.preset-menu button.selected {
  color: var(--accent);
  background: rgba(0, 253, 220, 0.07);
  border-color: rgba(0, 253, 220, 0.28);
}
.preset-check { color: var(--accent); }
.header-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: max-content;
  flex: 0 0 auto;
}
.header-meta {
  flex: 0 0 auto;
  font-size: 8px;
  letter-spacing: 0.10em;
  line-height: 1.2;
}
.header-mix { flex: 0 0 auto; }
.header-mix .knob-unit {
  width: auto;
  flex: 0 0 auto;
  display: flex;
  flex-direction: row-reverse;
  gap: 4px;
  white-space: nowrap;
}
.header-mix .knob-label { font-size: 8px; letter-spacing: 0.10em; }
.header-mix .knob-value { min-width: 28px; font-size: 8px; letter-spacing: 0.04em; }
#power {
  box-sizing: border-box;
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  padding: 0;
  margin: 0;
  line-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
}
#power svg {
  display: block;
  flex: 0 0 12px;
  width: 12px;
  height: 12px;
  margin: 0;
  transform: translate(0, 0);
  pointer-events: none;
}
.knob-unit { touch-action: none; -webkit-user-select: none; user-select: none; }
'''
    css_path.write_text(css)

# Additional spacing/drag-state refinements requested after the Mojave UI became functional.
css_path = root / "ui/src/App.css"
css = css_path.read_text()
refinement_marker = "Mojave refinement 2: stable mix drag highlight and separated labels"
if refinement_marker not in css:
    css += r'''
/* Mojave refinement 2: stable mix drag highlight and separated labels. */
/* The mix value lights only while actively dragging; hover alone does not latch it. */
.header-right {
  gap: 12px;
}
.header-meta {
  margin-right: 4px;
  flex-shrink: 0;
}
.header-mix .knob-unit {
  gap: 6px;
}
.header-mix .knob-unit:hover:not(.dragging) .knob-value {
  color: var(--dim);
}
.header-mix .knob-unit.dragging .knob-value {
  color: var(--accent);
}
/* Give the narrow input/output labels independent horizontal space. */
.meter-unit {
  width: 100%;
  min-width: 0;
}
.meter-pair {
  width: 100%;
  justify-content: center;
  gap: 14px;
}
.meter-col {
  flex: 0 0 auto;
}
.meter-label {
  white-space: nowrap;
  font-size: 8px;
  letter-spacing: 0.10em;
}
/* Separate all four control blocks and make active drag state unmistakable. */
.knob-col {
  gap: 20px;
}
.stack {
  gap: 14px;
}
.stack #monolow {
  margin-top: 30px;
}
.knob-unit.dragging .knob-label,
.knob-unit.dragging .knob-value {
  color: var(--accent) !important;
}
.header-mix .knob-unit.dragging .knob-label,
.header-mix .knob-unit.dragging .knob-value {
  color: var(--accent) !important;
}
/* Allocate real width for the two meter captions instead of letting their glyphs collide. */
.meter-unit {
  width: 100%;
  min-width: 58px;
}
.meter-pair {
  width: 100%;
  gap: 18px;
  justify-content: center;
}
.meter-col {
  flex: 0 0 20px;
  min-width: 20px;
}
.meter-label {
  width: 100%;
  text-align: center;
  white-space: nowrap;
  letter-spacing: 0.08em;
}
'''
    css_path.write_text(css)

# Correct static font-face metadata: let Safari synthesize bold instead of loading a regular file as an exact 700/800 match.
fonts_path = root / "ui/src/fonts/fonts.css"
fonts = fonts_path.read_text()
fonts_new = re.sub(r'/\* Archivo (?:500|700|800) latin \*/\n@font-face \{.*?\n\}\n', '', fonts, flags=re.S)
if fonts_new != fonts:
    fonts_path.write_text(fonts_new)
print("Applied Mojave-compatible knob drag, preset dropdown, header layout, font and power-button fixes.")

print("Applied Mojave WebView diagnostics, safe ResizeObserver fallback, and Safari 14.1 build target.")
