import Foundation

// Shapes modelled from the LIVE API, not from a guess. Every field below was
// observed in an actual response from `GET /api/findings` on 2026-07-15.
// Nullable fields are optional here because the server genuinely emits null for
// them (cube_source / source_ref / cube_id are NULL for non-cube findings, and
// regret's created_at comes from a nullable last_wanted).

struct Finding: Decodable, Identifiable, Hashable {
    let id: String              // "audit-366" | "regret-gc_ae65…" | "skill-dups"
    let kind: String            // nightly | factual | supersession | regret | agent-flag | skill | identity | temporal | decay | …
    let severity: String        // critical | high | warning | medium | info
    let title: String
    let why: String
    let evidencePreview: String
    let source: String?
    let sourceRef: String?
    let cubeID: String?
    let suggestedAction: String
    let createdAt: String?
    let lane: String            // decision | ambient

    enum CodingKeys: String, CodingKey {
        case id, kind, severity, title, why, source, lane
        case evidencePreview  = "evidence_preview"
        case sourceRef        = "source_ref"
        case cubeID           = "cube_id"
        case suggestedAction  = "suggested_action"
        case createdAt        = "created_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id              = try c.decode(String.self, forKey: .id)
        kind            = try c.decodeIfPresent(String.self, forKey: .kind) ?? "unknown"
        severity        = try c.decodeIfPresent(String.self, forKey: .severity) ?? "info"
        title           = try c.decodeIfPresent(String.self, forKey: .title) ?? "(untitled)"
        why             = try c.decodeIfPresent(String.self, forKey: .why) ?? ""
        evidencePreview = try c.decodeIfPresent(String.self, forKey: .evidencePreview) ?? ""
        source          = try c.decodeIfPresent(String.self, forKey: .source)
        sourceRef       = try c.decodeIfPresent(String.self, forKey: .sourceRef)
        cubeID          = try c.decodeIfPresent(String.self, forKey: .cubeID)
        suggestedAction = try c.decodeIfPresent(String.self, forKey: .suggestedAction) ?? "review"
        createdAt       = try c.decodeIfPresent(String.self, forKey: .createdAt)
        lane            = try c.decodeIfPresent(String.self, forKey: .lane) ?? "decision"
    }

    /// Only audit_log-backed findings carry an integer id the write path can
    /// address. `regret-*` and `skill-*` are computed at request time and have
    /// no row to confirm — the verdict bar must stay honestly disabled for them.
    var auditID: Int? {
        guard id.hasPrefix("audit-") else { return nil }
        return Int(id.dropFirst(6))
    }

    var isConfirmable: Bool { auditID != nil }

    /// Why the verdict bar is off, in the finding's own terms.
    var notConfirmableReason: String? {
        guard !isConfirmable else { return nil }
        if id.hasPrefix("regret-") {
            return "Regret findings are derived from retrieval history, not audit_log rows. "
                 + "The API exposes no write path for them — restore runs through review."
        }
        if id.hasPrefix("skill-") {
            return "Skill findings are recomputed from a filesystem scan on every request. "
                 + "There is no row to confirm; the fix is `helicon fix-skills --apply`."
        }
        return "No audit_log row backs this finding, so it cannot be confirmed over HTTP."
    }

    var shortTitle: String {
        title.count <= 96 ? title : String(title.prefix(96)) + "…"
    }

    /// "Contradiction: Cross-source contradiction: Casey wedding — …" → drop the
    /// leading check name, which the chip already carries.
    var whyBody: String {
        guard let r = why.range(of: ": ") else { return why }
        return String(why[r.upperBound...])
    }

    var checkName: String {
        guard let r = why.range(of: ": ") else { return kind.capitalized }
        return String(why[..<r.lowerBound])
    }

    var age: String {
        guard let createdAt, let d = Stamp.parse(createdAt) else { return "—" }
        return Stamp.relative(d)
    }
}

struct FindingsSummary: Decodable {
    let total: Int
    let needsYou: Int
    let ambient: Int
    let byKind: [String: Int]
    let bySeverity: [String: Int]

    enum CodingKeys: String, CodingKey {
        case total
        case needsYou    = "needs_you"
        case ambient
        case byKind      = "by_kind"
        case bySeverity  = "by_severity"
    }

    var critical: Int { bySeverity["critical"] ?? 0 }
    var warning: Int  { bySeverity["warning"] ?? 0 }

    static let empty = FindingsSummary(total: 0, needsYou: 0, ambient: 0,
                                       byKind: [:], bySeverity: [:])
}

struct FindingsResponse: Decodable {
    let findings: [Finding]
    let summary: FindingsSummary
}

struct Health: Decodable {
    let status: String
    let cubes: Int
}

struct ConfirmRequest: Encodable {
    let finding_id: Int
    let decision: String
    let notes: String
}

struct ConfirmResponse: Decodable {
    let findingID: Int
    let decision: String
    let killedCubes: [String]

    enum CodingKeys: String, CodingKey {
        case findingID   = "finding_id"
        case decision
        case killedCubes = "killed_cubes"
    }
}

// MARK: - timestamps

enum Stamp {
    static func parse(_ s: String) -> Date? {
        // The API emits naive ISO ("2026-07-15T07:53:39.055619"), UTC by
        // construction (datetime.now(timezone.utc).replace(tzinfo=None)).
        let head = String(s.prefix(19))
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        f.timeZone = TimeZone(identifier: "UTC")
        f.locale = Locale(identifier: "en_US_POSIX")
        return f.date(from: head)
    }

    static func relative(_ d: Date) -> String {
        let secs = Date().timeIntervalSince(d)
        if secs < 90 { return "just now" }
        let mins = secs / 60
        if mins < 60 { return "\(Int(mins))m ago" }
        let hours = mins / 60
        if hours < 24 { return "\(Int(hours))h ago" }
        return "\(Int(hours / 24))d ago"
    }

    static func absolute(_ s: String?) -> String {
        guard let s, let d = parse(s) else { return "—" }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        f.timeZone = TimeZone(identifier: "UTC")
        return f.string(from: d) + " UTC"
    }
}

// MARK: - contradiction evidence

/// One side of a contradiction, as `helicon.pairing.format_pair_evidence`
/// writes it. Parsed, never fabricated: if the text does not match the shape,
/// `PairEvidence.parse` returns nil and the inspector shows the raw receipt.
struct ClaimSide {
    let label: String     // "A" / "B"
    let value: String     // "03-14..03-22"
    let support: String   // "1 cube(s)"
    let scope: String     // "claude-code:memory_status_2026-07-11.md"
    let line: String      // the exact asserting line
}

struct PairEvidence {
    let a: ClaimSide
    let b: ClaimSide
    let also: String?
    let judge: String?

    /// Shape emitted by format_pair_evidence():
    ///   A: {value}   ({n} cube(s))   {scope}
    ///      | {line_a}
    ///   B: {value}   ({n} cube(s))   {scope}
    ///      | {line_b}
    ///      also asserted: x, y
    ///      judge: {explanation}
    static func parse(_ text: String) -> PairEvidence? {
        var head: [String: (String, String, String)] = [:]
        var lines: [String: String] = [:]
        var also: String?
        var judge: String?
        var last: String?

        for raw in text.components(separatedBy: "\n") {
            let trimmed = raw.trimmingCharacters(in: .whitespaces)
            if raw.hasPrefix("A: ") || raw.hasPrefix("B: ") {
                let key = String(raw.prefix(1))
                let parts = raw.dropFirst(3)
                    .components(separatedBy: "  ")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
                let value = parts.first ?? String(raw.dropFirst(3))
                var support = "", scope = ""
                for p in parts.dropFirst() {
                    if p.hasPrefix("("), p.hasSuffix(")") {
                        support = String(p.dropFirst().dropLast())
                    } else {
                        scope = p
                    }
                }
                head[key] = (value, support, scope)
                last = key
            } else if trimmed.hasPrefix("|"), let k = last {
                let body = trimmed.dropFirst().trimmingCharacters(in: .whitespaces)
                lines[k] = lines[k].map { $0 + "\n" + body } ?? body
            } else if trimmed.hasPrefix("also asserted:") {
                also = String(trimmed.dropFirst("also asserted:".count))
                    .trimmingCharacters(in: .whitespaces)
            } else if trimmed.hasPrefix("judge:") {
                judge = String(trimmed.dropFirst("judge:".count))
                    .trimmingCharacters(in: .whitespaces)
            }
        }

        guard let a = head["A"], let b = head["B"] else { return nil }
        return PairEvidence(
            a: ClaimSide(label: "A", value: a.0, support: a.1, scope: a.2, line: lines["A"] ?? ""),
            b: ClaimSide(label: "B", value: b.0, support: b.1, scope: b.2, line: lines["B"] ?? ""),
            also: also, judge: judge
        )
    }
}
