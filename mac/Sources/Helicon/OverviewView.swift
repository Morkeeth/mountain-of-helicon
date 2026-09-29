import SwiftUI

private struct OverviewAction: Identifiable {
    let id: String
    let title: String
    let evidence: String
    let destination: HeliconDestination
}

struct OverviewView: View {
    @ObservedObject private var navigation = RootNavigation.shared
    @State private var report: OverviewStatus?
    @State private var findings: FindingsSummary?
    @State private var windowDays = 30
    @State private var error: String?
    private let loader = OverviewStatusLoader()

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
        HStack(alignment: .bottom, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                RailLabel(text: "Setup health · separate denominators")
                Text("Overview")
                    .font(.display(28, .semibold)).foregroundStyle(Wash.ink)
                Text("Freshness, coverage, retrieval, drift, and rules. No magic overall score.")
                    .font(.iface(11.5)).foregroundStyle(Wash.muted)
            }
            Spacer()
            if let report {
                Text("Read \(Stamp.absolute(report.observedAt))")
                    .font(.data(9)).foregroundStyle(Wash.faint)
            }
            Button("Refresh") { Task { await load() } }
                .buttonStyle(.borderless)
                .font(.iface(10.5, .medium)).foregroundStyle(Wash.accent)
        }
        .padding(.leading, 28).padding(.trailing, 22)
        .padding(.top, 22).padding(.bottom, 16)
    }

    @ViewBuilder private var content: some View {
        if let report {
            dashboard(report)
        } else if let error {
            VStack(alignment: .leading, spacing: 9) {
                RailLabel(text: "Overview unavailable")
                Text("No health values are substituted.")
                    .font(.display(20, .medium)).foregroundStyle(Wash.ink)
                Text(error).font(.iface(11.5)).foregroundStyle(Wash.muted)
                Text("helicon overview --json")
                    .font(.data(10)).foregroundStyle(Wash.slate).textSelection(.enabled)
            }
            .padding(28).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else {
            ProgressView("Reading the local setup record…")
                .font(.iface(11)).foregroundStyle(Wash.muted)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func dashboard(_ report: OverviewStatus) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top, spacing: 10) {
                    ForEach(report.metrics) { metric in
                        metricCard(metric)
                    }
                }

                HStack(alignment: .top, spacing: 14) {
                    timeline(report.metrics)
                        .frame(maxWidth: .infinity)
                    statePanel(report)
                        .frame(width: 286)
                }

                HStack(alignment: .top, spacing: 14) {
                    actions(report)
                        .frame(maxWidth: .infinity)
                    inventory(report.inventory)
                        .frame(width: 390)
                }

                destinationRail
            }
            .padding(20)
            .frame(maxWidth: 1160, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
    }

    private func metricCard(_ metric: OverviewMetric) -> some View {
        let measured = metric.state == "measured"
        let value = metric.value ?? 0
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                RailLabel(text: metric.label)
                Spacer()
                Circle().fill(measured ? Wash.good : Wash.stale).frame(width: 6, height: 6)
            }
            Text(measured ? "\(Int(value.rounded()))%" : "—")
                .font(.display(25, .medium)).foregroundStyle(Wash.ink)
            Text(measured ? "\(metric.numerator ?? 0) / \(metric.denominator ?? 0)" : "unmeasured")
                .font(.data(10, .semibold)).foregroundStyle(measured ? Wash.slate : Wash.stale)
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(Wash.paperDeep)
                    Capsule().fill(measured ? Wash.good : Wash.faint)
                        .frame(width: measured ? proxy.size.width * value / 100 : 0)
                }
            }.frame(height: 5)
            Text(measured ? metric.formula : metric.unmeasured)
                .font(.iface(9.2)).foregroundStyle(Wash.muted)
                .lineLimit(3).fixedSize(horizontal: false, vertical: true)
        }
        .padding(13)
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 11).fill(Wash.bone.opacity(0.88))
            .overlay(RoundedRectangle(cornerRadius: 11).stroke(Wash.line)))
        .help(metric.limit + "\nSource: " + metric.source)
    }

    private func timeline(_ metrics: [OverviewMetric]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    RailLabel(text: "Recorded trend")
                    Text("Only windows with stored evidence draw a line")
                        .font(.iface(13, .semibold)).foregroundStyle(Wash.ink)
                }
                Spacer()
                Picker("Window", selection: $windowDays) {
                    Text("1w").tag(7)
                    Text("2w").tag(14)
                    Text("1m").tag(30)
                }
                .pickerStyle(.segmented).labelsHidden().frame(width: 170)
            }
            HStack(spacing: 18) {
                ForEach(metrics) { metric in
                    let values = recentValues(metric)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(metric.label).font(.iface(9.5, .medium)).foregroundStyle(Wash.ink70)
                        if values.count >= 2 {
                            TrendLine(values: values)
                                .stroke(Wash.slate, style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                                .frame(height: 38)
                        } else {
                            Text(values.isEmpty ? "no \(windowName) history" : "one reading")
                                .font(.data(8.5)).foregroundStyle(Wash.faint)
                                .frame(height: 38, alignment: .center)
                        }
                    }.frame(maxWidth: .infinity)
                }
            }
        }
        .panelStyle()
    }

    private var windowName: String { windowDays == 7 ? "1w" : windowDays == 14 ? "2w" : "1m" }

    private func recentValues(_ metric: OverviewMetric) -> [Double] {
        let cutoff = Date().addingTimeInterval(Double(-windowDays * 86_400))
        return metric.points.compactMap { point in
            guard let date = Stamp.parse(point.at), date >= cutoff else { return nil }
            return point.value
        }
    }

    private func statePanel(_ report: OverviewStatus) -> some View {
        let summary = findings
        let unresolved = summary?.total ?? report.unresolved.total
        let critical = summary?.critical ?? report.unresolved.critical
        return VStack(alignment: .leading, spacing: 11) {
            RailLabel(text: "Right now")
            stateRow("Setup drift", report.setupDrift.status == "tracking_started" ? "unmeasured" : report.setupDrift.status,
                     report.setupDrift.status == "tracking_started" ? Wash.stale : Wash.good)
            stateRow("Unresolved", unresolved.map(String.init) ?? "unmeasured",
                     (critical ?? 0) > 0 ? Wash.critical : Wash.good)
            stateRow("Needs judgment", summary.map { String($0.needsYou) } ?? "unmeasured",
                     (summary?.needsYou ?? 0) > 0 ? Wash.stale : Wash.faint)
            stateRow("Critical", critical.map(String.init) ?? "unmeasured",
                     (critical ?? 0) > 0 ? Wash.critical : Wash.good)
            Divider().overlay(Wash.line)
            Text(summary == nil ? report.unresolved.source : "GET /api/findings · full decision set")
                .font(.data(8.5)).foregroundStyle(Wash.faint)
                .fixedSize(horizontal: false, vertical: true)
        }
        .panelStyle()
    }

    private func stateRow(_ label: String, _ value: String, _ color: Color) -> some View {
        HStack {
            Text(label).font(.iface(10.5)).foregroundStyle(Wash.muted)
            Spacer()
            Text(value).font(.data(10, .semibold)).foregroundStyle(color)
        }
    }

    private func actions(_ report: OverviewStatus) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            RailLabel(text: "Top three actions")
            ForEach(topActions(report)) { action in
                Button { navigation.selection = action.destination } label: {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: action.destination.symbol)
                            .font(.system(size: 12)).foregroundStyle(Wash.slate).frame(width: 18)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(action.title).font(.iface(11.5, .semibold)).foregroundStyle(Wash.ink)
                            Text(action.evidence).font(.data(8.8)).foregroundStyle(Wash.muted)
                                .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer()
                        Image(systemName: "arrow.right").font(.system(size: 9)).foregroundStyle(Wash.faint)
                    }
                    .padding(.vertical, 5)
                }.buttonStyle(.plain)
            }
        }
        .panelStyle()
    }

    private func topActions(_ report: OverviewStatus) -> [OverviewAction] {
        var result: [OverviewAction] = []
        let critical = findings?.critical ?? report.unresolved.critical ?? 0
        let pending = findings?.needsYou ?? report.unresolved.total ?? 0
        if pending > 0 {
            let evidence = findings == nil
                ? "\(pending) unresolved store rows; \(critical) critical. Decision classification is unavailable."
                : "\(pending) need judgment; \(critical) critical."
            result.append(OverviewAction(id: "failures", title: "Review the highest-evidence failures",
                evidence: evidence, destination: .failures))
        }
        if let retrieval = report.metrics.first(where: { $0.id == "retrieval" }), retrieval.state != "measured" {
            result.append(OverviewAction(id: "retrieval", title: "Run a current labeled retrieval evaluation",
                evidence: retrieval.unmeasured, destination: .context))
        }
        if report.setupDrift.status == "tracking_started" {
            result.append(OverviewAction(id: "baseline", title: "Freeze an explicit setup baseline",
                evidence: "No prior snapshot exists, so setup drift cannot be claimed.", destination: .setup))
        }
        if let rules = report.metrics.first(where: { $0.id == "rules" }),
           let numerator = rules.numerator, let denominator = rules.denominator, numerator < denominator {
            result.append(OverviewAction(id: "rules", title: "Inspect rules with missing sources",
                evidence: "\(denominator - numerator) of \(denominator) compiled rules lost source integrity.", destination: .rules))
        }
        return Array(result.prefix(3))
    }

    private func inventory(_ inventory: OverviewInventory) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            RailLabel(text: "Observed architecture")
            inventoryRow("Harnesses", inventory.harnesses.count,
                         inventory.harnesses.joined(separator: " · "))
            inventoryRow("Index files", inventory.indexFiles.count,
                         inventory.indexFiles.map(\.name).joined(separator: " · "))
            inventoryRow("Routes", inventory.routes.reduce(0) { $0 + $1.count },
                         routeSummary(inventory.routes))
            let records = inventory.stores.compactMap(\.records).reduce(0, +)
            inventoryRow("Memory stores", inventory.stores.count,
                         inventory.stores.map(\.name).joined(separator: " · ") + (records > 0 ? " · \(records.formatted()) live" : ""))
        }
        .panelStyle()
    }

    private func inventoryRow(_ label: String, _ count: Int, _ detail: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text("\(count)").font(.display(17, .medium)).foregroundStyle(Wash.ink).frame(width: 30, alignment: .leading)
            VStack(alignment: .leading, spacing: 1) {
                Text(label).font(.iface(10.5, .semibold)).foregroundStyle(Wash.ink)
                Text(detail.isEmpty ? "none observed" : detail)
                    .font(.data(8.5)).foregroundStyle(Wash.muted).lineLimit(2)
            }
        }
    }

    private func routeSummary(_ routes: [OverviewRoute]) -> String {
        let hooks = routes.filter { $0.kind == "hook" }.count
        let sources = routes.filter { $0.kind == "source" }.count
        return "\(hooks) hook events · \(sources) source connectors"
    }

    private var destinationRail: some View {
        HStack(spacing: 9) {
            RailLabel(text: "Inspect")
            ForEach([HeliconDestination.setup, .context, .rules, .failures, .history]) { destination in
                Button(destination.title) { navigation.selection = destination }
                    .buttonStyle(.borderless).font(.iface(10.5, .medium)).foregroundStyle(Wash.slate)
            }
        }
        .padding(.horizontal, 4)
    }

    private func load() async {
        report = nil
        error = nil
        do {
            report = try await loader.load()
            findings = try? await HeliconAPI().findings(limit: 1).summary
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

private struct TrendLine: Shape {
    let values: [Double]

    func path(in rect: CGRect) -> Path {
        guard values.count >= 2 else { return Path() }
        var path = Path()
        for (index, value) in values.enumerated() {
            let x = rect.minX + rect.width * CGFloat(index) / CGFloat(values.count - 1)
            let y = rect.maxY - rect.height * CGFloat(max(0, min(100, value))) / 100
            if index == 0 { path.move(to: CGPoint(x: x, y: y)) }
            else { path.addLine(to: CGPoint(x: x, y: y)) }
        }
        return path
    }
}

private extension View {
    func panelStyle() -> some View {
        self.padding(15)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 11).fill(Wash.bone.opacity(0.88))
                .overlay(RoundedRectangle(cornerRadius: 11).stroke(Wash.line)))
    }
}
