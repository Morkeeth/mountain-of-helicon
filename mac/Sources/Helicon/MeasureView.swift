import SwiftUI

/// MEASUREMENT — the weekly review as a series.
///
/// Every other surface in this app answers a question about now: what is open,
/// what is unchecked, what forked. This one answers whether any of it is getting
/// better, which is a different question and needs a different unit — the week.
///
/// THE ONE DEVICE: every number on this screen carries, directly beneath it, the
/// command that reproduces it. That is not decoration and it is not a tooltip.
/// This product's own definition is that a measurement is a number, the command
/// that reproduces it, and the moment it was read — so the definition IS the
/// layout. A number here that you cannot re-derive yourself has failed on its own
/// terms, and the screen is built so that failing would be visible.
///
/// Three states, drawn differently on purpose:
///
///   MEASURED, WITH HISTORY   the number, and how it moved since last week.
///   FIRST READING            the number, and no trend. Not a zero delta, not a
///                            flat line: a delta implies a previous value and
///                            there is not one yet.
///   UNMEASURED               no number at all. The reason, and the command that
///                            would make it measurable. A detector whose source
///                            is not configured must never render as a healthy
///                            zero — that is the false-green this whole product
///                            exists to catch, and drawing it as 0 would put a
///                            falling line on the chart and call it progress.
struct MeasureView: View {
    private let api = HeliconAPI()
    @State private var payload: MeasurePayload?
    @State private var error: String?
    @State private var recording = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                header
                if let error { errorRow(error) }
                if let p = payload {
                    if p.metrics.isEmpty { emptyState }
                    else { ForEach(p.metrics, id: \.metric) { row($0) } }
                } else if error == nil {
                    Text("Reading the series…")
                        .font(.iface(13)).foregroundStyle(Wash.muted)
                }
            }
            .padding(28)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Wash.paper)
        .task { await load() }
    }

    // MARK: header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            RailLabel(text: "Measurement")
            Text("Is the setup getting better?")
                .font(.display(24, .medium)).foregroundStyle(Wash.ink)
            if let p = payload, !p.weeks.isEmpty {
                // The population, always. One week of readings is not a trend
                // and the header must not let it look like one.
                Text(p.weeks.count == 1
                     ? "1 week recorded · \(p.weeks[0]) · no trend yet"
                     : "\(p.weeks.count) weeks recorded · \(p.weeks.first ?? "") to \(p.weeks.last ?? "")")
                    .font(.iface(12)).foregroundStyle(Wash.muted)
            }
            // On its own line: in the header HStack it sat against the window
            // edge and clipped at the default width.
            recordButton.padding(.top, 2)
        }
    }

    /// Recording is an explicit act with its own button. Reading this screen must
    /// never write a row: a surface that measured on every open would turn one
    /// glanced-at day into four weeks of trend.
    private var recordButton: some View {
        Button {
            Task { await takeReading() }
        } label: {
            HStack(spacing: 6) {
                Text(recording ? "Reading…" : "Take this week's reading")
                    .font(.iface(11, .semibold))
                KeyCap(key: "M")
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                    .fill(Wash.accentDim)
                    .overlay(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                        .strokeBorder(Wash.line2, lineWidth: 0.5))
            )
            .foregroundStyle(Wash.accent)
        }
        .buttonStyle(.plain)
        .disabled(recording)
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Nothing recorded yet.")
                .font(.display(17, .medium)).foregroundStyle(Wash.ink)
            Text("The first reading is a number. The second one is a measurement.")
                .font(.iface(13)).foregroundStyle(Wash.muted)
            Text("helicon measure --record")
                .font(.data(12)).foregroundStyle(Wash.slate)
                .padding(.top, 4)
        }
        .padding(.vertical, 10)
    }

    // MARK: one metric

    private func row(_ m: MeasureMetric) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(m.label).font(.iface(13, .medium)).foregroundStyle(Wash.ink)

            if let v = m.latest {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    // The number is the biggest thing on the row, in the display
                    // face. Fraunces carries every number in this identity.
                    Text(String(v))
                        .font(.display(32, .semibold))
                        .foregroundStyle(Wash.ink)
                    trend(m)
                    if let pop = m.population {
                        Text("of \(pop)")
                            .font(.iface(12)).foregroundStyle(Wash.faint)
                    }
                }
            } else {
                // No number. Not a zero, not a dash pretending to be one.
                VStack(alignment: .leading, spacing: 2) {
                    Text("unmeasured")
                        .font(.display(20, .regular)).foregroundStyle(Wash.faint)
                    Text(m.unmeasured.isEmpty ? "source not configured" : m.unmeasured)
                        .font(.iface(11)).foregroundStyle(Wash.muted)
                }
            }

            // THE DEVICE. Every number, its reproducing command, right here.
            Text(m.command)
                .font(.data(11)).foregroundStyle(Wash.slate)
                .textSelection(.enabled)

            if m.readings >= 2 { ticks(m) }
        }
        .padding(.vertical, 9)
        .padding(.horizontal, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: Wash.radius, style: .continuous)
                .fill(Wash.bone)
                .overlay(RoundedRectangle(cornerRadius: Wash.radius, style: .continuous)
                    .strokeBorder(Wash.line, lineWidth: 0.5))
        )
    }

    /// How it moved. Orange is improvement and nothing else in this identity, so
    /// a worse week is stated in plain ink rather than alarmed in red — a metric
    /// going the wrong way is information, not an incident.
    @ViewBuilder
    private func trend(_ m: MeasureMetric) -> some View {
        if let d = m.delta {
            let better = (m.direction == "down" && d < 0) || (m.direction == "up" && d > 0)
            let word: String = d == 0 ? "unchanged"
                : "\(d > 0 ? "+" : "")\(d) since last week"
            Text(word)
                .font(.iface(12, better ? .semibold : .regular))
                .foregroundStyle(d == 0 ? Wash.muted : (better ? Wash.improve : Wash.ink70))
        } else {
            Text("first reading")
                .font(.iface(12)).foregroundStyle(Wash.faint)
        }
    }

    /// Week ticks, drawn ONLY once there are two real readings. With one point a
    /// chart is a dot claiming to be a line.
    private func ticks(_ m: MeasureMetric) -> some View {
        let points = m.points.filter { $0.value != nil }
        let values = points.compactMap { $0.value }
        let top = max(values.max() ?? 1, 1)
        return HStack(alignment: .bottom, spacing: 3) {
            ForEach(Array(points.enumerated()), id: \.offset) { _, p in
                let h = max(2.0, 22.0 * Double(p.value ?? 0) / Double(top))
                RoundedRectangle(cornerRadius: 1, style: .continuous)
                    .fill(Wash.mist)
                    .frame(width: 6, height: h)
            }
        }
        .frame(height: 24, alignment: .bottom)
        .padding(.top, 2)
    }

    private func errorRow(_ e: String) -> some View {
        Text(e).font(.iface(12)).foregroundStyle(Wash.ink)
            .padding(10).background(Wash.bone)
    }

    // MARK: data

    private func load() async {
        do {
            payload = try await api.measure()
            try? await api.recordSurfaceOpen("measure")
        } catch {
            self.error = "Could not read the series: \(error.localizedDescription)"
        }
    }

    private func takeReading() async {
        recording = true
        defer { recording = false }
        do {
            _ = try await api.takeReading()
            payload = try await api.measure()
        } catch {
            self.error = "Could not record a reading: \(error.localizedDescription)"
        }
    }
}
