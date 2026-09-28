import SwiftUI

/// A stable native entrance to the context that governed recent work. This is
/// intentionally smaller than ThisWeekView: it names the selected sources and
/// their limits, and it has a complete error state when the weekly computation
/// is slower than the native client's read budget.
struct ContextView: View {
    @EnvironmentObject private var store: Store
    private let api = HeliconAPI()
    @State private var data: ThisWeek?
    @State private var error: String?

    var body: some View {
        ZStack {
            WashBackground()
            VStack(alignment: .leading, spacing: 0) {
                header
                Divider().overlay(Wash.line)
                bodyContent
            }
        }
        .task { await load() }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                RailLabel(text: "What governed the work")
                Text("Context")
                    .font(.display(26, .semibold)).foregroundStyle(Wash.ink)
                Text("The recent source window, what it contained, and where the record is incomplete.")
                    .font(.iface(11.5)).foregroundStyle(Wash.muted)
            }
            Spacer()
            Button("Refresh") { Task { await load() } }
                .buttonStyle(.borderless)
                .font(.iface(10.5, .medium))
                .foregroundStyle(Wash.accent)
        }
        .padding(.leading, 28).padding(.trailing, 22)
        .padding(.top, 24).padding(.bottom, 18)
    }

    @ViewBuilder
    private var bodyContent: some View {
        if let data {
            context(data)
        } else if let error {
            unavailable(error)
        } else {
            ProgressView("Reading the weekly context window…")
                .font(.iface(11)).foregroundStyle(Wash.muted)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func context(_ data: ThisWeek) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                section("Window", title: data.week) {
                    let forks = data.setupHealth.identityForks.count
                    let contradictions = data.setupHealth.contradictions.count
                    let decisions = forks + contradictions
                    Text("\(decisions) decisions need attention: \(forks) identity forks and \(contradictions) contradictions.")
                        .font(.display(19, .medium)).foregroundStyle(Wash.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("The rest is a log, not a queue.")
                        .font(.iface(11.5, .medium)).foregroundStyle(Wash.muted)
                    Text("Read \(data.cached ? "from the saved weekly computation" : "from the live weekly computation")\(data.ranAt.map { " · " + Stamp.absolute($0) } ?? "")")
                        .font(.data(9.5)).foregroundStyle(Wash.faint)
                }

                HStack(alignment: .top, spacing: 14) {
                    section("Setup", title: "Where context disagrees") {
                        fact("Identity forks", "\(data.setupHealth.identityForks.count)", data.setupHealth.identityForks.source)
                        fact("Contradictions", "\(data.setupHealth.contradictions.count)", data.setupHealth.contradictions.source)
                        fact("Read-only fragments", "\(data.setupHealth.logFragments.count)", data.setupHealth.logFragments.source)
                    }
                    section("Learning", title: "What carried forward") {
                        if data.learningLedger.wired {
                            fact("Distilled this week", "\(data.learningLedger.distilledThisWeek ?? 0)", data.learningLedger.source ?? "source not named")
                            fact("Feedback lessons on file", "\(data.learningLedger.totalLessons ?? 0)", data.learningLedger.window ?? "window not named")
                        } else {
                            Text("Not wired: \(data.learningLedger.notWired?.joined(separator: " · ") ?? "memory directory unavailable")")
                                .font(.iface(11.5)).foregroundStyle(Wash.stale)
                        }
                    }
                }

                section("Observed work", title: "What the transcripts recorded") {
                    let review = data.transcriptReview
                    if review.wired {
                        HStack(spacing: 24) {
                            smallStat("Sessions", review.sessions)
                            smallStat("Human prompts", review.humanPrompts)
                            smallStat("Tool calls", review.toolCalls)
                            smallStat("Tool errors", review.toolErrors)
                        }
                        if let source = review.source {
                            Text(source).font(.data(9.5)).foregroundStyle(Wash.faint)
                        }
                    } else {
                        Text("Transcript review is not wired for this window.")
                            .font(.iface(11.5)).foregroundStyle(Wash.stale)
                    }
                }
            }
            .padding(26)
            .frame(maxWidth: 940, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
    }

    private func unavailable(_ reason: String) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 7) {
                RailLabel(text: "Weekly context unavailable")
                Text("The local record is \(store.connection.isLive ? "connected" : "not connected"), but this context window did not complete.")
                    .font(.display(20, .medium)).foregroundStyle(Wash.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(reason)
                    .font(.iface(11.5)).foregroundStyle(Wash.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12).fill(Wash.bone).overlay(RoundedRectangle(cornerRadius: 12).stroke(Wash.line)))

            VStack(alignment: .leading, spacing: 7) {
                RailLabel(text: "Exact boundary")
                Text("No empty dashboard or zero values are substituted. Project history, Rules, and Failures remain available from the same navigation because they use separate reads.")
                    .font(.iface(12)).foregroundStyle(Wash.ink70)
                Text("python3 -m uvicorn helicon.api.app:app --port 8420")
                    .font(.data(10)).foregroundStyle(Wash.slate).textSelection(.enabled)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12).fill(Wash.bone.opacity(0.78)).overlay(RoundedRectangle(cornerRadius: 12).stroke(Wash.line)))
        }
        .padding(28)
        .frame(maxWidth: 860, maxHeight: .infinity, alignment: .topLeading)
    }

    private func section<Content: View>(_ label: String, title: String,
                                        @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            RailLabel(text: label)
            Text(title).font(.iface(14, .semibold)).foregroundStyle(Wash.ink)
            content()
        }
        .padding(17)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Wash.bone.opacity(0.86)).overlay(RoundedRectangle(cornerRadius: 12).stroke(Wash.line)))
    }

    private func fact(_ label: String, _ value: String, _ source: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.iface(11.5)).foregroundStyle(Wash.ink70)
                Spacer()
                Text(value).font(.data(11, .semibold)).foregroundStyle(Wash.ink)
            }
            Text(source).font(.data(8.5)).foregroundStyle(Wash.faint).lineLimit(1)
        }
    }

    private func smallStat(_ label: String, _ value: Int?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value.map(String.init) ?? "—").font(.display(19, .medium)).foregroundStyle(Wash.ink)
            Text(label).font(.iface(9.5)).foregroundStyle(Wash.muted)
        }
    }

    private func load() async {
        data = nil
        error = nil
        do {
            data = try await api.thisWeek()
        } catch {
            self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }
}
