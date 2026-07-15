import Foundation
import SwiftUI

/// Connection is a first-class state, not a detail. When the API is down the
/// app says so and shows nothing else — there is no placeholder row anywhere in
/// this target, by project rule.
enum Connection: Equatable {
    case connecting
    case live(memories: Int)
    case down(String)

    var isLive: Bool { if case .live = self { return true }; return false }
}

@MainActor
final class Store: ObservableObject {
    /// One store for the process: the sentry and the cockpit are two views of
    /// the same queue, and a second poller would double the traffic and let the
    /// two surfaces disagree about the count.
    static let shared = Store()

    @Published private(set) var findings: [Finding] = []
    @Published private(set) var summary: FindingsSummary = .empty
    @Published private(set) var connection: Connection = .connecting
    @Published private(set) var lastRefresh: Date?
    @Published private(set) var busy: Set<String> = []
    @Published var actionError: String?
    @Published var selection: Finding.ID?

    private let api = HeliconAPI()
    private var poller: Task<Void, Never>?

    /// Poll cadence for the ambient sentry. Cheap call (19 rows), local socket.
    private let interval: Duration = .seconds(5)

    /// The sentry polls for the life of the PROCESS, so ownership lives here and
    /// not in a view. A `.task`-driven poller dies the moment SwiftUI tears the
    /// menu-bar panel down (observed: exactly one refresh, then silence), which
    /// would leave a stale count in the bar — the one thing the sentry must
    /// never do.
    init() {
        start()
    }

    /// Set HELICON_DEBUG=1 to trace the poll loop on stderr.
    private static let debug = ProcessInfo.processInfo.environment["HELICON_DEBUG"] == "1"

    private func log(_ msg: String) {
        guard Self.debug else { return }
        FileHandle.standardError.write("[sentry] \(msg)\n".data(using: .utf8)!)
    }

    var selected: Finding? {
        findings.first { $0.id == selection }
    }

    var selectedIndex: Int? {
        findings.firstIndex { $0.id == selection }
    }

    /// The sentry's two facts: how many need a ruling, and is any of them critical.
    var openCount: Int { summary.needsYou }
    var hasCritical: Bool { summary.critical > 0 }

    /// Queue grouped by drift class, in the order the server already ranked them.
    var groups: [(kind: String, items: [Finding])] {
        var order: [String] = []
        var byKind: [String: [Finding]] = [:]
        for f in findings {
            if byKind[f.kind] == nil { order.append(f.kind) }
            byKind[f.kind, default: []].append(f)
        }
        return order.map { ($0, byKind[$0] ?? []) }
    }

    func start() {
        guard poller == nil else { return }
        log("start")
        poller = Task { [weak self] in
            var tick = 0
            while true {
                guard let self else { return }
                tick += 1
                self.log("tick \(tick)")
                await self.refresh()
                do {
                    try await Task.sleep(for: self.interval)
                } catch {
                    // Only a genuine cancellation lands here (app teardown).
                    self.log("poller stopped: \(error)")
                    return
                }
            }
        }
    }

    func stop() {
        poller?.cancel()
        poller = nil
    }

    func refresh() async {
        do {
            let health = try await api.health()
            let res = try await api.findings(lane: "decision", limit: 100)
            findings = res.findings
            summary = res.summary
            connection = .live(memories: health.memories)
            lastRefresh = Date()
            // Keep a valid selection as the queue shrinks under triage.
            if selection == nil || !findings.contains(where: { $0.id == selection }) {
                // HELICON_SELECT=<finding id> focuses one finding at launch, so a
                // headless shell can screenshot a specific card.
                let wanted = ProcessInfo.processInfo.environment["HELICON_SELECT"]
                selection = findings.first { $0.id == wanted }?.id ?? findings.first?.id
            }
        } catch {
            connection = .down((error as? APIError)?.errorDescription
                               ?? error.localizedDescription)
            // Deliberately keep the last-known rows rather than inventing any;
            // the banner marks them as possibly stale.
        }
    }

    // MARK: - keyboard navigation

    func move(_ delta: Int) {
        guard !findings.isEmpty else { return }
        guard let i = selectedIndex else {
            selection = findings.first?.id
            return
        }
        let next = min(max(i + delta, 0), findings.count - 1)
        selection = findings[next].id
    }

    // MARK: - the real triage write

    /// POST /api/audit/confirm. On success the row leaves the pending queue, so
    /// the count decrements on the next refresh and focus auto-advances.
    func confirm(_ finding: Finding, decision: String) async {
        guard let auditID = finding.auditID else {
            actionError = finding.notConfirmableReason
            return
        }
        guard !busy.contains(finding.id) else { return }
        busy.insert(finding.id)
        defer { busy.remove(finding.id) }
        actionError = nil

        // Advance first so the loop feels like Linear's triage: the verdict is
        // the last thing you do with an item.
        let idx = selectedIndex
        do {
            let res = try await api.confirm(findingID: auditID, decision: decision)
            findings.removeAll { $0.id == finding.id }
            summary = FindingsSummary(
                total: max(summary.total - 1, 0),
                needsYou: max(summary.needsYou - 1, 0),
                ambient: summary.ambient,
                byKind: summary.byKind,
                bySeverity: summary.bySeverity.merging(
                    [finding.severity: max((summary.bySeverity[finding.severity] ?? 1) - 1, 0)]
                ) { _, new in new }
            )
            if let idx {
                selection = findings.indices.contains(idx)
                    ? findings[idx].id
                    : findings.last?.id
            }
            if !res.killedMemories.isEmpty {
                actionError = "Confirmed — also retired \(res.killedMemories.count) memories."
            }
            await refresh()
        } catch {
            actionError = "Write failed: "
                + ((error as? APIError)?.errorDescription ?? error.localizedDescription)
        }
    }
}
