import Foundation

struct OverviewStatus: Decodable {
    let schema: String
    let observedAt: String
    let metrics: [OverviewMetric]
    let setupDrift: SetupComparison
    let unresolved: OverviewUnresolved
    let inventory: OverviewInventory

    enum CodingKeys: String, CodingKey {
        case schema, metrics, unresolved, inventory
        case observedAt = "observed_at"
        case setupDrift = "setup_drift"
    }
}

struct OverviewMetric: Decodable, Identifiable {
    let id: String
    let label: String
    let state: String
    let value: Double?
    let numerator: Int?
    let denominator: Int?
    let formula: String
    let source: String
    let observedAt: String
    let limit: String
    let unmeasured: String
    let points: [OverviewTrendPoint]

    enum CodingKeys: String, CodingKey {
        case id, label, state, value, numerator, denominator, formula, source, limit, unmeasured, points
        case observedAt = "observed_at"
    }
}

struct OverviewTrendPoint: Decodable {
    let at: String
    let value: Double?
    let numerator: Int
    let denominator: Int
}

struct OverviewUnresolved: Decodable {
    let total: Int?
    let critical: Int?
    let source: String
}

struct OverviewInventory: Decodable {
    let harnesses: [String]
    let indexFiles: [OverviewIndex]
    let routes: [OverviewRoute]
    let stores: [OverviewStore]

    enum CodingKeys: String, CodingKey {
        case harnesses, routes, stores
        case indexFiles = "index_files"
    }
}

struct OverviewIndex: Decodable {
    let name: String
    let path: String
    let bytes: Int?
    let files: Int?
}

struct OverviewRoute: Decodable {
    let name: String
    let count: Int
    let kind: String
}

struct OverviewStore: Decodable {
    let name: String
    let path: String
    let bytes: Int?
    let records: Int?
}

struct OverviewStatusLoader {
    let environment: [String: String]
    let home: URL

    init(environment: [String: String] = ProcessInfo.processInfo.environment,
         home: URL = FileManager.default.homeDirectoryForCurrentUser) {
        self.environment = environment
        self.home = home
    }

    func command() throws -> SetupCommand {
        let project = environment["HELICON_SETUP_PROJECT"] ?? home.path
        var arguments = ["overview", "--json", "--project", project]
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

    func load() async throws -> OverviewStatus {
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
            let collector = OverviewOutputCollector(output: output, errors: errors)
            collector.start()
            process.waitUntilExit()
            let (out, err) = collector.finish()
            guard process.terminationStatus == 0 else {
                let message = String(data: err, encoding: .utf8) ?? "no error text"
                throw SetupStatusError.commandFailed(process.terminationStatus, message)
            }
            do { return try JSONDecoder().decode(OverviewStatus.self, from: out) }
            catch { throw SetupStatusError.invalidOutput(String(describing: error)) }
        }.value
    }
}

private final class OverviewOutputCollector: @unchecked Sendable {
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
