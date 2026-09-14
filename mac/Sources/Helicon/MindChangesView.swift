import SwiftUI
import AppKit

// WHAT CHANGED MY MIND? for the past week, read from the same local route the
// dashboard uses (/api/mind-changes), with the server's own build identity.
// The app never computes an answer itself: a stale or foreign server shows as
// an error line, not as an empty week.

struct MindChanges: Decodable {
    struct Passage: Decodable { let file: String; let line: Int; let date: String; let text: String }
    struct Item: Decodable {
        let topic: String
        let instruction: Passage?
        let current: [Passage]
        let changed_in_window: Bool
    }
    struct Gap: Decodable { let reason: String }
    struct ServedBy: Decodable {
        let repo: String; let branch: String; let head: String; let dirty: Bool
        let module_sha256: String; let pid: Int; let process_started: String
    }
    let since: String
    let as_of: String
    let items: [Item]
    let gap: Gap?
    let redactions: [String: Int]
    let served_by: ServedBy
}

extension HeliconAPI {
    /// GET /api/mind-changes, loopback only, with the explicit local header the
    /// route requires. An HTML reply (an older server's SPA fallback) is refused.
    func mindChanges(window: Int = 7) async throws -> MindChanges {
        var comps = URLComponents(url: base.appendingPathComponent("/api/mind-changes"),
                                  resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "window", value: String(window))]
        var req = URLRequest(url: comps.url!)
        req.setValue("1", forHTTPHeaderField: "X-Helicon-Local")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.transport("no HTTP response") }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        guard (http.value(forHTTPHeaderField: "Content-Type") ?? "").contains("json") else {
            throw APIError.transport("\(base.absoluteString) has no /api/mind-changes route. It is running older code.")
        }
        return try JSONDecoder().decode(MindChanges.self, from: data)
    }
}

/// Where the menu bar item actually sits. MenuBarExtra gives no handle, so the
/// status window is found by class name and compared with the areas beside the
/// notch. Unknown stays unknown; it is never reported as visible.
@MainActor
enum StatusItemPlacement {
    static func describe() -> String? {
        guard let screen = NSScreen.screens.first(where: { $0.auxiliaryTopLeftArea != nil }) else { return nil }
        let win = NSApp.windows.first { String(describing: type(of: $0)).contains("StatusBarWindow") }
        guard let frame = win?.frame, frame.width > 0 else {
            return "Menu bar item position unknown: no status window found."
        }
        let left = screen.auxiliaryTopLeftArea ?? .zero, right = screen.auxiliaryTopRightArea ?? .zero
        let visible = left.contains(CGPoint(x: frame.midX, y: left.midY)) || right.contains(CGPoint(x: frame.midX, y: right.midY))
        if visible { return nil }
        return "The menu bar item is hidden under the camera notch (x=\(Int(frame.minX))pt). Hold Cmd and drag it right, quit other menu bar apps, or use this window and the Dock icon."
    }
}

struct MindChangesSection: View {
    private let api = HeliconAPI()
    @State private var result: MindChanges?
    @State private var error: String?
    @State private var placement: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("What changed my mind? · past week").font(.display(18, .regular)).foregroundStyle(Wash.ink)
            if let placement {
                Text(placement).font(.iface(11.5)).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let r = result {
                Text("served by \(r.served_by.repo) · \(r.served_by.branch)@\(r.served_by.head)\(r.served_by.dirty ? "+dirty" : "") · module \(r.served_by.module_sha256) · pid \(String(r.served_by.pid)) · via \(api.base.absoluteString)")
                    .font(.data(10)).foregroundStyle(Wash.muted).textSelection(.enabled)
                Text("window \(r.since) → \(r.as_of)\(r.redactions.isEmpty ? "" : " · redacted on screen: " + r.redactions.sorted { $0.key < $1.key }.map { "\($0.value) \($0.key)" }.joined(separator: ", "))")
                    .font(.data(10)).foregroundStyle(Wash.faint)
                if let gap = r.gap {
                    Text("Evidence gap: \(gap.reason)").font(.iface(12)).foregroundStyle(Wash.ink)
                }
                ForEach(Array(r.items.enumerated()), id: \.offset) { _, item in
                    VStack(alignment: .leading, spacing: 3) {
                        Text("\(item.current.first?.date ?? "") · \(item.topic.replacingOccurrences(of: "_", with: " ").replacingOccurrences(of: "-", with: " "))")
                            .font(.iface(12.5, .semibold)).foregroundStyle(Wash.ink)
                        Text(item.changed_in_window ? "overturned \(item.instruction?.date ?? "")" : "ruling, no earlier instruction found")
                            .font(.iface(11)).foregroundStyle(Wash.muted)
                        if let cur = item.current.first {
                            Text(String(cur.text.replacingOccurrences(of: "\n", with: " ").prefix(220)))
                                .font(.iface(11.5)).foregroundStyle(Wash.ink)
                                .fixedSize(horizontal: false, vertical: true)
                            Text("\(cur.file):\(cur.line)").font(.data(10)).foregroundStyle(Wash.faint)
                        }
                    }
                    .padding(.vertical, 4)
                }
            } else if let error {
                Text(error).font(.iface(12)).foregroundStyle(.red).textSelection(.enabled)
            } else {
                Text("Reading dated memory…").font(.iface(12)).foregroundStyle(Wash.muted)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: Wash.radius, style: .continuous)
            .fill(Wash.bone)
            .overlay(RoundedRectangle(cornerRadius: Wash.radius, style: .continuous)
                .strokeBorder(Wash.line, lineWidth: 0.5)))
        .task {
            do { result = try await api.mindChanges(); error = nil }
            catch { self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription }
            try? await Task.sleep(nanoseconds: 800_000_000)
            placement = StatusItemPlacement.describe()
            if let placement { FileHandle.standardError.write(("helicon: " + placement + "\n").data(using: .utf8)!) }
        }
    }
}
