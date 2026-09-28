import SwiftUI

private struct ParsedRule: Identifiable {
    let id: Int
    let section: String
    let text: String
    let provenance: String?
}

/// Native read of the compiled law. This does not maintain a second rules
/// store: every row comes from GET /api/gold and keeps its provenance line.
struct RulesView: View {
    private let api = HeliconAPI()
    @State private var payload: GoldPayload?
    @State private var query = ""
    @State private var error: String?

    private var rules: [ParsedRule] {
        guard let markdown = payload?.markdown else { return [] }
        var section = "Rules"
        var parsed: [ParsedRule] = []
        var pending: (section: String, text: String)?

        func appendPending(_ provenance: String? = nil) {
            guard let pending else { return }
            parsed.append(ParsedRule(id: parsed.count, section: pending.section,
                                     text: pending.text, provenance: provenance))
        }

        for raw in markdown.components(separatedBy: .newlines) {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("## ") {
                appendPending()
                pending = nil
                section = String(line.dropFirst(3))
            } else if line.hasPrefix("- ") {
                appendPending()
                pending = (section, String(line.dropFirst(2)))
            } else if line.hasPrefix("_["), line.hasSuffix("]_") {
                appendPending(String(line.dropFirst().dropLast()))
                pending = nil
            } else if line.hasPrefix("_why:"), let current = pending {
                pending = (current.section, current.text + " · " + line.dropFirst().dropLast())
            }
        }
        appendPending()
        return parsed
    }

    private var shown: [ParsedRule] {
        guard !query.isEmpty else { return rules }
        return rules.filter {
            ($0.section + " " + $0.text + " " + ($0.provenance ?? ""))
                .localizedCaseInsensitiveContains(query)
        }
    }

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
        HStack(alignment: .bottom, spacing: 18) {
            VStack(alignment: .leading, spacing: 4) {
                RailLabel(text: "Current law")
                Text("Rules")
                    .font(.display(26, .semibold))
                    .foregroundStyle(Wash.ink)
                Text("Human rulings and standing feedback, compiled with their receipts.")
                    .font(.iface(11.5))
                    .foregroundStyle(Wash.muted)
            }
            Spacer()
            TextField("Find a rule", text: $query)
                .textFieldStyle(.roundedBorder)
                .font(.iface(11))
                .frame(width: 260)
            if let payload {
                Text("\(rules.count) rules · \(payload.history.count) compiles")
                    .font(.data(9.5))
                    .foregroundStyle(Wash.faint)
            }
        }
        .padding(.leading, 28)
        .padding(.trailing, 22)
        .padding(.top, 24)
        .padding(.bottom, 18)
    }

    @ViewBuilder
    private var content: some View {
        if let error {
            VStack(alignment: .leading, spacing: 8) {
                Text("Could not read the rules").font(.display(18, .medium))
                Text(error).font(.iface(11.5)).foregroundStyle(Wash.muted)
                Text("python3 -m uvicorn helicon.api.app:app --port 8420")
                    .font(.data(10)).foregroundStyle(Wash.slate).textSelection(.enabled)
            }
            .padding(28)
        } else if payload == nil {
            ProgressView("Compiling the current law…")
                .font(.iface(11)).foregroundStyle(Wash.muted)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 9) {
                    ForEach(shown) { rule in
                        VStack(alignment: .leading, spacing: 6) {
                            RailLabel(text: rule.section)
                            Text(rule.text.replacingOccurrences(of: "**", with: "")
                                .replacingOccurrences(of: "`", with: ""))
                                .font(.iface(12.5))
                                .foregroundStyle(Wash.ink)
                                .fixedSize(horizontal: false, vertical: true)
                            if let provenance = rule.provenance {
                                Text(provenance)
                                    .font(.data(9.5))
                                    .foregroundStyle(Wash.faint)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Wash.bone.opacity(0.88))
                                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Wash.line))
                        )
                    }
                    if shown.isEmpty {
                        Text("No rule matches “\(query)”.")
                            .font(.iface(12)).foregroundStyle(Wash.muted)
                            .padding(.top, 36)
                    }
                }
                .padding(24)
                .frame(maxWidth: 920)
                .frame(maxWidth: .infinity)
            }
        }
    }

    private func load() async {
        do {
            payload = try await api.gold()
            error = nil
        } catch {
            self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }
}
