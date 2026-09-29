import Foundation

struct SetupStatus: Decodable {
    let schema: String
    let snapshot: SetupSnapshot
    let comparison: SetupComparison
}

struct SetupSnapshot: Decodable {
    let schema: String
    let observedAt: String
    let project: String
    let scope: String
    let coverage: SetupCoverage
    let components: [SetupComponent]
    let edges: [SetupEdge]
    let findings: [SetupFinding]

    enum CodingKeys: String, CodingKey {
        case schema, project, scope, coverage, components, edges, findings
        case observedAt = "observed_at"
    }
}

struct SetupCoverage: Decodable {
    let status: String
    let observed: [String]
    let unknown: [String]
}

struct SetupComponent: Decodable, Identifiable {
    let id: String
    let kind: String
    let name: String
    let path: String?
    let stage: String?
    let verdict: String?
}

struct SetupEvidence: Decodable {
    let configured: String
    let loaded: String
    let used: String
}

struct SetupEdge: Decodable, Identifiable {
    let id: String
    let from: String
    let to: String
    let relation: String
    let evidence: SetupEvidence
}

struct SetupFinding: Decodable, Identifiable {
    let id: String
    let harness: String
    let status: String
    let title: String
    let action: String
}

struct SetupChangeItem: Decodable {
    let id: String?
}

struct SetupChangeSet: Decodable {
    let added: [SetupChangeItem]
    let removed: [SetupChangeItem]
    let changed: [SetupChangeItem]

    var count: Int { added.count + removed.count + changed.count }
}

struct SetupComparison: Decodable {
    let status: String
    let baselineObservedAt: String?
    let message: String
    let components: SetupChangeSet
    let edges: SetupChangeSet

    enum CodingKeys: String, CodingKey {
        case status, message, components, edges
        case baselineObservedAt = "baseline_observed_at"
    }
}

struct SetupCommand: Equatable {
    let executable: URL
    let arguments: [String]
    let directory: URL?
    let environment: [String: String]
}

enum SetupStatusError: LocalizedError {
    case commandMissing
    case commandFailed(Int32, String)
    case invalidOutput(String)

    var errorDescription: String? {
        switch self {
        case .commandMissing:
            return "The Helicon CLI was not found. Install it, or set HELICON_CLI to its executable path."
        case .commandFailed(let code, let message):
            return "helicon status exited \(code): \(message)"
        case .invalidOutput(let message):
            return "helicon status returned an unreadable snapshot: \(message)"
        }
    }
}

struct SetupStatusLoader {
    let environment: [String: String]
    let home: URL

    init(environment: [String: String] = ProcessInfo.processInfo.environment,
         home: URL = FileManager.default.homeDirectoryForCurrentUser) {
        self.environment = environment
        self.home = home
    }

    func command() throws -> SetupCommand {
        let project = environment["HELICON_SETUP_PROJECT"] ?? home.path
        var arguments = ["status", "--json", "--project", project]
        if let previous = environment["HELICON_SETUP_PREVIOUS"], !previous.isEmpty {
            arguments += ["--previous", previous]
        }

        if let source = environment["HELICON_SOURCE_ROOT"], !source.isEmpty {
            var childEnvironment = environment
            childEnvironment["PYTHONPATH"] = source
            return SetupCommand(
                executable: URL(fileURLWithPath: "/usr/bin/env"),
                arguments: ["python3", "-m", "helicon.cli"] + arguments,
                directory: URL(fileURLWithPath: source, isDirectory: true),
                environment: childEnvironment
            )
        }

        let candidates = [
            environment["HELICON_CLI"],
            home.appendingPathComponent(".local/bin/helicon").path,
            "/opt/homebrew/bin/helicon",
            "/usr/local/bin/helicon"
        ].compactMap { $0 }
        guard let path = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else {
            throw SetupStatusError.commandMissing
        }
        return SetupCommand(executable: URL(fileURLWithPath: path), arguments: arguments,
                            directory: nil, environment: environment)
    }

    func load() async throws -> SetupStatus {
        let command = try command()
        return try await Task.detached(priority: .userInitiated) {
            let process = Process()
            let output = Pipe()
            let errors = Pipe()
            process.executableURL = command.executable
            process.arguments = command.arguments
            process.currentDirectoryURL = command.directory
            process.environment = command.environment
            process.standardOutput = output
            process.standardError = errors
            try process.run()

            // A real setup snapshot can exceed the pipe buffer. Drain both
            // streams while the child runs; waiting first deadlocks as soon as
            // `helicon status --json` fills stdout.
            let collector = ProcessOutputCollector(output: output, errors: errors)
            collector.start()
            process.waitUntilExit()
            let (data, errorData) = collector.finish()
            guard process.terminationStatus == 0 else {
                let message = String(data: errorData, encoding: .utf8)?
                    .trimmingCharacters(in: .whitespacesAndNewlines) ?? "no error text"
                throw SetupStatusError.commandFailed(process.terminationStatus, message)
            }
            do {
                return try JSONDecoder().decode(SetupStatus.self, from: data)
            } catch {
                throw SetupStatusError.invalidOutput(String(describing: error))
            }
        }.value
    }
}

private final class ProcessOutputCollector: @unchecked Sendable {
    private let output: Pipe
    private let errors: Pipe
    private let group = DispatchGroup()
    private let lock = NSLock()
    private var outputData = Data()
    private var errorData = Data()

    init(output: Pipe, errors: Pipe) {
        self.output = output
        self.errors = errors
    }

    func start() {
        group.enter()
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            let data = output.fileHandleForReading.readDataToEndOfFile()
            lock.lock(); outputData = data; lock.unlock()
            group.leave()
        }
        group.enter()
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            let data = errors.fileHandleForReading.readDataToEndOfFile()
            lock.lock(); errorData = data; lock.unlock()
            group.leave()
        }
    }

    func finish() -> (Data, Data) {
        group.wait()
        lock.lock(); defer { lock.unlock() }
        return (outputData, errorData)
    }
}
