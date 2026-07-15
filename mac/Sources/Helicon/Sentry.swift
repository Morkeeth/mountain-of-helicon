import SwiftUI
import AppKit

/// The bar glyph. Drawn as a non-template NSImage so the critical state can
/// carry judgment red — a template image would be flattened to monochrome by
/// the menu bar and the one signal that matters would be lost.
@MainActor
func sentryImage(count: Int, critical: Bool, live: Bool) -> NSImage {
    let tint: NSColor = !live
        ? NSColor.tertiaryLabelColor
        : (critical
            ? NSColor(srgbRed: 0xA9/255.0, green: 0x4A/255.0, blue: 0x3D/255.0, alpha: 1) // JUDGMENT RED
            : NSColor.labelColor)

    let symbolName = !live ? "mountain.2" : (critical ? "mountain.2.fill" : "mountain.2")
    let base = NSImage.SymbolConfiguration(pointSize: 13, weight: critical ? .semibold : .regular)
    let cfg = base.applying(NSImage.SymbolConfiguration(paletteColors: [tint]))
    let symbol = NSImage(systemSymbolName: symbolName, accessibilityDescription: "Mount Helicon")?
        .withSymbolConfiguration(cfg)
    guard let symbol else { return NSImage() }

    // Disconnected shows no number: a count we cannot verify is a lie.
    let label = live ? "\(count)" : "–"
    let font = NSFont.monospacedDigitSystemFont(ofSize: 11.5, weight: critical ? .semibold : .medium)
    let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: tint]
    let text = NSAttributedString(string: label, attributes: attrs)
    let textSize = text.size()

    let gap: CGFloat = 3
    let height: CGFloat = 18
    let width = symbol.size.width + gap + ceil(textSize.width)

    let image = NSImage(size: NSSize(width: width, height: height))
    image.lockFocus()
    symbol.draw(in: NSRect(x: 0,
                           y: (height - symbol.size.height) / 2,
                           width: symbol.size.width,
                           height: symbol.size.height))
    text.draw(at: NSPoint(x: symbol.size.width + gap,
                          y: (height - textSize.height) / 2))
    image.unlockFocus()
    image.isTemplate = false
    return image
}

/// The dropdown: a mini console, not a menu. Every number here is read from the
/// live API — there is no cached or synthetic value on this panel.
struct SentryPanel: View {
    @EnvironmentObject var store: Store

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().overlay(Wash.line)

            switch store.connection {
            case .down(let reason):
                disconnected(reason)
            case .connecting:
                Text("Connecting to helicon serve…")
                    .font(.iface(11))
                    .foregroundStyle(Wash.muted)
                    .padding(14)
            case .live(let memories):
                liveBody(memories: memories)
            }

            Divider().overlay(Wash.line)
            footer
        }
        .frame(width: 292)
        .background(Wash.bone)
    }

    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: "mountain.2.fill")
                .font(.system(size: 11))
                .foregroundStyle(Wash.slate)
            Text("Mount Helicon")
                .font(.display(13, .medium))
                .foregroundStyle(Wash.ink)
            Spacer()
            Circle()
                .fill(store.connection.isLive ? Wash.good : Wash.critical)
                .frame(width: 5, height: 5)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
    }

    private func liveBody(memories: Int) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // The hero number: what needs a human ruling.
            HStack(alignment: .firstTextBaseline, spacing: 9) {
                Text("\(store.openCount)")
                    .font(.display(38, .light))
                    .foregroundStyle(store.hasCritical ? Wash.critical : Wash.ink)
                    .monospacedDigit()
                VStack(alignment: .leading, spacing: 1) {
                    Text("need your ruling")
                        .font(.iface(12, .medium))
                        .foregroundStyle(Wash.ink70)
                    Text("\(store.summary.ambient) ambient, auto-managed")
                        .font(.iface(10))
                        .foregroundStyle(Wash.faint)
                }
                Spacer()
            }

            if store.hasCritical || store.summary.warning > 0 {
                HStack(spacing: 6) {
                    if store.summary.critical > 0 {
                        Chip(text: "\(store.summary.critical) critical", color: Wash.critical, filled: true)
                    }
                    if store.summary.warning > 0 {
                        Chip(text: "\(store.summary.warning) warning", color: Wash.stale)
                    }
                    if let high = store.summary.bySeverity["high"], high > 0 {
                        Chip(text: "\(high) high", color: Wash.accent)
                    }
                    Spacer()
                }
            }

            // Drift classes actually present, largest first.
            let kinds = store.summary.byKind.sorted { ($0.value, $1.key) > ($1.value, $0.key) }
            if !kinds.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    RailLabel(text: "drift classes")
                    ForEach(kinds.prefix(4), id: \.key) { k, v in
                        HStack(spacing: 6) {
                            Text(k)
                                .font(.data(10))
                                .foregroundStyle(Wash.muted)
                            Spacer()
                            Text("\(v)")
                                .font(.data(10, .medium))
                                .foregroundStyle(Wash.ink70)
                        }
                    }
                }
            }

            Button {
                NSApp.setActivationPolicy(.regular)
                Cockpit.shared.show()
            } label: {
                HStack(spacing: 6) {
                    Text("Review \(store.openCount)")
                        .font(.iface(12, .semibold))
                    Image(systemName: "arrow.right")
                        .font(.system(size: 9, weight: .semibold))
                    Spacer()
                }
                .foregroundStyle(Wash.bone)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity)
                .background(RoundedRectangle(cornerRadius: Wash.radiusSm, style: .continuous)
                    .fill(store.hasCritical ? Wash.critical : Wash.accent))
            }
            .buttonStyle(.plain)

            Text("\(memories.formatted()) memories indexed")
                .font(.data(9.5))
                .foregroundStyle(Wash.faint)
        }
        .padding(14)
    }

    private func disconnected(_ reason: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "bolt.horizontal.circle")
                    .font(.system(size: 11))
                    .foregroundStyle(Wash.critical)
                Text("Not connected")
                    .font(.iface(12, .semibold))
                    .foregroundStyle(Wash.critical)
            }
            Text(reason)
                .font(.iface(10.5))
                .foregroundStyle(Wash.muted)
                .fixedSize(horizontal: false, vertical: true)
            Text("No counts are shown because none can be verified.")
                .font(.iface(10))
                .foregroundStyle(Wash.faint)
                .fixedSize(horizontal: false, vertical: true)
            Text("python3 -m uvicorn helicon.api.app:app --port 8420")
                .font(.data(9.5))
                .foregroundStyle(Wash.ink70)
                .padding(7)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(Wash.paperDeep))
                .textSelection(.enabled)
        }
        .padding(14)
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Image(systemName: "lock.fill")
                .font(.system(size: 8))
                .foregroundStyle(Wash.faint)
            Text("local · BYOK")
                .font(.iface(9.5))
                .foregroundStyle(Wash.faint)
            Spacer()
            if let t = store.lastRefresh {
                Text(Stamp.relative(t))
                    .font(.iface(9.5))
                    .foregroundStyle(Wash.faint)
            }
            Button("Quit") { NSApp.terminate(nil) }
                .buttonStyle(.plain)
                .font(.iface(9.5))
                .foregroundStyle(Wash.muted)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }
}
