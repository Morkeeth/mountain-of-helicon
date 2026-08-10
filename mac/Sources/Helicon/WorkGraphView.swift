import SwiftUI

/// Native read-only inspection of the exact same local Work Graph record as
/// the web dashboard. This view does not write SQLite or resolve outcomes.
struct WorkGraphView: View {
    @State private var response: WorkCardsResponse?
    @State private var attention: WorkAttentionResponse?
    @State private var selected: WorkTrace?
    @State private var error: String?
    private let api = HeliconAPI()

    var body: some View {
        ZStack {
            WashBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    RailLabel(text: "Agentic Work Graph")
                    if let error { Text("work graph unavailable — \(error)").font(.data(12)).foregroundStyle(Wash.muted) }
                    else if let response { content(response) }
                    else { Text("reading connected work records…").font(.data(12)).foregroundStyle(Wash.muted) }
                }
                .frame(maxWidth: 880, alignment: .leading).padding(30).frame(maxWidth: .infinity)
            }
        }
        .frame(minWidth: 820, minHeight: 680)
        .task { await load() }
    }

    private func load() async {
        do {
            async let cards = api.workCards()
            async let queue = api.workAttention()
            response = try await cards
            attention = try await queue
        } catch { self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription }
    }

    @ViewBuilder private func content(_ data: WorkCardsResponse) -> some View {
        Text("\(data.measurement.openCards) open · \(data.measurement.linkedRuns) linked runs · \(data.measurement.contextWithMemory) with memory")
            .font(.data(11)).foregroundStyle(Wash.muted)
        if let attention, !attention.attention.isEmpty {
            section("Attention") {
                ForEach(attention.attention.prefix(5)) { item in
                    Text("\(item.priority.uppercased()) · \(item.action.replacingOccurrences(of: "_", with: " ")) — \(item.reason)")
                        .font(.iface(12)).foregroundStyle(item.priority == "now" ? Wash.ink : Wash.muted).padding(.vertical, 2)
                }
            }
        }
        section("Work Cards") {
            ForEach(data.cards) { card in
                Button {
                    Task { await inspect(card.id) }
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(card.intent).font(.iface(15, .medium)).foregroundStyle(Wash.ink)
                        Text("\(card.outcome ?? "outcome pending") · \(card.model ?? "no run") · \(card.contextItems) context · \(card.evidenceCount) receipts")
                            .font(.data(10)).foregroundStyle(Wash.muted)
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(12)
                    .background(.white.opacity(0.65)).overlay(RoundedRectangle(cornerRadius: 8).stroke(Wash.line))
                }.buttonStyle(.plain)
            }
        }
        if let selected { trace(selected) }
    }

    private func inspect(_ id: String) async {
        do { selected = try await api.workTrace(id) }
        catch { self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription }
    }

    @ViewBuilder private func trace(_ trace: WorkTrace) -> some View {
        section("Connected record · \(trace.workCard.outcome ?? "outcome pending")") {
            Text(trace.workCard.intent).font(.iface(14)).foregroundStyle(Wash.ink)
            Text("\(trace.workCard.beneficiary) · \(trace.taskRun?.model ?? "no model") / \(trace.taskRun?.harness ?? "no harness")")
                .font(.data(10)).foregroundStyle(Wash.muted)
            Text("Context: \(trace.contextPacket?.includedMemoryItems.count ?? 0) memory items · \(trace.contextPacket?.tokenEstimate ?? 0) tokens")
                .font(.data(10)).foregroundStyle(Wash.muted)
            Text("Skills: \(trace.skills.isEmpty ? "none declared" : trace.skills.map { skill in trace.skillReviews.contains(where: { $0.skillVersion == skill }) ? "reviewed \(skill)" : "needs review \(skill)" }.joined(separator: " · "))")
                .font(.data(10)).foregroundStyle(Wash.muted)
            Text("Outcome receipts: \(trace.outcomeEvidence.count) · execution receipts: \(trace.executionEvidence.count)")
                .font(.data(10)).foregroundStyle(Wash.muted)
            ForEach(trace.timeline.suffix(8)) { event in
                Text("\(String(event.at.prefix(16)).replacingOccurrences(of: "T", with: " ")) · \(event.label)")
                    .font(.data(10)).foregroundStyle(Wash.muted)
            }
        }
    }

    @ViewBuilder private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased()).font(.data(10, .semibold)).foregroundStyle(Wash.muted)
            content()
        }.padding(.vertical, 6)
    }
}
