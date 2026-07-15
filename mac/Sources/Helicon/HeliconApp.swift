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

final class AppDelegate: NSObject, NSApplicationDelegate {
    /// `--queue` opens the cockpit straight away (demo + headless verification).
    /// Without it the app is menu-bar-only and the window is opened from the
    /// sentry, which is the everyday shape.
    static var opensQueueAtLaunch: Bool {
        CommandLine.arguments.contains("--queue")
    }

    // Menu-bar-first: no Dock icon until a window is opened. Set in code because
    // a SwiftPM executable has no Info.plist to carry LSUIElement.
    func applicationDidFinishLaunching(_ notification: Notification) {
        if Self.opensQueueAtLaunch {
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
                || env["HELICON_VERDICT"] != nil else { return }

        // HELICON_VERDICT=<decision> fires one real verdict through the app's own
        // path (Store.confirm -> POST /api/audit/confirm) so the write can be
        // verified headlessly. Point HELICON_API at a sandbox instance first.
        if let verdict = env["HELICON_VERDICT"] {
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                Task { @MainActor in
                    guard let f = Store.shared.selected else {
                        Self.note("verdict: nothing selected"); return
                    }
                    Self.note("verdict: firing '\(verdict)' on \(f.id) [\(f.kind)] — queue was \(Store.shared.openCount)")
                    await Store.shared.confirm(f, decision: verdict)
                    Self.note("verdict: queue now \(Store.shared.openCount), note=\(Store.shared.actionError ?? "none")")
                }
            }
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 7) {
            let windows = NSApp.windows.filter { $0.isVisible }
            for w in windows {
                Self.note("window '\(w.title)' \(Int(w.frame.width))x\(Int(w.frame.height)) visible=\(w.isVisible)")
            }
            if let path = env["HELICON_SHOT"] {
                Self.capture(windows: windows, to: path)
                NSApp.terminate(nil)
            }
        }
    }

    private static func capture(windows: [NSWindow], to path: String) {
        guard let win = windows.first(where: { $0.frame.width > 500 }),
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
