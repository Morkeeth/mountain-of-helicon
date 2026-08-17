import SwiftUI

/// THIS WEEK — the weekly knowledge-palace read, the one screen the app opens to.
///
/// It answers the ship question in a single read: is my agentic-engineering setup
/// any good THIS WEEK — computed from the real transcripts, memory, and git behind
/// `helicon serve`. Same object the web's ThisWeek surface renders (GET
/// /api/thisweek), ported 1:1.
///
/// The honesty bar this whole product exists to hold applies to its own front
/// page: every number prints the source that produced it, and a section that
/// cannot be probed renders "not wired" with the reason — never a faked zero. The
/// rot exam is deliberately NOT composed here (its R8 replay costs ~16s and would
/// turn one read into a 20s load); the web fetches /api/rot in parallel, and the
/// forks/contradictions shown here are the cheap db read.
struct ThisWeekView: View {
    private let api = HeliconAPI()
    @State private var data: ThisWeek?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let d = data {
                    header(d)
                    setupHealth(d.setupHealth)
                    overboard(d.overboard)
                    learningLedger(d.learningLedger)
                    transcriptReview(d.transcriptReview)
                    recommendations(d.recommendations)
                } else if let error {
                    errorRow(error)
                } else {
                    Text("Reading this week…")
                        .font(.iface(13)).foregroundStyle(Wash.muted)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.top, 60)
                }
            }
            .padding(28)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(WashBackground())
        .task { await load() }
    }

    // MARK: header + verdict

    private func header(_ d: ThisWeek) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            RailLabel(text: "This week · \(d.week)")
            Text(d.verdict)
                .font(.display(23, .medium))
                .foregroundStyle(Wash.ink)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                let open = d.setupHealth.identityForks.count + d.setupHealth.contradictions.count
                Text("\(open) to rule")
                    .font(.data(11, .medium))
                    .foregroundStyle(open > 0 ? Wash.stale : Wash.good)
                Text("·").foregroundStyle(Wash.faint)
                Text("read \(d.cached ? "from cache" : "live")\(d.ranAt.map { " · " + Stamp.absolute($0) } ?? "")")
                    .font(.iface(10)).foregroundStyle(Wash.muted)
                Button { Task { await load() } } label: {
                    Text("refresh").font(.iface(10)).foregroundStyle(Wash.accent)
                }.buttonStyle(.plain)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(card)
    }

    // MARK: 1 · setup health

    private func setupHealth(_ sh: ThisWeek.SetupHealth) -> some View {
        Section(n: "1", title: "Setup health",
                lede: "Where your stack disagrees with itself. These are the real things to rule this week.") {
            HStack(spacing: 10) {
                Stat(value: "\(sh.identityForks.count)", label: "Identity forks",
                     tone: sh.identityForks.count > 0 ? Wash.stale : Wash.good)
                Stat(value: "\(sh.contradictions.count)", label: "Contradictions",
                     tone: sh.contradictions.count > 0 ? Wash.stale : Wash.good)
                Stat(value: "\(sh.logFragments.count)", label: "Log fragments", tone: Wash.muted)
            }
            if sh.identityForks.count > 0 {
                Text("Same name, forked definition: ")
                    .font(.iface(12)).foregroundStyle(Wash.ink70)
                + Text(sh.identityForks.names.joined(separator: ", "))
                    .font(.iface(12, .semibold)).foregroundStyle(Wash.stale)
            }
            Text("Plus \(sh.logFragments.count) read-only memory fragments — a log, not decisions (kept out of the ruling queue).")
                .font(.iface(11)).foregroundStyle(Wash.muted)
                .fixedSize(horizontal: false, vertical: true)
            Source(sh.identityForks.source)
        }
    }

    // MARK: 2 · overboard

    private func overboard(_ ob: ThisWeek.Overboard) -> some View {
        Section(n: "2", title: "Overboard",
                lede: "What got over-captured this week: repos opened and left, and branches piling up as addresses that look live and are not.") {
            if ob.wired {
                HStack(spacing: 10) {
                    Stat(value: "\(ob.reposTouched ?? 0)", label: "Repos touched / \(ob.windowDays ?? 7)d", tone: Wash.ink)
                    Stat(value: "\(ob.oneDayRepos?.count ?? 0)", label: "Opened & left",
                         tone: (ob.oneDayRepos?.count ?? 0) > 0 ? Wash.stale : Wash.ink)
                    Stat(value: "\(ob.mergedNotDeleted ?? 0)", label: "Merged, not deleted", tone: Wash.ink)
                    Stat(value: "\(ob.abandonedBranches ?? 0)", label: "Abandoned branches",
                         tone: (ob.abandonedBranches ?? 0) > 0 ? Wash.stale : Wash.ink)
                }
                if let one = ob.oneDayRepos, !one.isEmpty {
                    (Text("One-day repos: ").font(.iface(11)).foregroundStyle(Wash.muted)
                     + Text(one.prefix(12).joined(separator: ", ")).font(.iface(11)).foregroundStyle(Wash.ink70))
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let root = ob.codeRoot {
                    Text("code root: \(root)").font(.data(9.5)).foregroundStyle(Wash.faint)
                }
                if let s = ob.source { Source(s) }
                notWired(ob.notWired)
            } else {
                Text("not wired: \(ob.reason ?? "source not configured")")
                    .font(.iface(11)).foregroundStyle(Wash.faint)
            }
        }
    }

    // MARK: 3 · learning ledger

    private func learningLedger(_ ll: ThisWeek.LearningLedger) -> some View {
        Section(n: "3", title: "Learning ledger",
                lede: "The lessons distilled to memory this week. A week with zero captured learnings is a capture gap, not a quiet win.") {
            if ll.wired {
                HStack(spacing: 10) {
                    Stat(value: "\(ll.distilledThisWeek ?? 0)", label: "Distilled · \(ll.window ?? "last 7 days")",
                         tone: (ll.distilledThisWeek ?? 0) > 0 ? Wash.good : Wash.stale)
                    Stat(value: "\(ll.totalLessons ?? 0)", label: "Total lessons on file", tone: Wash.ink)
                }
                if let files = ll.files, !files.isEmpty {
                    FlowChips(items: files.prefix(16).map {
                        $0.replacingOccurrences(of: "feedback_", with: "")
                          .replacingOccurrences(of: ".md", with: "")
                    })
                }
                if let s = ll.source { Source(s) }
                notWired(ll.notWired)
            } else {
                Text("not wired: no memory dir found")
                    .font(.iface(11)).foregroundStyle(Wash.faint)
            }
        }
    }

    // MARK: 4 · what you actually did

    private func transcriptReview(_ tx: ThisWeek.TranscriptReview) -> some View {
        Section(n: "4", title: "What you actually did",
                lede: "An honest week-in-review computed from your local transcripts. Aggregate only; nothing raw leaves your machine.") {
            HStack(spacing: 10) {
                Stat(value: "\(tx.sessions ?? 0)", label: "Sessions", tone: Wash.ink)
                Stat(value: "\(tx.humanPrompts ?? 0)", label: "Your prompts", tone: Wash.ink)
                Stat(value: "\(tx.toolCalls ?? 0)", label: "Tool calls", tone: Wash.ink)
                Stat(value: tx.toolSuccessPct.map { "\($0)%" } ?? "—", label: "Tool success",
                     tone: (tx.toolSuccessPct ?? 100) < 90 ? Wash.stale : Wash.good)
            }
            HStack(alignment: .top, spacing: 18) {
                VStack(alignment: .leading, spacing: 6) {
                    RailLabel(text: "most-used tools")
                    if let tools = tx.topTools, !tools.isEmpty {
                        Bar(items: Array(tools.prefix(6)))
                    } else {
                        Text("none").font(.iface(10.5)).foregroundStyle(Wash.faint)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .leading, spacing: 6) {
                    RailLabel(text: "where it failed (\(tx.toolErrors ?? 0) errors)")
                    if let errs = tx.errorsByTool, !errs.isEmpty {
                        Bar(items: Array(errs.prefix(6)))
                    } else {
                        Text("no tool errors").font(.iface(10.5)).foregroundStyle(Wash.good)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(alignment: .top, spacing: 10) {
                ReviewCol(title: "What you did", items: tx.did, tone: Wash.ink, empty: "—")
                ReviewCol(title: "What worked", items: tx.worked, tone: Wash.good, empty: "—")
                ReviewCol(title: "What to improve", items: tx.improve, tone: Wash.stale,
                          empty: "nothing recurring — clean week")
            }
            if let s = tx.source { Source(s) }
        }
    }

    // MARK: 5 · recommended next

    private func recommendations(_ recs: [ThisWeek.Recommendation]) -> some View {
        Section(n: "5", title: "Recommended next",
                lede: "The honest verdict — the highest-leverage moves for the setup this week, each tied to the signal it came from.") {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(recs.enumerated()), id: \.offset) { i, r in
                    HStack(alignment: .top, spacing: 10) {
                        Text(String(format: "%02d", i + 1))
                            .font(.data(11)).foregroundStyle(Wash.accent)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(r.text)
                                .font(.iface(12.5)).foregroundStyle(Wash.ink)
                                .fixedSize(horizontal: false, vertical: true)
                            Text("↳ \(r.basis)")
                                .font(.data(9.5)).foregroundStyle(Wash.faint)
                        }
                    }
                }
            }
        }
    }

    // MARK: shared pieces

    private var card: some ShapeStyle { Wash.bone }

    private func errorRow(_ e: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Could not read this week")
                .font(.display(17, .medium)).foregroundStyle(Wash.ink)
            Text(e).font(.iface(11.5)).foregroundStyle(Wash.muted)
                .fixedSize(horizontal: false, vertical: true)
            Text("python3 -m uvicorn helicon.api.app:app --port 8420")
                .font(.data(10)).foregroundStyle(Wash.slate).textSelection(.enabled)
        }
        .padding(20).frame(maxWidth: .infinity, alignment: .leading).background(card)
    }

    @ViewBuilder
    private func notWired(_ items: [String]?) -> some View {
        if let items, !items.isEmpty {
            Text("not wired: \(items.joined(separator: " · "))")
                .font(.iface(10.5)).foregroundStyle(Wash.faint)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func load() async {
        do {
            data = try await api.thisWeek()
            error = nil
            try? await api.recordSurfaceOpen("thisweek")
        } catch {
            self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }
}

// MARK: - section primitives

private struct Section<Content: View>: View {
    let n: String
    let title: String
    let lede: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(n).font(.data(11)).foregroundStyle(Wash.faint)
                Text(title).font(.display(18, .regular)).foregroundStyle(Wash.ink)
            }
            Text(lede).font(.iface(11.5)).foregroundStyle(Wash.muted)
                .fixedSize(horizontal: false, vertical: true)
            content
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: Wash.radius, style: .continuous)
            .fill(Wash.bone)
            .overlay(RoundedRectangle(cornerRadius: Wash.radius, style: .continuous)
                .strokeBorder(Wash.line, lineWidth: 0.5)))
    }
}

private struct Stat: View {
    let value: String
    let label: String
    var tone: Color = Wash.ink

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(value)
                .font(.display(24, .semibold)).foregroundStyle(tone)
                .monospacedDigit()
            Text(label.uppercased())
                .font(.iface(8.5, .semibold)).tracking(0.10 * 8.5)
                .foregroundStyle(Wash.muted).lineLimit(1)
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
            .fill(Wash.paperDeep.opacity(0.5))
            .overlay(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                .strokeBorder(Wash.line, lineWidth: 0.5)))
    }
}

private struct Bar: View {
    let items: [ThisWeek.NamedCount]

    var body: some View {
        let top = max(1, items.map(\.count).max() ?? 1)
        VStack(alignment: .leading, spacing: 5) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, i in
                HStack(spacing: 8) {
                    Text(i.name).font(.iface(10.5)).foregroundStyle(Wash.ink70)
                        .frame(width: 96, alignment: .leading).lineLimit(1)
                    GeometryReader { geo in
                        RoundedRectangle(cornerRadius: 2, style: .continuous)
                            .fill(Wash.accent)
                            .frame(width: max(3, geo.size.width * CGFloat(i.count) / CGFloat(top)))
                            .frame(maxHeight: .infinity, alignment: .center)
                    }
                    .frame(height: 6)
                    Text("\(i.count)").font(.data(9.5)).foregroundStyle(Wash.muted)
                        .frame(width: 34, alignment: .trailing)
                }
            }
        }
    }
}

private struct ReviewCol: View {
    let title: String
    let items: [String]?
    let tone: Color
    let empty: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            RailLabel(text: title)
            if let items, !items.isEmpty {
                ForEach(Array(items.enumerated()), id: \.offset) { _, t in
                    Text(t).font(.iface(11)).foregroundStyle(tone)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Text(empty).font(.iface(10.5)).foregroundStyle(Wash.faint)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
            .fill(Wash.paperDeep.opacity(0.5)))
    }
}

private struct FlowChips: View {
    let items: [String]
    var body: some View {
        // A simple wrapping row of memory-file chips.
        FlexWrap(items, spacing: 6) { name in
            Text(name)
                .font(.data(9.5)).foregroundStyle(Wash.muted)
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(Capsule().fill(Wash.paperDeep.opacity(0.6))
                    .overlay(Capsule().strokeBorder(Wash.line, lineWidth: 0.5)))
        }
    }
}

/// Minimal wrapping HStack — enough for a chip cloud, no external dependency.
private struct FlexWrap<Data: RandomAccessCollection, Content: View>: View where Data.Element: Hashable {
    let data: Data
    let spacing: CGFloat
    let content: (Data.Element) -> Content

    init(_ data: Data, spacing: CGFloat = 6, @ViewBuilder content: @escaping (Data.Element) -> Content) {
        self.data = data
        self.spacing = spacing
        self.content = content
    }

    var body: some View {
        var width: CGFloat = 0
        var rows: [[Data.Element]] = [[]]
        let cap: CGFloat = 520          // approximate wrap width; chips are short
        for el in data {
            let est = CGFloat(String(describing: el).count) * 6.5 + 20
            if width + est > cap, !(rows.last?.isEmpty ?? true) {
                rows.append([el]); width = est + spacing
            } else {
                rows[rows.count - 1].append(el); width += est + spacing
            }
        }
        return VStack(alignment: .leading, spacing: spacing) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(spacing: spacing) {
                    ForEach(row, id: \.self) { content($0) }
                }
            }
        }
    }
}

private struct Source: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text("↳ \(text)")
            .font(.data(9)).foregroundStyle(Wash.faint)
            .fixedSize(horizontal: false, vertical: true)
    }
}
