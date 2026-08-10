import Foundation

// Shapes modelled from the LIVE API, not from a guess. Every field below was
// observed in an actual response from `GET /api/findings` on 2026-07-15.
// Nullable fields are optional here because the server genuinely emits null for
// them (source / source_ref / memory_id are NULL for non-memory findings, and
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
    let memoryID: String?
    let suggestedAction: String
    let createdAt: String?
    let lane: String            // decision | ambient

    enum CodingKeys: String, CodingKey {
        case id, kind, severity, title, why, source, lane
        case evidencePreview  = "evidence_preview"
        case sourceRef        = "source_ref"
        case memoryID         = "memory_id"
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
        memoryID        = try c.decodeIfPresent(String.self, forKey: .memoryID)
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

    /// "Contradiction: Cross-source contradiction: Itai wedding — …" → drop the
    /// leading check name, which the chip already carries.
    var whyBody: String {
        guard let r = why.range(of: ": ") else { return why }
        return String(why[r.upperBound...])
    }

    var checkName: String {
        guard let r = why.range(of: ": ") else { return kind.capitalized }
        return String(why[..<r.lowerBound])
    }

    /// The precedent line a reasoned dismissal will write, exactly as gold.py
    /// composes it: `"NOT rot: " + clip(finding, 118)`. The server keys off the
    /// audit_log `finding` column, which the API hands back as `whyBody` (the
    /// check name is prepended for the human sentence only). Previewed so the
    /// operator sees the rule before filing it.
    var compiledRule: String { Gold.clip(whyBody, Gold.findingClip) }

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

/// The GOLDEN_RULES compiler's clipping, ported 1:1 from gold.py `_clip` so the
/// composer can preview the exact rule the server will write — same limits, same
/// word-boundary cut, same ellipsis. A preview that clipped differently than the
/// compiler would show the operator a rule they are not actually filing.
enum Gold {
    /// gold.py clips the finding at 118 chars and the dismiss reason at 140.
    static let findingClip = 118
    static let reasonClip  = 140

    static func clip(_ text: String, _ limit: Int) -> String {
        let flat = text.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        if flat.count <= limit { return flat }
        let headSlice = String(flat.prefix(limit - 1))
        var head = headSlice
        if let sp = headSlice.range(of: " ", options: .backwards) {
            head = String(headSlice[..<sp.lowerBound])
        }
        head = head.trimmingCharacters(in: CharacterSet(charactersIn: " ,;:-"))
        if head.isEmpty {
            head = String(flat.prefix(limit - 1)).trimmingCharacters(in: .whitespaces)
        }
        return head + "…"
    }
}

struct FindingsResponse: Decodable {
    let findings: [Finding]
    let summary: FindingsSummary
}

struct Health: Decodable {
    let status: String
    let memories: Int
}

// MARK: - the morning brief (GET /api/brief)
// Shapes modelled 1:1 from helicon.brief.build_brief. Every pillar carries a
// headline the server already composed honestly, so the app never invents a
// number — it renders what the record supports, empty pillars included.

struct Brief: Decodable {
    let truth: Truth
    let continuity: Continuity
    let direction: Direction
    let reflection: Reflection
    let calm: Calm

    struct Truth: Decodable {
        let grade: Double?
        let headline: String
        let noLongerTrustworthy: [Stale]
        enum CodingKeys: String, CodingKey { case grade, headline; case noLongerTrustworthy = "no_longer_trustworthy" }
        struct Stale: Decodable, Identifiable {
            let id: String; let title: String; let confidence: Double
        }
    }
    struct Continuity: Decodable { let headline: String }
    struct Direction: Decodable {
        let headline: String
        let taskClasses: [Pick]
        enum CodingKeys: String, CodingKey { case headline; case taskClasses = "task_classes" }
        struct Pick: Decodable, Identifiable {
            let taskClass: String; let recommendation: String?; let lean: String?; let sufficient: Bool
            var id: String { taskClass }
            enum CodingKeys: String, CodingKey { case taskClass = "task_class", recommendation, lean, sufficient }
        }
    }
    struct Reflection: Decodable {
        let headline: String
        let runsScored: [Run]
        enum CodingKeys: String, CodingKey { case headline; case runsScored = "runs_scored" }
        struct Run: Decodable, Identifiable {
            let runID: String; let model: String; let score: Double; let cost: Double
            var id: String { runID }
            enum CodingKeys: String, CodingKey { case runID = "run_id", model, score, cost }
        }
    }
    struct Calm: Decodable {
        let openExceptions: Int
        let headline: String
        let worthYourJudgment: [Exception]
        enum CodingKeys: String, CodingKey {
            case openExceptions = "open_exceptions", headline
            case worthYourJudgment = "worth_your_judgment"
        }
        struct Exception: Decodable, Identifiable {
            let id: Int; let finding: String; let severity: String
        }
    }
}

struct ConfirmRequest: Encodable {
    let finding_id: Int
    let decision: String
    let notes: String
}

struct ConfirmResponse: Decodable {
    let findingID: Int
    let decision: String
    let killedMemories: [String]
    /// True only when this dismissal carried a reason and the server compiled a
    /// GOLDEN_RULES precedent from it (audit.py returns precedent:true). The app
    /// reports back exactly what the server did, never what it hoped happened.
    let precedent: Bool

    enum CodingKeys: String, CodingKey {
        case findingID   = "finding_id"
        case decision
        case killedMemories = "killed_memories"
        case precedent
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        findingID      = try c.decode(Int.self, forKey: .findingID)
        decision       = try c.decode(String.self, forKey: .decision)
        killedMemories = try c.decodeIfPresent([String].self, forKey: .killedMemories) ?? []
        precedent      = try c.decodeIfPresent(Bool.self, forKey: .precedent) ?? false
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
    let value: String     // "08-14..08-22"
    let support: String   // "1 memory" / "3 memories"
    let scope: String     // "claude-code:memory_status_2026-07-11.md"
    let line: String      // the exact asserting line
}

struct PairEvidence {
    let a: ClaimSide
    let b: ClaimSide
    let also: String?
    let judge: String?

    /// Shape emitted by format_pair_evidence():
    ///   A: {value}   ({n} memories)   {scope}
    ///      | {line_a}
    ///   B: {value}   ({n} memories)   {scope}
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


// --- Workgraph models, salvaged alongside WorkGraphView.swift. The view was
// ported without them in 5db661f and the app has not compiled since.
struct WorkCardsResponse: Decodable {
    let cards: [WorkCard]
    let measurement: WorkMeasurement
}

struct WorkCard: Decodable, Identifiable {
    let id: String
    let intent: String
    let beneficiary: String
    let observableChange: String
    let outcome: String?
    let status: String
    let model: String?
    let harness: String?
    let contextItems: Int
    let evidenceCount: Int
    let nextAction: String?

    enum CodingKeys: String, CodingKey {
        case id, intent, beneficiary, outcome, status, model, harness
        case observableChange = "observable_change"
        case contextItems = "context_items"
        case evidenceCount = "evidence_count"
        case nextAction = "next_action"
    }
}

struct WorkMeasurement: Decodable {
    let workCards: Int
    let openCards: Int
    let linkedRuns: Int
    let contextPackets: Int
    let contextWithMemory: Int
    let declaredSkills: Int
    let reviewedSkillVersions: Int
    let cardsWithAllDeclaredSkillsReviewed: Int
    let cardsWithSkills: Int
    let cardsWithArtifacts: Int
    let verifiedRuns: Int
    let runsWithWallElapsed: Int
    let runsWithTokenUsage: Int
    let cardsWithOutcomeEvidence: Int
    let evidenceReceipts: Int

    enum CodingKeys: String, CodingKey {
        case workCards = "work_cards", openCards = "open_cards", linkedRuns = "linked_runs"
        case contextPackets = "context_packets", contextWithMemory = "context_with_memory", declaredSkills = "declared_skills"
        case reviewedSkillVersions = "reviewed_skill_versions", cardsWithAllDeclaredSkillsReviewed = "cards_with_all_declared_skills_reviewed"
        case cardsWithSkills = "cards_with_skills", cardsWithArtifacts = "cards_with_artifacts", verifiedRuns = "verified_runs", runsWithWallElapsed = "runs_with_wall_elapsed", runsWithTokenUsage = "runs_with_token_usage", cardsWithOutcomeEvidence = "cards_with_outcome_evidence", evidenceReceipts = "evidence_receipts"
    }
}

struct WorkAttentionResponse: Decodable { let attention: [WorkAttention] }

struct WorkAttention: Decodable, Identifiable {
    var id: String { "\(wagerID)-\(action)" }
    let wagerID: String
    let intent: String
    let priority: String
    let action: String
    let reason: String
    enum CodingKeys: String, CodingKey {
        case intent, priority, action, reason
        case wagerID = "wager_id"
    }
}

/// Read-only detail from GET /api/workgraph/cards/{id}. Optional fields are
/// intentional: missing links remain visible rather than decoded as invented
/// empty records.
struct WorkTrace: Decodable {
    let workCard: TraceCard
    let taskRun: TraceRun?
    let contextPacket: TracePacket?
    let skills: [String]
    let skillReviews: [TraceSkillReview]
    let outcomeEvidence: [TraceEvidence]
    let executionEvidence: [TraceEvidence]
    let timeline: [TraceEvent]

    enum CodingKeys: String, CodingKey {
        case workCard = "work_card", taskRun = "task_run", contextPacket = "context_packet"
        case skills, skillReviews = "skill_reviews", outcomeEvidence = "outcome_evidence"
        case executionEvidence = "execution_evidence", timeline
    }
}

struct TraceCard: Decodable {
    let intent: String
    let beneficiary: String
    let outcome: String?
}

struct TraceRun: Decodable {
    let model: String?
    let harness: String?
    let verificationOutcome: String?
    enum CodingKeys: String, CodingKey { case model, harness; case verificationOutcome = "verification_outcome" }
}

struct TracePacket: Decodable {
    let tokenEstimate: Int?
    let includedMemoryItems: [TraceMemory]
    enum CodingKeys: String, CodingKey { case tokenEstimate = "token_estimate", includedMemoryItems = "included_memory_items" }
}
struct TraceMemory: Decodable { let cubeID: String; enum CodingKeys: String, CodingKey { case cubeID = "cube_id" } }

struct TraceSkillReview: Decodable { let skillVersion: String; enum CodingKeys: String, CodingKey { case skillVersion = "skill_version" } }
struct TraceEvidence: Decodable { let kind: String; let reference: String }
struct TraceEvent: Decodable, Identifiable { var id: String { "\(at)-\(kind)-\(label)" }; let at: String; let kind: String; let label: String }

struct WorkLearning: Decodable {
    let evidenceFloor: Int
    let resolvedWorkCards: Int
    let recommendationsWithheld: Bool
    enum CodingKeys: String, CodingKey {
        case evidenceFloor = "evidence_floor"
        case resolvedWorkCards = "resolved_work_cards"
        case recommendationsWithheld = "recommendations_withheld"
    }
}

// MARK: - the morning brief (GET /api/brief)
// Shapes modelled 1:1 from helicon.brief.build_brief. Every pillar carries a
// headline the server already composed honestly, so the app never invents a
// number — it renders what the record supports, empty pillars included.



// Fleet board payloads. Optionals are deliberate: cost is UNKNOWN when a run has
// no cost card, and rendering it as 0 would make unmeasured work look free.
struct ClaimRow: Decodable, Identifiable {
    let id: String
    let claimed: String
    let written: Int
    let cost: Double?
    let costKnown: Bool
    let level: String
    let why: String
    enum CodingKeys: String, CodingKey {
        case id, claimed, written, cost, level, why
        case costKnown = "cost_known"
    }
}

struct ClaimsPayload: Decodable {
    let claims: [ClaimRow]
    let counts: [String: Int]
    let levels: [String]
    let meaning: [String: String]
    let total: Int
    let headline: String
}

struct FleetPayload: Decodable {
    let runningCount: Int
    let observedCount: Int
    enum CodingKeys: String, CodingKey {
        case runningCount = "running_count"
        case observedCount = "observed_count"
    }
}
