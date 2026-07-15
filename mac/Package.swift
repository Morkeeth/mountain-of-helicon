// swift-tools-version: 6.0
import PackageDescription

// Executable SwiftPM target (not an .xcodeproj) so the app builds and runs
// headless from a shell: `swift build` / `swift run`. `./make-app.sh` wraps the
// same binary in a real .app bundle when a bundled identity is wanted.
let package = Package(
    name: "Helicon",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Helicon", targets: ["Helicon"])
    ],
    targets: [
        .executableTarget(
            name: "Helicon",
            path: "Sources/Helicon",
            // The brand faces travel with the binary, so `swift run` looks the
            // same as the .app. Without this the app falls back to New York/SF
            // and reads as a different product than the dashboard.
            resources: [.copy("Fonts")],
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
