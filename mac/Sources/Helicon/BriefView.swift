import SwiftUI

/// BRIEF — the morning screen on the desktop, the product vision in one glance.
/// Reads GET /api/brief (the same object the CLI, MCP, and dashboard render) and
/// draws all five pillars in Alpine Wash. Fraunces carries the one number that
/// matters (how many things need YOU); mono for ids and costs; judgment red only
/// for genuine exceptions. An empty pillar says so in words — nothing is invented.
struct BriefView: View {
    @State private var brief: Brief?
    @State private var error: String?

    private let api = HeliconAPI()

    var body: some View {
        ZStack {
            WashBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if let error {
                        Text("brief unavailable — \(error)")
                            .font(.data(12)).foregroundStyle(Wash.muted).padding(28)
                    } else if let brief {
                        content(brief)
                    } else {
                        Text("assembling the brief…")
                            .font(.data(12)).foregroundStyle(Wash.muted).padding(28)
                    }
                }
                .frame(maxWidth: 720, alignment: .leading)
                .padding(.horizontal, 30)
                .padding(.vertical, 30)
                .frame(maxWidth: .infinity)
            }
        }
        .frame(minWidth: 760, minHeight: 680)
        .task { await load() }
    }

    private func load() async {
        do { brief = try await api.brief() }
        catch { self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription }
    }

    @ViewBuilder
    private func content(_ b: Brief) -> some View {
        let need = b.calm.worthYourJudgment.count

        RailLabel(text: "Morning Brief")
        HStack(alignment: .firstTextBaseline, spacing: 14) {
            Text("\(need)")
                .font(.display(64, .light))
                .foregroundStyle(need > 0 ? Wash.critical : Wash.faint)
            Text(need == 1 ? "thing worth your judgment" : "things worth your judgment")
                .font(.display(20)).foregroundStyle(Wash.ink)
        }
        .padding(.top, 4).padding(.bottom, 18)

        pillar("Calm", b.calm.headline) {
            ForEach(b.calm.worthYourJudgment) { e in
                HStack(alignment: .top, spacing: 10) {
                    Text(e.severity.uppercased())
                        .font(.data(10, .semibold)).foregroundStyle(Wash.severity(e.severity))
                        .frame(width: 62, alignment: .leading)
                    Text("#\(e.id) \(e.finding)")
                        .font(.iface(13)).foregroundStyle(Wash.ink)
                }.padding(.vertical, 3)
            }
        }
        pillar("Truth", b.truth.headline) {
            ForEach(b.truth.noLongerTrustworthy) { m in
                HStack(spacing: 10) {
                    Text(m.id).font(.data(10)).foregroundStyle(Wash.muted)
                    Text(m.title).font(.iface(13)).foregroundStyle(Wash.ink).lineLimit(1)
                    Text("conf \(m.confidence, specifier: "%.2f")").font(.data(10)).foregroundStyle(Wash.faint)
                }.padding(.vertical, 2)
            }
        }
        pillar("Direction", b.direction.headline) {
            ForEach(b.direction.taskClasses) { p in
                HStack(spacing: 6) {
                    Text("\(p.taskClass) →").font(.data(12)).foregroundStyle(Wash.muted)
                    Text(p.recommendation ?? "\(p.lean ?? "—") (lean)")
                        .font(.data(12, .medium))
                        .foregroundStyle(p.sufficient ? Wash.improve : Wash.muted)
                }.padding(.vertical, 2)
            }
        }
        pillar("Reflection", b.reflection.headline) {
            ForEach(b.reflection.runsScored) { r in
                Text("\(r.runID) · \(r.model) · score \(r.score, specifier: "%.2f") · $\(r.cost, specifier: "%.2f")")
                    .font(.data(11)).foregroundStyle(Wash.muted).padding(.vertical, 2)
            }
        }
        pillar("Continuity", b.continuity.headline) { EmptyView() }
    }

    @ViewBuilder
    private func pillar<Content: View>(_ name: String, _ headline: String,
                                       @ViewBuilder _ items: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Divider().overlay(Wash.line)
            HStack(alignment: .firstTextBaseline, spacing: 14) {
                Text(name.uppercased())
                    .font(.iface(10, .semibold)).tracking(0.14 * 10)
                    .foregroundStyle(Wash.muted).frame(width: 92, alignment: .leading)
                Text(headline).font(.display(16)).foregroundStyle(Wash.ink)
            }.padding(.vertical, 14)
            VStack(alignment: .leading, spacing: 0) { items() }
                .padding(.leading, 106).padding(.bottom, 6)
        }
    }
}
