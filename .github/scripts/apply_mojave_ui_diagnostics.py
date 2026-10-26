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
                               if (target && target !== window && (target.src || target.href)) {
                                   report("resource-error", "Failed to load resource", target.src || target.href);
                               } else {
                                   report("error", event && event.message, (event && event.filename ? event.filename : "")
                                       + ":" + (event && event.lineno ? event.lineno : 0)
                                       + ":" + (event && event.colno ? event.colno : 0));
                               }
                           }, true);
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

// Mojave ships Safari/WebKit 14.1.2. Target it without changing the UI design.
export default defineConfig({
  plugins: [react()],
  build: {
    target: 'safari14.1',
    cssTarget: 'safari14.1',
  },
})
""")
print("Applied Mojave WebView diagnostics, safe ResizeObserver fallback, and Safari 14.1 build target.")
