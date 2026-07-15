import SwiftUI
import AppKit
import CoreText

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

/// The brand type stack, for real (Jul 15).
///
/// This used to map Fraunces/Bricolage/IBM Plex Mono onto New York/SF Pro/SF
/// Mono via `design:`, on the theory that web fonts are a native anti-pattern.
/// The colors were already a 1:1 port of the web tokens, so type was the only
/// thing left carrying a difference — and typography IS the brand, so the app
/// read as a different product than the dashboard. The faces are the same files
/// the web now self-hosts; they ship inside the target and register at launch.
///
/// Variable fonts, deliberately: the legacy static exports register split
/// families ("Fraunces SemiBold" as its OWN family), which silently defeats
/// `.weight()`. The variable files register one clean family each and CoreText
/// resolves weights off the wght axis.
enum BrandFont {
    /// Registered once, at first use. `.process` scope keeps it to this app
    /// rather than installing anything on the machine.
    static let ready: Bool = register()

    /// The families we expect after registration. If a lookup misses, that face
    /// falls back to its closest system design rather than crashing or, worse,
    /// silently drawing the wrong weight.
    static let fraunces  = "Fraunces"
    static let bricolage = "Bricolage Grotesque"
    static let plexMono  = "IBM Plex Mono"

    private static func register() -> Bool {
        // Bundle.module covers `swift run` and the .app alike. The bundled app
        // ALSO declares ATSApplicationFontsPath (see make-app.sh), so a second
        // registration here is expected to be a no-op: an already-registered
        // error is success, not failure.
        guard let dir = Bundle.module.url(forResource: "Fonts", withExtension: nil) else {
            return available(fraunces)   // maybe ATS already did it
        }
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: nil))?
            .filter { $0.pathExtension.lowercased() == "ttf" } ?? []
        for url in urls {
            var err: Unmanaged<CFError>?
            if !CTFontManagerRegisterFontsForURL(url as CFURL, .process, &err) {
                // kCTFontManagerErrorAlreadyRegistered (105) is fine.
                let code = (err?.takeUnretainedValue() as Error?).map { ($0 as NSError).code }
                if code != 105 {
                    FileHandle.standardError.write(
                        "[font] could not register \(url.lastPathComponent)\n".data(using: .utf8)!)
                }
            }
        }
        return available(fraunces)
    }

    private static func available(_ family: String) -> Bool {
        NSFont(name: family, size: 12) != nil
    }

    /// One place decides brand-face-or-fallback, so a missing file degrades to
    /// a readable system face instead of taking the cockpit down.
    static func font(_ family: String, _ size: CGFloat,
                     _ weight: Font.Weight, fallback: Font.Design) -> Font {
        guard ready, available(family) else {
            return .system(size: size, weight: weight, design: fallback)
        }
        return .custom(family, size: size).weight(weight)
    }
}

extension Font {
    /// Fraunces. Display, headings, and hero numbers.
    static func display(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        BrandFont.font(BrandFont.fraunces, size, weight, fallback: .serif)
    }
    /// Bricolage Grotesque. Interface text.
    static func iface(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        BrandFont.font(BrandFont.bricolage, size, weight, fallback: .default)
    }
    /// IBM Plex Mono. Data, receipts, raw claim text.
    static func data(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        BrandFont.font(BrandFont.plexMono, size, weight, fallback: .monospaced)
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
