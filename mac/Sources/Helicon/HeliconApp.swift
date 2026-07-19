import SwiftUI
import AppKit

@main
struct HeliconApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        // The ambient sentry is the whole SwiftUI scene graph. `.window` style =
        // a real panel, not an NSMenu.
        //
        // The cockpit is deliberately NOT a SwiftUI `Window` scene: on macOS 14
        // a Window scene in a MenuBarExtra app does not present at launch and
        // can only be opened via `openWindow` from an existing view, which a
        // menu-bar-only app does not have until the panel is first opened.
        // Cockpit owns an NSWindow instead, so it can be opened from the panel,
        // from the launch flag, or from the Dock icon, all through one path.
        MenuBarExtra {
            SentryPanel()
                .environmentObject(Store.shared)
        } label: {
            SentryLabel()
                .environmentObject(Store.shared)
        }
        .menuBarExtraStyle(.window)
    }
}

/// The bar item. Kept as its own view so it observes the store and redraws the
/// glyph the moment the count or the critical state changes.
struct SentryLabel: View {
    @EnvironmentObject var store: Store

    var body: some View {
        Image(nsImage: sentryImage(count: store.openCount,
                                   critical: store.hasCritical,
                                   live: store.connection.isLive))
    }
}

/// The cockpit window, owned by AppKit so any entry point can open it.
@MainActor
final class Cockpit {
    static let shared = Cockpit()
    private var window: NSWindow?

    func show() {
        if let window {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let host = NSHostingController(rootView: QueueView().environmentObject(Store.shared))
        let w = NSWindow(contentViewController: host)
        w.title = "Review Queue"
        w.setContentSize(NSSize(width: 1180, height: 740))
        w.styleMask = [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView]
        w.titlebarAppearsTransparent = true
        w.backgroundColor = NSColor(srgbRed: 0xEC/255.0, green: 0xE4/255.0, blue: 0xD8/255.0, alpha: 1) // PAPER
        w.isReleasedWhenClosed = false
        w.center()
        window = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

/// The morning-brief window, owned by AppKit so the sentry or a launch flag can
/// open it. Same pattern as Cockpit — one path, many entry points.
@MainActor
final class BriefWindow {
    static let shared = BriefWindow()
    private var window: NSWindow?

    func show() {
        if let window {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let host = NSHostingController(rootView: BriefView())
        let w = NSWindow(contentViewController: host)
        w.title = "Morning Brief"
        w.setContentSize(NSSize(width: 780, height: 720))
        w.styleMask = [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView]
        w.titlebarAppearsTransparent = true
        w.backgroundColor = NSColor(srgbRed: 0xEC/255.0, green: 0xE4/255.0, blue: 0xD8/255.0, alpha: 1) // PAPER
        w.isReleasedWhenClosed = false
        w.center()
        window = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    /// `--queue` opens the cockpit straight away (demo + headless verification).
    /// Without it the app is menu-bar-only and the window is opened from the
    /// sentry, which is the everyday shape.
    static var opensQueueAtLaunch: Bool {
        CommandLine.arguments.contains("--queue")
    }

    /// `--brief` opens the morning brief straight away (demo + headless shot).
    static var opensBriefAtLaunch: Bool {
        CommandLine.arguments.contains("--brief")
    }

    // Menu-bar-first: no Dock icon until a window is opened. Set in code because
    // a SwiftPM executable has no Info.plist to carry LSUIElement.
    func applicationDidFinishLaunching(_ notification: Notification) {
        if Self.opensBriefAtLaunch {
            NSApp.setActivationPolicy(.regular)
            BriefWindow.shared.show()
        } else if Self.opensQueueAtLaunch {
            NSApp.setActivationPolicy(.regular)
            Cockpit.shared.show()
        } else {
            NSApp.setActivationPolicy(.accessory)
        }
        scheduleDiagnostics()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false   // the sentry outlives the window
    }

    /// Verification affordance: HELICON_SHOT=<path> renders the live cockpit
    /// window to a PNG from inside the process, then exits. Lets a headless
    /// shell prove what actually drew without Screen Recording permission.
    /// HELICON_DEBUG=1 additionally dumps the window inventory.
    private func scheduleDiagnostics() {
        let env = ProcessInfo.processInfo.environment
        guard env["HELICON_SHOT"] != nil || env["HELICON_DEBUG"] == "1"
                || env["HELICON_VERDICT"] != nil || env["HELICON_COMPOSE"] != nil else { return }

        // HELICON_COMPOSE=1 opens the ruling composer on the selected finding so
        // the money shot (the sheet, not just the queue) can be screenshotted
        // without injecting a keystroke. The composer prefills its reason from
        // HELICON_REASON in this mode so the "compiles to" preview is populated.
        if env["HELICON_COMPOSE"] != nil {
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                Task { @MainActor in
                    guard let f = Store.shared.selected else {
                        Self.note("compose: nothing selected"); return
                    }
                    Self.note("compose: opening ruling composer on \(f.id) [\(f.kind)]")
                    Store.shared.beginDismiss(f)
                }
            }
        }

        // HELICON_VERDICT=<decision> fires one real verdict through the app's own
        // path (Store.confirm -> POST /api/audit/confirm) so the write can be
        // verified headlessly. HELICON_REASON=<text> rides along on a dismissal
        // so the reason->precedent->law flow can be proven without injecting a
        // keystroke into the sheet. Point HELICON_API at a sandbox instance first.
        if let verdict = env["HELICON_VERDICT"] {
            let reason = env["HELICON_REASON"] ?? ""
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                Task { @MainActor in
                    guard let f = Store.shared.selected else {
                        Self.note("verdict: nothing selected"); return
                    }
                    Self.note("verdict: firing '\(verdict)' on \(f.id) [\(f.kind)]"
                              + (reason.isEmpty ? "" : " reason=\"\(reason)\"")
                              + " — queue was \(Store.shared.openCount)")
                    let res = await Store.shared.confirm(f, decision: verdict, notes: reason)
                    Self.note("verdict: queue now \(Store.shared.openCount), "
                              + "precedent=\(res?.precedent ?? false), "
                              + "note=\(Store.shared.actionError ?? "none")")
                }
            }
        }

        // Which faces actually drew. Type is the brand, and a missing font does
        // not throw — it silently falls back and the app quietly becomes a
        // different product. So the check is printed, not assumed.
        Self.note("font: brand faces registered = \(BrandFont.ready)")
        for family in [BrandFont.fraunces, BrandFont.bricolage, BrandFont.plexMono] {
            let resolved = NSFont(name: family, size: 13)?.fontName ?? "MISSING -> system fallback"
            Self.note("font: \(family) -> \(resolved)")
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 7) {
            let windows = NSApp.windows.filter { $0.isVisible }
            for w in windows {
                Self.note("window '\(w.title)' \(Int(w.frame.width))x\(Int(w.frame.height)) visible=\(w.isVisible)")
            }
            if let path = env["HELICON_SHOT"] {
                // When the composer is up, screenshot the sheet (the smaller
                // attached window) rather than the cockpit behind it.
                Self.capture(windows: windows, to: path,
                             preferSheet: env["HELICON_COMPOSE"] != nil)
                NSApp.terminate(nil)
            }
        }
    }

    private static func capture(windows: [NSWindow], to path: String, preferSheet: Bool = false) {
        let wide = windows.filter { $0.frame.width > 480 }
        let target = preferSheet
            ? wide.min(by: { $0.frame.width < $1.frame.width })
            : wide.max(by: { $0.frame.width < $1.frame.width })
        guard let win = target ?? windows.first(where: { $0.frame.width > 480 }),
              let view = win.contentView,
              let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
            note("capture: no cockpit window found")
            return
        }
        view.cacheDisplay(in: view.bounds, to: rep)
        guard let data = rep.representation(using: .png, properties: [:]) else {
            note("capture: PNG encode failed")
            return
        }
        do {
            try data.write(to: URL(fileURLWithPath: path))
            note("capture: wrote \(path) at \(rep.pixelsWide)x\(rep.pixelsHigh)")
        } catch {
            note("capture: \(error.localizedDescription)")
        }
    }

    static func note(_ msg: String) {
        FileHandle.standardError.write("[app] \(msg)\n".data(using: .utf8)!)
    }
}
