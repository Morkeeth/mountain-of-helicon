import SwiftUI
import AppKit
import WebKit

/// The start card: where your context is, and its state. One page, served by
/// `helicon serve` at /start. The browser shows the same page, so the dashboard
/// exists once and the app cannot drift from the web view.
struct StartLine: Decodable {
    let line: String
    let toFix: Int

    enum CodingKeys: String, CodingKey {
        case line
        case toFix = "to_fix"
    }
}

extension HeliconAPI {
    /// The one line the menu bar shows, and how many things need a person.
    func startLine() async throws -> StartLine {
        let (data, response) = try await URLSession.shared.data(from: base.appendingPathComponent("/api/start"))
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
        return try JSONDecoder().decode(StartLine.self, from: data)
    }
}

/// The page itself. No navigation away from the local address is allowed.
private struct StartPage: NSViewRepresentable {
    let url: URL

    func makeCoordinator() -> Guard { Guard(host: url.host) }

    func makeNSView(context: Context) -> WKWebView {
        let view = WKWebView()
        view.navigationDelegate = context.coordinator
        view.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {}

    final class Guard: NSObject, WKNavigationDelegate {
        let host: String?
        init(host: String?) { self.host = host }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            decisionHandler(action.request.url?.host == host ? .allow : .cancel)
        }
    }
}

/// The start window, owned by AppKit so the menu bar panel can open it through
/// one path, same pattern as Cockpit.
@MainActor
final class StartWindow {
    static let shared = StartWindow()
    private var window: NSWindow?

    func show() {
        let url = HeliconAPI().base.appendingPathComponent("/start")
        // Rebuilt on every open: the page is a reading, and an old one is worse
        // than none.
        let host = NSHostingController(rootView: StartPage(url: url))
        if let window {
            window.contentViewController = host
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let w = NSWindow(contentViewController: host)
        w.title = "Helicon"
        w.setContentSize(NSSize(width: 1120, height: 820))
        w.styleMask = [.titled, .closable, .miniaturizable, .resizable]
        w.backgroundColor = NSColor(srgbRed: 0xED/255.0, green: 0xF1/255.0, blue: 0xF6/255.0, alpha: 1)
        w.isReleasedWhenClosed = false
        w.center()
        window = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

/// The row at the top of the menu bar panel: the state of the setup in one line.
struct StartRow: View {
    @State private var line: String = "Reading your setup…"
    @State private var toFix: Int = 0

    var body: some View {
        Button {
            StartWindow.shared.show()
        } label: {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Your setup")
                        .font(.iface(9.5))
                        .foregroundStyle(Wash.muted)
                    Text(line)
                        .font(.iface(11.5))
                        .foregroundStyle(Wash.ink)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 9))
                    .foregroundStyle(Wash.faint)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .task { await load() }
    }

    private func load() async {
        do {
            let reading = try await HeliconAPI().startLine()
            line = reading.line
            toFix = reading.toFix
        } catch {
            line = "Could not read your setup. Is Helicon running?"
        }
    }
}
