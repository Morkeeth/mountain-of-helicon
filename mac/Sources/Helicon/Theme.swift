import SwiftUI

/// Alpine Wash — the locked visual identity, ported 1:1 from web/helicon-tokens.css.
/// The six named brand colors and nothing else; no new color is invented here.
enum Wash {
    // ground & surfaces
    static let paper      = Color(hex: 0xECE4D8)   // PAPER — app ground
    static let paperDeep  = Color(hex: 0xE2D8C8)   // recessed
    static let bone       = Color(hex: 0xF4EFE7)   // BONE — card
    static let boneRaised = Color(hex: 0xFAF7F0)   // raised card

    // ink — one navy hue at varying weight
    static let ink        = Color(hex: 0x17283A)   // INK NAVY — primary text
    static let ink70      = Color(hex: 0x17283A).opacity(0.68)
    static let muted      = Color(hex: 0x4E6173)   // labels
    static let faint      = Color(hex: 0x17283A).opacity(0.34)
    static let slate      = Color(hex: 0x465B6F)   // SLATE BLUE
    static let mist       = Color(hex: 0xAEBFCC)   // MIST BLUE

    // semantic signals — the world is blue; orange is improvement ONLY;
    // judgment red is a whisper, reserved for genuine critical alarms.
    static let accent     = Color(hex: 0x223A4E)   // primary action / counts
    static let accentDim  = Color(hex: 0x223A4E).opacity(0.09)
    static let improve    = Color(hex: 0xC67C3E)   // improvement / gains only
    static let stale      = Color(hex: 0xC6963F)   // warning — amber, sparing
    static let critical   = Color(hex: 0xA94A3D)   // JUDGMENT RED — genuine alarms
    static let good       = Color(hex: 0x3F627D)   // connected — calm slate-blue

    // hairlines
    static let line       = Color(hex: 0x17283A).opacity(0.10)
    static let line2      = Color(hex: 0x17283A).opacity(0.16)

    // shape
    static let radius: CGFloat   = 18
    static let radiusSm: CGFloat = 12

    /// The one place severity becomes color. `critical` earns judgment red
    /// (that is what the token reserves it for, and what the sentry signals on);
    /// everything else stays in the calm blue/amber world.
    static func severity(_ s: String) -> Color {
        switch s {
        case "critical":         return critical
        case "high":             return accent
        case "warning", "medium": return stale
        default:                 return faint
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red:     Double((hex >> 16) & 0xFF) / 255,
                  green:   Double((hex >> 8)  & 0xFF) / 255,
                  blue:    Double( hex        & 0xFF) / 255,
                  opacity: 1)
    }
}

/// The brand type stack is web-font-only (Fraunces / Bricolage Grotesque / IBM
/// Plex Mono) and none of the three are installed on this machine. The design
/// doc lists web fonts as a native anti-pattern, so each brand face maps to its
/// closest native counterpart rather than being bundled.
extension Font {
    /// Fraunces → New York. Display, headings, and hero numbers.
    static func display(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .serif)
    }
    /// Bricolage Grotesque → SF Pro. Interface text.
    static func iface(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .default)
    }
    /// IBM Plex Mono → SF Mono. Data, receipts, raw claim text.
    static func data(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}

/// The watercolor ground: soft washes bleeding from the corners over paper.
/// Atmosphere, not decoration — same two gradients the dashboard body carries.
struct WashBackground: View {
    var body: some View {
        ZStack {
            Wash.paper
            RadialGradient(colors: [Wash.mist.opacity(0.34), .clear],
                           center: UnitPoint(x: 0.86, y: -0.06),
                           startRadius: 0, endRadius: 680)
            RadialGradient(colors: [Wash.slate.opacity(0.16), .clear],
                           center: UnitPoint(x: -0.04, y: 1.10),
                           startRadius: 0, endRadius: 560)
        }
        .ignoresSafeArea()
    }
}

// MARK: - shared small pieces

/// The one consistent state chip, used identically in queue, detail, and menu.
struct Chip: View {
    let text: String
    var color: Color = Wash.muted
    var filled: Bool = false

    var body: some View {
        Text(text.uppercased())
            .font(.iface(9, .semibold))
            .tracking(0.09 * 9)
            .foregroundStyle(filled ? Wash.bone : color)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(
                Capsule().fill(filled ? color : color.opacity(0.10))
            )
            .overlay(
                Capsule().strokeBorder(color.opacity(filled ? 0 : 0.22), lineWidth: 0.5)
            )
            .fixedSize()
    }
}

/// Superhuman-style inline shortcut hint — every action shows its key.
struct KeyCap: View {
    let key: String
    var body: some View {
        Text(key)
            .font(.data(9, .semibold))
            .foregroundStyle(Wash.ink70)
            .frame(minWidth: 15)
            .padding(.horizontal, 4)
            .padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(Wash.paperDeep)
                    .overlay(RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .strokeBorder(Wash.line2, lineWidth: 0.5))
            )
    }
}

/// Section label — the quiet uppercase rule used across the dashboard.
struct RailLabel: View {
    let text: String
    var body: some View {
        Text(text.uppercased())
            .font(.iface(9, .semibold))
            .tracking(0.15 * 9)
            .foregroundStyle(Wash.faint)
    }
}
