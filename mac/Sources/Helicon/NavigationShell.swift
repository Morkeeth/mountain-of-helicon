import SwiftUI
import AppKit

enum HeliconDestination: String, CaseIterable, Identifiable {
    case overview
    case history
    case setup
    case context
    case rules
    case failures

    var id: String { rawValue }

    var title: String {
        switch self {
        case .overview: "Overview"
        case .history: "Project history"
        case .setup: "Setup"
        case .context: "Context"
        case .rules: "Rules"
        case .failures: "Failures"
        }
    }

    var subtitle: String {
        switch self {
        case .overview: "Setup health"
        case .history: "Runs and evidence"
        case .setup: "What is wired now"
        case .context: "What governed the work"
        case .rules: "Current law"
        case .failures: "Open drift"
        }
    }

    var symbol: String {
        switch self {
        case .overview: "mountain.2"
        case .history: "clock.arrow.circlepath"
        case .setup: "point.3.connected.trianglepath.dotted"
        case .context: "shippingbox"
        case .rules: "seal"
        case .failures: "exclamationmark.triangle"
        }
    }
}

@MainActor
final class RootNavigation: ObservableObject {
    static let shared = RootNavigation()

    @Published var selection: HeliconDestination {
        didSet { UserDefaults.standard.set(selection.rawValue, forKey: Self.storageKey) }
    }

    private static let storageKey = "helicon.rootDestination"

    private init() {
        let saved = UserDefaults.standard.string(forKey: Self.storageKey)
        selection = HeliconDestination(rawValue: saved ?? "") ?? .overview
    }
}

/// One native shell for the four questions Helicon owns. The selected section
/// lives outside the view tree, so closing and reopening the window preserves
/// orientation instead of resetting the operator to a different product.
struct NavigationShell: View {
    @ObservedObject private var navigation = RootNavigation.shared
    @EnvironmentObject private var store: Store

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider().overlay(Wash.line)
            detail
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(WashBackground())
        .frame(minWidth: 1180, minHeight: 720)
        .task(id: navigation.selection) {
            try? await HeliconAPI().recordSurfaceOpen("native-\(navigation.selection.rawValue)")
        }
        .onChange(of: navigation.selection) { _, destination in
            NSApp.keyWindow?.title = "Helicon · \(destination.title)"
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Image(systemName: "mountain.2.fill")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(Wash.slate)
                    Text("Helicon")
                        .font(.display(21, .semibold))
                        .foregroundStyle(Wash.ink)
                }
                Text("Agent engineering, over time")
                    .font(.iface(10.5))
                    .foregroundStyle(Wash.muted)
            }
            .padding(.top, 28)
            .padding(.horizontal, 18)
            .padding(.bottom, 24)

            VStack(spacing: 5) {
                ForEach(HeliconDestination.allCases) { destination in
                    destinationButton(destination)
                }
            }
            .padding(.horizontal, 10)

            Spacer()

            VStack(alignment: .leading, spacing: 8) {
                Divider().overlay(Wash.line)
                HStack(spacing: 7) {
                    Circle()
                        .fill(store.connection.isLive ? Wash.good : Wash.critical)
                        .frame(width: 6, height: 6)
                    switch store.connection {
                    case .live(let memories):
                        Text("Local · \(memories.formatted()) memories")
                    case .connecting:
                        Text("Connecting to local record")
                    case .down:
                        Text("Local record unavailable")
                    }
                }
                .font(.iface(9.5))
                .foregroundStyle(Wash.muted)
                Text("Each screen names what its evidence can prove.")
                    .font(.iface(9.5))
                    .foregroundStyle(Wash.faint)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(16)
        }
        .frame(width: 232)
        .background(Wash.bone.opacity(0.92))
    }

    private func destinationButton(_ destination: HeliconDestination) -> some View {
        let selected = navigation.selection == destination
        return Button {
            navigation.selection = destination
        } label: {
            HStack(spacing: 11) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(selected ? Wash.improve : .clear)
                    .frame(width: 3, height: 34)
                Image(systemName: destination.symbol)
                    .font(.system(size: 13, weight: selected ? .semibold : .regular))
                    .foregroundStyle(selected ? Wash.ink : Wash.muted)
                    .frame(width: 18)
                VStack(alignment: .leading, spacing: 2) {
                    Text(destination.title)
                        .font(.iface(12.5, selected ? .semibold : .medium))
                        .foregroundStyle(Wash.ink)
                    Text(destination.subtitle)
                        .font(.iface(9.5))
                        .foregroundStyle(Wash.muted)
                }
                Spacer(minLength: 4)
                if destination == .failures, store.openCount > 0 {
                    Text("\(store.openCount)")
                        .font(.data(9.5, .semibold))
                        .foregroundStyle(store.hasCritical ? Wash.critical : Wash.accent)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(Wash.accentDim))
                }
            }
            .padding(.trailing, 10)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(selected ? Wash.paperDeep.opacity(0.82) : .clear)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var detail: some View {
        switch navigation.selection {
        case .overview:
            OverviewView()
        case .history:
            ProjectHistoryView()
        case .setup:
            SetupView()
        case .context:
            ContextView()
        case .rules:
            RulesView()
        case .failures:
            QueueView()
        }
    }
}
