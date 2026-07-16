import SwiftUI
import AppKit

/// The cockpit: queue | finding in focus | evidence. Keyboard-first —
/// J/K move, A and D are verdicts, every action shows its key.
struct QueueView: View {
    @EnvironmentObject var store: Store
    @FocusState private var focused: Bool

    var body: some View {
        ZStack {
            WashBackground()
            VStack(spacing: 0) {
                TopBar()
                Divider().overlay(Wash.line)
                content
                Divider().overlay(Wash.line)
                VerdictBar()
            }
        }
        .frame(minWidth: 1040, minHeight: 620)
        .focusable()
        .focusEffectDisabled()
        .focused($focused)
        .onAppear { focused = true; store.start() }
        // Linear-triage keys. Arrows mirror J/K so the mouse-free loop works
        // for anyone who has not learned vim bindings yet.
        .onKeyPress(.init("j")) { store.move(1);  return .handled }
        .onKeyPress(.init("k")) { store.move(-1); return .handled }
        .onKeyPress(.downArrow) { store.move(1);  return .handled }
        .onKeyPress(.upArrow)   { store.move(-1); return .handled }
        .onKeyPress(.init("a")) { verdict("acted"); return .handled }
        // D no longer fires a blind dismissal — it opens the ruling composer, so
        // the reason that turns "not rot" into law is written before the row
        // clears. A dismissal with no reason compiled to nothing.
        .onKeyPress(.init("d")) { beginDismiss(); return .handled }
        .onKeyPress(.init("r")) { Task { await store.refresh() }; return .handled }
        // The ruling composer: name why it is not rot, watch it compile into the
        // law. Presented over the cockpit so the queue stays in view behind it.
        .sheet(item: $store.composing) { finding in
            ReasonComposer(finding: finding).environmentObject(store)
        }
    }

    private func verdict(_ decision: String) {
        guard let f = store.selected else { return }
        Task { await store.confirm(f, decision: decision) }
    }

    private func beginDismiss() {
        guard let f = store.selected else { return }
        store.beginDismiss(f)
    }

    @ViewBuilder
    private var content: some View {
        switch store.connection {
        case .down(let reason) where store.findings.isEmpty:
            DisconnectedState(reason: reason)
        case .connecting where store.findings.isEmpty:
            VStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Reading the queue…")
                    .font(.iface(11))
                    .foregroundStyle(Wash.muted)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        default:
            if store.findings.isEmpty {
                EmptyQueue()
            } else {
                HStack(spacing: 0) {
                    QueueRail().frame(width: 340)
                    Divider().overlay(Wash.line)
                    FocusPanel().frame(maxWidth: .infinity)
                    Divider().overlay(Wash.line)
                    EvidencePanel().frame(width: 330)
                }
            }
        }
    }
}

// MARK: - top bar

private struct TopBar: View {
    @EnvironmentObject var store: Store

    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: 7) {
                Image(systemName: "mountain.2.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(Wash.slate)
                Text("Review Queue")
                    .font(.display(15, .medium))
                    .foregroundStyle(Wash.ink)
            }

            // Counts are shown only when they were actually read. A "0" while
            // the API is down would be a number the app cannot stand behind.
            if store.connection.isLive {
                Text("\(store.openCount)")
                    .font(.data(11, .semibold))
                    .foregroundStyle(store.hasCritical ? Wash.critical : Wash.accent)
                    .padding(.horizontal, 7).padding(.vertical, 2)
                    .background(Capsule().fill(
                        (store.hasCritical ? Wash.critical : Wash.accent).opacity(0.10)))

                if store.summary.critical > 0 {
                    Chip(text: "\(store.summary.critical) critical", color: Wash.critical, filled: true)
                }
            }

            Spacer()

            // The aftermath of a ruling: shown only when the server actually
            // compiled a precedent, and cleared after a beat so it never becomes
            // a permanent boast. Calm slate-blue, not an alarm color.
            if let flash = store.lawFlash {
                HStack(spacing: 5) {
                    Image(systemName: "seal.fill")
                        .font(.system(size: 10))
                        .foregroundStyle(Wash.good)
                    Text("compiled into the law")
                        .font(.iface(10.5, .medium))
                        .foregroundStyle(Wash.good)
                }
                .help("NOT rot: \(flash.rule)")
                .task(id: flash) {
                    try? await Task.sleep(for: .seconds(6))
                    if store.lawFlash == flash { store.lawFlash = nil }
                }
            } else if let err = store.actionError {
                Text(err)
                    .font(.iface(10.5))
                    .foregroundStyle(Wash.critical)
                    .lineLimit(1)
                    .help(err)
            }

            switch store.connection {
            case .live(let memories):
                HStack(spacing: 5) {
                    Circle().fill(Wash.good).frame(width: 5, height: 5)
                    Text("live · \(memories.formatted()) memories")
                        .font(.iface(10))
                        .foregroundStyle(Wash.muted)
                }
            case .connecting:
                Text("connecting…").font(.iface(10)).foregroundStyle(Wash.faint)
            case .down:
                HStack(spacing: 5) {
                    Circle().fill(Wash.critical).frame(width: 5, height: 5)
                    Text("API down · rows may be stale")
                        .font(.iface(10))
                        .foregroundStyle(Wash.critical)
                }
            }
        }
        // The window is fullSizeContentView with a transparent titlebar, so the
        // content starts under the traffic lights. Inset past them rather than
        // give the instrument a stock titlebar.
        .padding(.leading, 82)
        .padding(.trailing, 16)
        .frame(height: 44)
    }
}

// MARK: - left rail

private struct QueueRail: View {
    @EnvironmentObject var store: Store

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14, pinnedViews: [.sectionHeaders]) {
                    ForEach(store.groups, id: \.kind) { group in
                        Section {
                            ForEach(group.items) { f in
                                QueueCard(finding: f, selected: f.id == store.selection)
                                    .id(f.id)
                                    .onTapGesture { store.selection = f.id }
                            }
                        } header: {
                            HStack {
                                RailLabel(text: group.kind)
                                Spacer()
                                Text("\(group.items.count)")
                                    .font(.data(9, .medium))
                                    .foregroundStyle(Wash.faint)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 5)
                            .background(Wash.paper.opacity(0.94))
                        }
                    }
                }
                .padding(.vertical, 8)
            }
            .onChange(of: store.selection) { _, new in
                guard let new else { return }
                withAnimation(.easeOut(duration: 0.14)) {
                    proxy.scrollTo(new, anchor: .center)
                }
            }
        }
    }
}

private struct QueueCard: View {
    let finding: Finding
    let selected: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            // severity spine
            RoundedRectangle(cornerRadius: 1.5)
                .fill(Wash.severity(finding.severity))
                .frame(width: 2.5)

            VStack(alignment: .leading, spacing: 5) {
                Text(finding.title)
                    .font(.iface(11.5, selected ? .semibold : .regular))
                    .foregroundStyle(selected ? Wash.ink : Wash.ink70)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                HStack(spacing: 5) {
                    Chip(text: finding.severity, color: Wash.severity(finding.severity))
                    if !finding.isConfirmable {
                        Chip(text: "read-only", color: Wash.faint)
                    }
                    Spacer()
                    Text(finding.age)
                        .font(.data(9))
                        .foregroundStyle(Wash.faint)
                }
            }
        }
        .padding(.vertical, 9)
        .padding(.horizontal, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                .fill(selected ? Wash.boneRaised : Wash.bone.opacity(0.55))
        )
        .overlay(
            RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                .strokeBorder(selected ? Wash.line2 : .clear, lineWidth: 1)
        )
        .padding(.horizontal, 10)
        .contentShape(Rectangle())
    }
}

// MARK: - center: the finding in focus

private struct FocusPanel: View {
    @EnvironmentObject var store: Store

    var body: some View {
        if let f = store.selected {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 9) {
                        HStack(spacing: 6) {
                            Chip(text: f.checkName, color: Wash.severity(f.severity), filled: true)
                            Chip(text: f.kind, color: Wash.slate)
                            Chip(text: f.lane, color: Wash.mist)
                            Spacer()
                            Text(f.id)
                                .font(.data(9))
                                .foregroundStyle(Wash.faint)
                                .textSelection(.enabled)
                        }

                        Text(f.title)
                            .font(.display(21, .regular))
                            .foregroundStyle(Wash.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .textSelection(.enabled)

                        Text(f.whyBody)
                            .font(.iface(12.5))
                            .foregroundStyle(Wash.ink70)
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                            .textSelection(.enabled)
                    }

                    // A contradiction's receipt is the two conflicting lines side
                    // by side. When the evidence parses into that shape, show the
                    // diff; when it does not, the raw receipt is in the inspector.
                    if let pair = PairEvidence.parse(f.evidencePreview) {
                        ClaimDiff(pair: pair)
                    } else if !f.evidencePreview.isEmpty {
                        VStack(alignment: .leading, spacing: 7) {
                            RailLabel(text: "evidence")
                            Text(f.evidencePreview)
                                .font(.data(10.5))
                                .foregroundStyle(Wash.ink70)
                                .lineSpacing(2.5)
                                .fixedSize(horizontal: false, vertical: true)
                                .textSelection(.enabled)
                                .padding(12)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                                    .fill(Wash.bone))
                                .overlay(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                                    .strokeBorder(Wash.line, lineWidth: 1))
                        }
                    } else {
                        VStack(alignment: .leading, spacing: 5) {
                            RailLabel(text: "evidence")
                            Text("This finding carries no evidence payload. The server sent an empty evidence_preview — nothing is being hidden, and nothing is being invented to fill the space.")
                                .font(.iface(11))
                                .foregroundStyle(Wash.faint)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }

                    if let reason = f.notConfirmableReason {
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "hand.raised.fill")
                                .font(.system(size: 10))
                                .foregroundStyle(Wash.stale)
                            Text(reason)
                                .font(.iface(11))
                                .foregroundStyle(Wash.muted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(11)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                            .fill(Wash.stale.opacity(0.07)))
                    }
                }
                .padding(22)
            }
        } else {
            Color.clear
        }
    }
}

/// Conflicting claims, diffed: value + support + source + the exact line, per side.
private struct ClaimDiff: View {
    let pair: PairEvidence

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            RailLabel(text: "conflicting claims")
            HStack(alignment: .top, spacing: 10) {
                SideCard(side: pair.a, tone: Wash.critical)
                SideCard(side: pair.b, tone: Wash.accent)
            }
            if let also = pair.also {
                Text("also asserted: \(also)")
                    .font(.data(10))
                    .foregroundStyle(Wash.faint)
            }
            if let judge = pair.judge {
                HStack(alignment: .top, spacing: 7) {
                    Image(systemName: "scale.3d")
                        .font(.system(size: 10))
                        .foregroundStyle(Wash.slate)
                    Text(judge)
                        .font(.iface(11))
                        .foregroundStyle(Wash.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                    .fill(Wash.mist.opacity(0.20)))
            }
        }
    }

    private struct SideCard: View {
        let side: ClaimSide
        let tone: Color

        var body: some View {
            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 6) {
                    Text(side.label)
                        .font(.data(9, .bold))
                        .foregroundStyle(tone)
                    Spacer()
                    if !side.support.isEmpty {
                        Text(side.support)
                            .font(.data(9))
                            .foregroundStyle(Wash.faint)
                    }
                }

                Text(side.value)
                    .font(.display(17, .medium))
                    .foregroundStyle(Wash.ink)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)

                if !side.scope.isEmpty {
                    Text(side.scope)
                        .font(.data(9))
                        .foregroundStyle(Wash.slate)
                        .lineLimit(2)
                        .textSelection(.enabled)
                }

                if !side.line.isEmpty {
                    Text(side.line)
                        .font(.data(10))
                        .foregroundStyle(Wash.ink70)
                        .lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(Wash.paperDeep.opacity(0.55)))
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                .fill(Wash.bone))
            .overlay(
                RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                    .strokeBorder(tone.opacity(0.28), lineWidth: 1)
            )
        }
    }
}

// MARK: - right: evidence / provenance inspector

private struct EvidencePanel: View {
    @EnvironmentObject var store: Store

    var body: some View {
        if let f = store.selected {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    RailLabel(text: "provenance")

                    Row(label: "source", value: f.source ?? "—", mono: true)
                    Row(label: "source ref", value: f.sourceRef ?? "—", mono: true)
                    Row(label: "memory id", value: f.memoryID ?? "— (not memory-backed)", mono: true)
                    Row(label: "filed", value: Stamp.absolute(f.createdAt), mono: true)
                    Row(label: "suggested", value: f.suggestedAction, mono: true)
                    Row(label: "lane", value: f.lane, mono: true)

                    if let ref = f.sourceRef, FileManager.default.fileExists(atPath: ref) {
                        Button {
                            NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: ref)])
                        } label: {
                            HStack(spacing: 5) {
                                Image(systemName: "folder")
                                    .font(.system(size: 9))
                                Text("Reveal in Finder")
                                    .font(.iface(10.5, .medium))
                            }
                            .foregroundStyle(Wash.accent)
                        }
                        .buttonStyle(.plain)
                    }

                    if !f.evidencePreview.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            RailLabel(text: "raw receipt")
                            Text(f.evidencePreview)
                                .font(.data(9.5))
                                .foregroundStyle(Wash.ink70)
                                .lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                                .textSelection(.enabled)
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(Wash.paperDeep.opacity(0.5)))
                        }
                    }

                    Spacer(minLength: 0)
                }
                .padding(16)
            }
        } else {
            Color.clear
        }
    }

    private struct Row: View {
        let label: String
        let value: String
        var mono: Bool = false

        var body: some View {
            VStack(alignment: .leading, spacing: 3) {
                Text(label.uppercased())
                    .font(.iface(8.5, .semibold))
                    .tracking(0.12 * 8.5)
                    .foregroundStyle(Wash.faint)
                Text(value)
                    .font(mono ? .data(10) : .iface(11))
                    .foregroundStyle(Wash.ink70)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - verdict bar

private struct VerdictBar: View {
    @EnvironmentObject var store: Store

    private var canAct: Bool {
        guard let f = store.selected else { return false }
        return f.isConfirmable && store.connection.isLive && !store.busy.contains(f.id)
    }

    var body: some View {
        HStack(spacing: 14) {
            Verdict(key: "A", label: "Acted", tone: Wash.accent, enabled: canAct) {
                act("acted")
            }
            Verdict(key: "D", label: "Not rot · rule", tone: Wash.slate, enabled: canAct) {
                if let f = store.selected { store.beginDismiss(f) }
            }

            Divider().frame(height: 15).overlay(Wash.line)

            HStack(spacing: 5) {
                KeyCap(key: "J"); KeyCap(key: "K")
                Text("move").font(.iface(10)).foregroundStyle(Wash.muted)
            }
            HStack(spacing: 5) {
                KeyCap(key: "R")
                Text("refresh").font(.iface(10)).foregroundStyle(Wash.muted)
            }

            Spacer()

            if let i = store.selectedIndex {
                Text("\(i + 1) of \(store.findings.count)")
                    .font(.data(10))
                    .foregroundStyle(Wash.faint)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 9)
        .background(Wash.bone.opacity(0.6))
    }

    private func act(_ decision: String) {
        guard let f = store.selected else { return }
        Task { await store.confirm(f, decision: decision) }
    }

    private struct Verdict: View {
        let key: String
        let label: String
        let tone: Color
        let enabled: Bool
        let action: () -> Void

        var body: some View {
            Button(action: action) {
                HStack(spacing: 6) {
                    KeyCap(key: key)
                    Text(label)
                        .font(.iface(11, .medium))
                        .foregroundStyle(enabled ? tone : Wash.faint)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(enabled ? tone.opacity(0.08) : .clear))
            }
            .buttonStyle(.plain)
            .disabled(!enabled)
            .opacity(enabled ? 1 : 0.45)
        }
    }
}

// MARK: - honest states

/// No rows, no placeholders, and the exact command that fixes it.
struct DisconnectedState: View {
    let reason: String

    var body: some View {
        VStack(spacing: 13) {
            Image(systemName: "bolt.horizontal.circle")
                .font(.system(size: 26, weight: .light))
                .foregroundStyle(Wash.critical)
            Text("Not connected to helicon serve")
                .font(.display(17, .medium))
                .foregroundStyle(Wash.ink)
            Text(reason)
                .font(.iface(11.5))
                .foregroundStyle(Wash.muted)
                .multilineTextAlignment(.center)
            Text("The queue is empty because nothing could be read — not because\nthere is nothing to review. No sample rows are shown by design.")
                .font(.iface(11))
                .foregroundStyle(Wash.faint)
                .multilineTextAlignment(.center)
            Text("cd ~/CODE/helicon && python3 -m uvicorn helicon.api.app:app --port 8420")
                .font(.data(10))
                .foregroundStyle(Wash.ink70)
                .padding(10)
                .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Wash.paperDeep))
                .textSelection(.enabled)
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EmptyQueue: View {
    var body: some View {
        VStack(spacing: 9) {
            Image(systemName: "checkmark.seal")
                .font(.system(size: 24, weight: .light))
                .foregroundStyle(Wash.good)
            Text("Nothing needs your ruling")
                .font(.display(17, .medium))
                .foregroundStyle(Wash.ink)
            Text("The decision lane is clear. Ambient findings are auto-managed.")
                .font(.iface(11.5))
                .foregroundStyle(Wash.muted)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - the ruling composer

/// The one beat that makes the cockpit worth showing: name why a finding is not
/// rot, and watch the reason compile into GOLDEN_RULES. A dismissal is the only
/// verdict that can become law — but only if it carries a reason (gold.py emits
/// a precedent for `dismissed AND dismiss_reason`, nothing else). So the reason
/// is not a nicety to skip; it IS the rule. This sheet says what the reason buys
/// before asking for it, previews the exact line the compiler will write, and
/// reports back what the server actually did — never what it hoped.
struct ReasonComposer: View {
    let finding: Finding
    @EnvironmentObject var store: Store

    @State private var reason = ""
    @State private var busy = false
    @State private var error: String?
    /// nil while composing; set to the server's precedent verdict once filed.
    @State private var filed: Bool?
    @FocusState private var fieldFocused: Bool

    private var trimmed: String {
        reason.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    private var over: Bool { trimmed.count > Gold.reasonClip }

    var body: some View {
        ZStack {
            Wash.paper
            RadialGradient(colors: [Wash.mist.opacity(0.30), .clear],
                           center: UnitPoint(x: 0.92, y: -0.10),
                           startRadius: 0, endRadius: 460)
                .allowsHitTesting(false)
            if let filed {
                filedState(precedent: filed)
            } else {
                composeState
            }
        }
        .frame(width: 560)
        .fixedSize(horizontal: false, vertical: true)
        .onAppear {
            fieldFocused = true
            // Screenshot/demo affordance only: populate the reason so the
            // "compiles to" preview is visible in a headless capture. Never
            // fabricates in normal use — the var is unset unless explicitly given.
            if reason.isEmpty,
               let seed = ProcessInfo.processInfo.environment["HELICON_REASON"] {
                reason = seed
            }
        }
    }

    // MARK: compose

    private var composeState: some View {
        VStack(alignment: .leading, spacing: 15) {
            // Which finding is being ruled on, in its own chips.
            HStack(spacing: 6) {
                Chip(text: finding.checkName, color: Wash.severity(finding.severity), filled: true)
                Chip(text: finding.kind, color: Wash.slate)
                Spacer()
                Text(finding.id)
                    .font(.data(9))
                    .foregroundStyle(Wash.faint)
                    .textSelection(.enabled)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Why is this not rot?")
                    .font(.display(21, .regular))
                    .foregroundStyle(Wash.ink)
                Text("Your reason becomes law. Helicon files it under the precedents in GOLDEN_RULES, with a receipt, so this never alarms again. Rule without one and the finding just closes, compiling to nothing.")
                    .font(.iface(12))
                    .foregroundStyle(Wash.muted)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            // The reason field.
            ZStack(alignment: .topLeading) {
                if reason.isEmpty {
                    Text("selector false positive: place-as-person, fixed same hour")
                        .font(.iface(12.5))
                        .foregroundStyle(Wash.faint)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .allowsHitTesting(false)
                }
                TextEditor(text: $reason)
                    .font(.iface(12.5))
                    .foregroundStyle(Wash.ink)
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 66)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .focused($fieldFocused)
            }
            .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                .fill(Wash.boneRaised))
            .overlay(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                .strokeBorder(fieldFocused ? Wash.line2 : Wash.line, lineWidth: 1))

            Text(over
                 ? "\(trimmed.count)/\(Gold.reasonClip) · the compiled rule clips at \(Gold.reasonClip)"
                 : "\(trimmed.count)/\(Gold.reasonClip)")
                .font(.data(10))
                .foregroundStyle(over ? Wash.stale : Wash.faint)

            // What the finding becomes — gold.py's exact shape, so the operator
            // reads the rule before writing it.
            if !trimmed.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    RailLabel(text: "compiles to")
                    Text("NOT rot: \(finding.compiledRule)")
                        .font(.data(11))
                        .foregroundStyle(Wash.ink)
                        .lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("why: \(Gold.clip(trimmed, Gold.reasonClip))")
                        .font(.data(11))
                        .foregroundStyle(Wash.muted)
                        .lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                    .fill(Wash.accentDim))
                .overlay(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                    .strokeBorder(Wash.line, lineWidth: 1))
            }

            if let error {
                Text("Not filed: \(error)")
                    .font(.iface(11))
                    .foregroundStyle(Wash.critical)
                    .fixedSize(horizontal: false, vertical: true)
            }

            // Actions.
            HStack(spacing: 10) {
                Button { Task { await file(withReason: true) } } label: {
                    Text(busy ? "Filing…" : "File as precedent")
                        .font(.iface(12, .semibold))
                        .foregroundStyle(Wash.bone)
                        .padding(.horizontal, 14).padding(.vertical, 8)
                        .background(RoundedRectangle(cornerRadius: 9, style: .continuous)
                            .fill(trimmed.isEmpty ? Wash.accent.opacity(0.4) : Wash.accent))
                }
                .buttonStyle(.plain)
                .disabled(busy || trimmed.isEmpty)
                .keyboardShortcut(.return, modifiers: .command)

                Button { store.cancelDismiss() } label: {
                    Text("Back")
                        .font(.iface(11.5))
                        .foregroundStyle(Wash.muted)
                        .padding(.horizontal, 8).padding(.vertical, 8)
                }
                .buttonStyle(.plain)
                .disabled(busy)
                .keyboardShortcut(.cancelAction)

                Spacer()

                Button { Task { await file(withReason: false) } } label: {
                    Text("Dismiss without a reason")
                        .font(.iface(11))
                        .foregroundStyle(Wash.faint)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.plain)
                .disabled(busy)
                .help("Closes the finding without writing a rule. It compiles to nothing.")
            }
        }
        .padding(24)
    }

    // MARK: filed

    @ViewBuilder
    private func filedState(precedent: Bool) -> some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack(spacing: 9) {
                Image(systemName: precedent ? "seal.fill" : "tray.and.arrow.down")
                    .font(.system(size: 17))
                    .foregroundStyle(precedent ? Wash.good : Wash.muted)
                Text(precedent ? "Compiled into the law" : "Dismissed")
                    .font(.display(20, .medium))
                    .foregroundStyle(Wash.ink)
            }

            if precedent {
                VStack(alignment: .leading, spacing: 5) {
                    RailLabel(text: "now in GOLDEN_RULES · precedents")
                    Text("NOT rot: \(finding.compiledRule)")
                        .font(.data(11))
                        .foregroundStyle(Wash.ink)
                        .lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                    Text("why: \(Gold.clip(trimmed, Gold.reasonClip))")
                        .font(.data(11))
                        .foregroundStyle(Wash.muted)
                        .lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                    .fill(Wash.good.opacity(0.08)))
                .overlay(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                    .strokeBorder(Wash.good.opacity(0.25), lineWidth: 1))

                Text("The ruling carries a receipt. The same rot re-alarms if it ever returns; until then, Helicon stays quiet about it.")
                    .font(.iface(11.5))
                    .foregroundStyle(Wash.muted)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("The finding is closed and will not refile. It compiled to no rule — a dismissal only becomes law when it carries a reason.")
                    .font(.iface(11.5))
                    .foregroundStyle(Wash.muted)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack {
                Spacer()
                Button { store.cancelDismiss() } label: {
                    Text("Done")
                        .font(.iface(12, .semibold))
                        .foregroundStyle(Wash.bone)
                        .padding(.horizontal, 16).padding(.vertical, 8)
                        .background(RoundedRectangle(cornerRadius: 9, style: .continuous)
                            .fill(Wash.accent))
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
    }

    // MARK: file

    private func file(withReason: Bool) async {
        busy = true
        error = nil
        let notes = withReason ? trimmed : ""
        let res = await store.confirm(finding, decision: "dismissed", notes: notes)
        busy = false
        guard let res else {
            // dismiss_finding refuses an already-decided finding; keep the sheet
            // open and say so rather than pretend the ruling landed.
            error = store.actionError ?? "could not file this ruling"
            store.actionError = nil
            return
        }
        if withReason {
            // Stay on the success card so the moment is visible: the reason
            // became law (or honestly did not).
            filed = res.precedent
        } else {
            // A reasonless dismissal closes quietly, like the web.
            store.cancelDismiss()
        }
    }
}
