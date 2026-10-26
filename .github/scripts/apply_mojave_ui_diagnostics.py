#!/usr/bin/env python3
"""Apply Mojave WebView diagnostics and safe UI fallbacks to a prepared TagoClip tree."""
from pathlib import Path
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

# Ensure the actual React root is a fresh native DOM element. The diagnostic
# log showed React #299 even though the HTML's "root" lookup later succeeded.
# Replacing the placeholder avoids handing React a stale/non-native container.
main_tsx = root / "ui/src/main.tsx"
main_source = main_tsx.read_text(encoding="utf-8")
old_mount = """createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)"""
new_mount = """// Create a fresh native container at startup. This avoids passing a stale or
// invalid container to ReactDOM.createRoot in the embedded macOS WebView.
const oldRoot = document.getElementById('root')
const mountRoot = document.createElement('div')
mountRoot.id = 'root'
if (oldRoot && oldRoot.parentNode)
  oldRoot.parentNode.replaceChild(mountRoot, oldRoot)
else
  document.body.appendChild(mountRoot)

console.error('[TagoClip mount probe] originalRoot=' + !!oldRoot
  + '; originalNodeType=' + (oldRoot && oldRoot.nodeType)
  + '; newNodeType=' + mountRoot.nodeType
  + '; bodyNodeType=' + (document.body && document.body.nodeType))

createRoot(mountRoot).render(
  <StrictMode>
    <App />
  </StrictMode>,
)"""
if old_mount not in main_source:
    if "createRoot(mountRoot).render(" not in main_source:
        raise SystemExit("Could not locate original React mount call in ui/src/main.tsx")
else:
    main_source = main_source.replace(old_mount, new_mount)
    main_tsx.write_text(main_source, encoding="utf-8")

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

def inline_script(match):
    global script_count
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
    return '<script>\n' + js + '\n</script>'

html = script_re.sub(inline_script, html)
if script_count != 1:
    raise SystemExit(f"Expected exactly one external module script, inlined {script_count}")

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

print("Applied Mojave WebView diagnostics, safe ResizeObserver fallback, and Safari 14.1 build target.")
