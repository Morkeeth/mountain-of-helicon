import SwiftUI

/// Project history is a read-only walk through the exact Work Graph record:
/// intent, frozen context, evidence, and dated events. It does not infer that a
/// receipt proved the intended outcome and it does not write the record.
struct ProjectHistoryView: View {
    @State private var response: WorkCardsResponse?
    @State private var attention: WorkAttentionResponse?
    @State private var selected: WorkTrace?
    @State private var error: String?
    @AppStorage("helicon.projectHistorySelection") private var selectedID = ""
    private let api = HeliconAPI()

    var body: some View {
        ZStack {
            WashBackground()
            VStack(spacing: 0) {
                header
                Divider().overlay(Wash.line)
                if let error {
                    unavailable(error)
                } else if let response {
                    history(response)
                } else {
                    ProgressView("Reading connected work records…")
                        .font(.iface(11)).foregroundStyle(Wash.muted)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .task { await load() }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                RailLabel(text: "Source-backed record")
                Text("Project history")
                    .font(.display(26, .semibold)).foregroundStyle(Wash.ink)
                Text("Open a run to see the context it received, the failure it met, and the evidence it left.")
                    .font(.iface(11.5)).foregroundStyle(Wash.muted)
            }
            Spacer()
            if let response {
                Text("\(response.measurement.linkedRuns) linked runs · \(response.measurement.evidenceReceipts) receipts")
                    .font(.data(9.5)).foregroundStyle(Wash.faint)
            }
        }
        .padding(.leading, 28).padding(.trailing, 22)
        .padding(.top, 24).padding(.bottom, 18)
    }

    private func load() async {
        do {
            async let cards = api.workCards()
            async let queue = api.workAttention()
            response = try await cards
            attention = try await queue
            if let data = response {
                let candidate = data.cards.contains { $0.id == selectedID }
                    ? selectedID : (data.cards.first?.id ?? "")
                if !candidate.isEmpty {
                    selectedID = candidate
                    await inspect(candidate)
                }
            }
        } catch { self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription }
    }

    private func history(_ data: WorkCardsResponse) -> some View {
        HStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(data.cards) { card in
                        Button {
                            selectedID = card.id
                            Task { await inspect(card.id) }
                        } label: {
                            historyCard(card, selected: selectedID == card.id)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(14)
            }
            .frame(width: 330)
            .background(Wash.bone.opacity(0.5))
            Divider().overlay(Wash.line)
            if let selected {
                trace(selected)
            } else {
                Text("Choose a recorded run.")
                    .font(.iface(12)).foregroundStyle(Wash.muted)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    private func historyCard(_ card: WorkCard, selected: Bool) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(card.openedAt.map { String($0.prefix(10)) } ?? "date unknown")
                    .font(.data(9.5)).foregroundStyle(Wash.faint)
                Spacer()
                Chip(text: card.status, color: card.status == "open" ? Wash.stale : Wash.good)
            }
            Text(card.intent)
                .font(.iface(12.5, selected ? .semibold : .medium))
                .foregroundStyle(Wash.ink)
                .fixedSize(horizontal: false, vertical: true)
            Text("\(card.model ?? "model unrecorded") · \(card.contextItems) context · \(card.evidenceCount) receipts")
                .font(.data(9.5)).foregroundStyle(Wash.muted)
        }
        .padding(13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(selected ? Wash.paperDeep : Wash.bone.opacity(0.84))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(selected ? Wash.slate.opacity(0.36) : Wash.line))
        )
    }

    private func inspect(_ id: String) async {
        do { selected = try await api.workTrace(id) }
        catch { self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription }
    }

    private func trace(_ trace: WorkTrace) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 7) {
                    RailLabel(text: trace.workCard.openedAt.map { "Opened " + String($0.prefix(16)).replacingOccurrences(of: "T", with: " ") } ?? "Dated record")
                    Text(trace.workCard.intent)
                        .font(.display(23, .medium)).foregroundStyle(Wash.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(trace.workCard.beneficiary)
                        .font(.iface(11.5)).foregroundStyle(Wash.muted)
                    Text("Outcome: \(trace.workCard.outcome ?? "not established")")
                        .font(.iface(11.5, .semibold))
                        .foregroundStyle(trace.workCard.outcome == nil ? Wash.stale : Wash.good)
                }

                historySection("Observable change") {
                    Text(trace.workCard.observableChange ?? "No observable change was recorded.")
                        .font(.iface(12.5)).foregroundStyle(Wash.ink)
                    if let contract = trace.workCard.evidenceContract {
                        receiptLabel("Evidence contract", contract)
                    }
                    if let kill = trace.workCard.killCondition {
                        receiptLabel("Failure condition", kill)
                    }
                }

                historySection("Run") {
                    Text("\(trace.taskRun?.model ?? "model unrecorded") · \(trace.taskRun?.harness ?? "harness unrecorded")")
                        .font(.data(10.5)).foregroundStyle(Wash.ink70)
                    receiptLabel("Verification", trace.taskRun?.verificationOutcome ?? "not recorded")
                    if let acceptance = trace.taskRun?.acceptanceTest {
                        receiptLabel("Acceptance test", acceptance)
                    }
                }

                historySection("Context") {
                    let memories = trace.contextPacket?.includedMemoryItems ?? []
                    Text("\(memories.count) memory items · \(trace.contextPacket?.tokenEstimate ?? 0) tokens")
                        .font(.data(10.5)).foregroundStyle(Wash.muted)
                    if memories.isEmpty {
                        Text("No memory items were frozen for this run.")
                            .font(.iface(11.5)).foregroundStyle(Wash.faint)
                    } else {
                        ForEach(memories.prefix(8), id: \.cubeID) { memory in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(memory.selectionReason ?? memory.cubeID)
                                    .font(.iface(11.5)).foregroundStyle(Wash.ink)
                                Text("\(memory.provenance ?? "source unrecorded") · \(memory.freshness ?? "date unrecorded")")
                                    .font(.data(9.5)).foregroundStyle(Wash.faint)
                            }
                        }
                    }
                }

                historySection("Evidence") {
                    let evidence = trace.outcomeEvidence + trace.executionEvidence
                    if evidence.isEmpty {
                        Text("No evidence receipt is linked. The outcome remains unproved.")
                            .font(.iface(11.5)).foregroundStyle(Wash.stale)
                    } else {
                        ForEach(Array(evidence.enumerated()), id: \.offset) { _, receipt in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Chip(text: receipt.kind, color: Wash.good)
                                    Text(receipt.observedAt.map { String($0.prefix(16)).replacingOccurrences(of: "T", with: " ") } ?? "date unrecorded")
                                        .font(.data(9.5)).foregroundStyle(Wash.faint)
                                }
                                if let note = receipt.note {
                                    Text(note).font(.iface(11.5)).foregroundStyle(Wash.ink)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                Text(receipt.reference).font(.data(9.5)).foregroundStyle(Wash.muted)
                            }
                            .padding(11)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: 8).fill(Wash.bone))
                        }
                    }
                }

                historySection("Event trail") {
                    ForEach(trace.timeline) { event in
                        HStack(alignment: .top, spacing: 12) {
                            Text(String(event.at.prefix(16)).replacingOccurrences(of: "T", with: " "))
                                .font(.data(9.5)).foregroundStyle(Wash.faint).frame(width: 112, alignment: .leading)
                            Text(event.label).font(.iface(11.5)).foregroundStyle(Wash.ink70)
                        }
                    }
                }
            }
            .padding(26)
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
    }

    @ViewBuilder private func historySection<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            RailLabel(text: title)
            content()
        }
        .padding(15)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 11).fill(Wash.bone.opacity(0.82)).overlay(RoundedRectangle(cornerRadius: 11).stroke(Wash.line)))
    }

    private func receiptLabel(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased()).font(.data(8.5, .semibold)).foregroundStyle(Wash.faint)
            Text(value).font(.iface(11.5)).foregroundStyle(Wash.ink70)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func unavailable(_ reason: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Project history unavailable").font(.display(18, .medium)).foregroundStyle(Wash.ink)
            Text(reason).font(.iface(11.5)).foregroundStyle(Wash.muted)
            Text("python3 -m uvicorn helicon.api.app:app --port 8420")
                .font(.data(10)).foregroundStyle(Wash.slate).textSelection(.enabled)
        }
        .padding(28).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

/// Kept as a source-compatible name for any older window code or previews.
typealias WorkGraphView = ProjectHistoryView
