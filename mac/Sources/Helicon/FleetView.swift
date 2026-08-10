import SwiftUI

/// The fleet board: which of my agents' claims has anything independent checked?
///
/// Six incidents on 2026-08-10 were instruments reporting healthy while broken —
/// a VPS probe green with no key, a benchmark reporting LIFTS off its own answer
/// key, this suite's own fleet showing runs as governed whose objectives had been
/// reconstructed after the fact. Each was a claim nobody had checked, drawn
/// identically to a claim that had been.
///
/// So the one job of this surface is that an unchecked claim must not look like a
/// checked one. Levels get different weight, different colour and a stated reason;
/// none of them get a tick.
///
/// Added alongside the ruling queue, not in place of it (Oscar, 2026-08-10:
/// "add feature and we remove the ones we dont use in the future"). Both surfaces
/// record their opens so that later removal is decided on usage, not taste.
struct FleetView: View {
    private let api = HeliconAPI()
    @State private var claims: ClaimsPayload?
    @State private var fleet: FleetPayload?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                if let error { errorRow(error) }
                if let claims { ladder(claims); claimRows(claims) }
                else if error == nil { Text("Reading the store…").font(.iface(13)).foregroundStyle(Wash.muted) }
            }
            .padding(28)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Wash.paper)
        .task { await load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("FLEET").font(.iface(11, .semibold)).foregroundStyle(Wash.muted).tracking(1.4)
            // The headline is the finding, not a score. On 2026-08-10 it read
            // "2 of 40" with INDEPENDENTLY_CHECKED at zero.
            Text(claims?.headline ?? "…").font(.iface(19, .medium)).foregroundStyle(Wash.ink)
            if let f = fleet {
                Text("\(f.runningCount) running · \(f.observedCount) observed after the fact")
                    .font(.iface(12)).foregroundStyle(Wash.muted)
            }
        }
    }

    private func ladder(_ c: ClaimsPayload) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(c.levels, id: \.self) { level in
                let n = c.counts[level] ?? 0
                HStack(spacing: 12) {
                    Text(String(n)).font(.iface(15, .semibold))
                        .frame(width: 34, alignment: .trailing)
                        .foregroundStyle(n == 0 ? Wash.faint : tone(level))
                    Text(level.replacingOccurrences(of: "_", with: " ").lowercased())
                        .font(.iface(13, weight(level))).foregroundStyle(tone(level))
                        .frame(width: 190, alignment: .leading)
                    Text(c.meaning[level] ?? "").font(.iface(11)).foregroundStyle(Wash.muted)
                }
            }
        }
    }

    private func claimRows(_ c: ClaimsPayload) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("CLAIMS").font(.iface(11, .semibold)).foregroundStyle(Wash.muted).tracking(1.4)
            ForEach(c.claims.prefix(24), id: \.id) { claim in
                VStack(alignment: .leading, spacing: 3) {
                    Text(claim.claimed).font(.iface(13, weight(claim.level)))
                        .foregroundStyle(Wash.ink).lineLimit(2)
                    HStack(spacing: 10) {
                        Text(claim.level.replacingOccurrences(of: "_", with: " ").lowercased())
                            .font(.iface(11, .medium)).foregroundStyle(tone(claim.level))
                        Text("\(claim.written) written").font(.iface(11)).foregroundStyle(Wash.muted)
                        // Unknown, never 0 — a 0 would make the most expensive
                        // unmeasured work look free.
                        Text(claim.costKnown ? String(format: "$%.4f", claim.cost ?? 0)
                                             : "cost unknown")
                            .font(.iface(11)).foregroundStyle(claim.costKnown ? Wash.muted : Wash.faint)
                        Text(claim.why).font(.iface(11)).foregroundStyle(Wash.faint).lineLimit(1)
                    }
                }
            }
        }
    }

    private func errorRow(_ e: String) -> some View {
        Text(e).font(.iface(12)).foregroundStyle(Wash.ink).padding(10)
            .background(Wash.bone)
    }

    /// Weight carries the distinction as well as colour, so it survives greyscale
    /// and colour-blindness. An unchecked claim must never read as settled.
    private func weight(_ level: String) -> Font.Weight {
        switch level {
        case "INDEPENDENTLY_CHECKED", "HUMAN_RULED": return .semibold
        case "SELF_REPORTED": return .regular
        default: return .light
        }
    }

    private func tone(_ level: String) -> Color {
        switch level {
        case "INDEPENDENTLY_CHECKED": return Wash.ink
        case "HUMAN_RULED": return Wash.ink
        case "SELF_REPORTED": return Wash.muted
        default: return Wash.faint
        }
    }

    private func load() async {
        do {
            async let c: ClaimsPayload = api.claims()
            async let f: FleetPayload = api.fleet()
            claims = try await c
            fleet = try await f
            // Recorded so the later remove-what-we-don't-use decision has evidence.
            try? await api.recordSurfaceOpen("fleet")
        } catch {
            self.error = "Could not read the store: \(error.localizedDescription)"
        }
    }
}
