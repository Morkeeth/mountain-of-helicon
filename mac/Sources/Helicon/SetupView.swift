import SwiftUI

struct SetupView: View {
    @State private var status: SetupStatus?
    @State private var error: String?
    private let loader = SetupStatusLoader()

    var body: some View {
        ZStack {
            WashBackground()
            VStack(alignment: .leading, spacing: 0) {
                header
                Divider().overlay(Wash.line)
                content
            }
        }
        .task { await load() }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                RailLabel(text: "What is wired now")
                Text("Setup")
                    .font(.display(26, .semibold)).foregroundStyle(Wash.ink)
                Text("Instructions, skills, harness routes, and what the evidence cannot yet prove.")
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

    @ViewBuilder private var content: some View {
        if let status {
            setup(status)
        } else if let error {
            unavailable(error)
        } else {
            ProgressView("Reading helicon status --json…")
                .font(.iface(11)).foregroundStyle(Wash.muted)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func setup(_ report: SetupStatus) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                stateCard(report)

                HStack(alignment: .top, spacing: 14) {
                    panel("Coverage", title: report.snapshot.coverage.status.capitalized) {
                        fact("Observed", "\(report.snapshot.coverage.observed.count)")
                        fact("Unknown", "\(report.snapshot.coverage.unknown.count)")
                        if !report.snapshot.coverage.unknown.isEmpty {
                            Text(report.snapshot.coverage.unknown.joined(separator: " · "))
                                .font(.data(9)).foregroundStyle(Wash.faint)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    panel("Inventory", title: "Current local setup") {
                        fact("Components", "\(report.snapshot.components.count)")
                        fact("Edges", "\(report.snapshot.edges.count)")
                        fact("Findings", "\(report.snapshot.findings.count)")
                    }
                }

                panel("Components", title: "What was found") {
                    let groups = Dictionary(grouping: report.snapshot.components, by: \.kind)
                    ForEach(groups.keys.sorted(), id: \.self) { kind in
                        let items = groups[kind] ?? []
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(kind.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.iface(11.5, .semibold)).foregroundStyle(Wash.ink)
                                Spacer()
                                Text("\(items.count)").font(.data(10, .semibold)).foregroundStyle(Wash.slate)
                            }
                            Text(items.prefix(8).map(\.name).joined(separator: " · "))
                                .font(.data(9.5)).foregroundStyle(Wash.muted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if kind != groups.keys.sorted().last { Divider().overlay(Wash.line) }
                    }
                }

                panel("Routes", title: "Configuration is not use") {
                    ForEach(report.snapshot.edges.prefix(24)) { edge in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text(edge.relation.replacingOccurrences(of: "_", with: " "))
                                .font(.iface(10.5, .medium)).foregroundStyle(Wash.ink)
                                .frame(width: 92, alignment: .leading)
                            Text(short(edge.from) + " → " + short(edge.to))
                                .font(.data(9.5)).foregroundStyle(Wash.ink70)
                            Spacer()
                            Text("loaded \(edge.evidence.loaded) · used \(edge.evidence.used)")
                                .font(.data(8.5)).foregroundStyle(Wash.faint)
                        }
                    }
                    if report.snapshot.edges.count > 24 {
                        Text("\(report.snapshot.edges.count - 24) more routes in the CLI snapshot")
                            .font(.iface(9.5)).foregroundStyle(Wash.faint)
                    }
                }

                Text("Source: helicon status --json · \(report.snapshot.project) · \(report.snapshot.scope)")
                    .font(.data(8.5)).foregroundStyle(Wash.faint).textSelection(.enabled)
            }
            .padding(26)
            .frame(maxWidth: 960, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
    }

    private func stateCard(_ report: SetupStatus) -> some View {
        let comparison = report.comparison
        return VStack(alignment: .leading, spacing: 9) {
            HStack {
                RailLabel(text: "Change since explicit baseline")
                Spacer()
                Chip(text: comparison.status,
                     color: comparison.status == "changed" ? Wash.improve : Wash.slate)
            }
            Text(comparison.status == "tracking_started" ? "Tracking started" : comparison.message)
                .font(.display(21, .medium)).foregroundStyle(Wash.ink)
            Text(comparison.message)
                .font(.iface(11.5)).foregroundStyle(Wash.muted)
            HStack(spacing: 24) {
                fact("Component changes", "\(comparison.components.count)")
                fact("Route changes", "\(comparison.edges.count)")
                fact("Baseline", comparison.baselineObservedAt.map(Stamp.absolute) ?? "None supplied")
            }
            Text("Observed \(Stamp.absolute(report.snapshot.observedAt))")
                .font(.data(9)).foregroundStyle(Wash.faint)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Wash.boneRaised)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Wash.line2)))
    }

    private func unavailable(_ reason: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            RailLabel(text: "Setup status unavailable")
            Text("No setup values are substituted.")
                .font(.display(20, .medium)).foregroundStyle(Wash.ink)
            Text(reason).font(.iface(11.5)).foregroundStyle(Wash.muted)
            Text("helicon status --json --project <project>")
                .font(.data(10)).foregroundStyle(Wash.slate).textSelection(.enabled)
        }
        .padding(20)
        .frame(maxWidth: 780, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Wash.bone)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Wash.line)))
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func panel<Content: View>(_ label: String, title: String,
                                      @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            RailLabel(text: label)
            Text(title).font(.iface(14, .semibold)).foregroundStyle(Wash.ink)
            content()
        }
        .padding(17)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Wash.bone.opacity(0.86))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Wash.line)))
    }

    private func fact(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(.iface(10.5)).foregroundStyle(Wash.muted)
            Spacer()
            Text(value).font(.data(10, .semibold)).foregroundStyle(Wash.ink)
        }
    }

    private func short(_ value: String) -> String {
        value.split(separator: ":", maxSplits: 1).first.map(String.init) ?? value
    }

    private func load() async {
        status = nil
        error = nil
        do {
            status = try await loader.load()
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
