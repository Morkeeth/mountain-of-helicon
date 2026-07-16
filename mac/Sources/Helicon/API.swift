import Foundation

enum APIError: LocalizedError {
    case badStatus(Int)
    case transport(String)
    case decode(String)

    var errorDescription: String? {
        switch self {
        case .badStatus(let c): return "API returned HTTP \(c)"
        case .transport(let m): return m
        case .decode(let m):    return "Response did not match the expected shape (\(m))"
        }
    }
}

/// Thin client over the local `helicon serve` API. Local-only by construction:
/// the base URL is 127.0.0.1 and nothing here talks to a network host.
struct HeliconAPI {
    var base: URL

    /// Defaults to the port `helicon serve` uses. HELICON_API repoints it — at a
    /// sandbox instance for testing the write path, never at a remote host.
    init(base: URL? = nil) {
        if let base {
            self.base = base
        } else if let s = ProcessInfo.processInfo.environment["HELICON_API"],
                  let u = URL(string: s) {
            self.base = u
        } else {
            self.base = URL(string: "http://127.0.0.1:8420")!
        }
    }

    private static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 5
        c.timeoutIntervalForResource = 10
        c.waitsForConnectivity = false
        return URLSession(configuration: c)
    }()

    private func run<T: Decodable>(_ req: URLRequest, as: T.Type) async throws -> T {
        let data: Data, resp: URLResponse
        do {
            (data, resp) = try await Self.session.data(for: req)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        guard let http = resp as? HTTPURLResponse else {
            throw APIError.transport("no HTTP response")
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.badStatus(http.statusCode)
        }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decode(String(describing: error).prefix(160).description)
        }
    }

    private func get<T: Decodable>(_ path: String, _ query: [URLQueryItem] = []) async throws -> T {
        var comps = URLComponents(url: base.appendingPathComponent(path),
                                  resolvingAgainstBaseURL: false)!
        if !query.isEmpty { comps.queryItems = query }
        return try await run(URLRequest(url: comps.url!), as: T.self)
    }

    // GET /api/health -> {"status":"ok","memories":7003}  ("cubes" is a deprecated alias)
    func health() async throws -> Health {
        try await get("/api/health")
    }

    /// GET /api/findings?lane=decision&limit=100
    /// summary.needs_you / summary.ambient always describe the FULL set (the
    /// server counts them before the lane slice), so one call feeds both the
    /// sentry count and the queue.
    func findings(lane: String? = "decision", limit: Int = 100) async throws -> FindingsResponse {
        var q = [URLQueryItem(name: "limit", value: String(limit))]
        if let lane { q.append(URLQueryItem(name: "lane", value: lane)) }
        return try await get("/api/findings", q)
    }

    /// POST /api/audit/confirm — the one real write path the HTTP API exposes
    /// for a finding. It sets audit_log.human_decision + resolved_at, which is
    /// what drops the finding out of the pending queue.
    ///
    /// A dismissal that carries `notes` now routes through the SAME function the
    /// CLI uses (`helicon.pairing.dismiss_finding`), which records the reason as
    /// details.dismiss_reason — the one field gold.py compiles a GOLDEN_RULES
    /// precedent from. The server answers `precedent: true` when that happened,
    /// so the UI can report the ruling became law because it did, and stays
    /// quiet when it did not (a dismissal with no reason still clears the queue
    /// but compiles to nothing).
    @discardableResult
    func confirm(findingID: Int, decision: String, notes: String = "") async throws -> ConfirmResponse {
        var req = URLRequest(url: base.appendingPathComponent("/api/audit/confirm"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(
            ConfirmRequest(finding_id: findingID, decision: decision, notes: notes)
        )
        return try await run(req, as: ConfirmResponse.self)
    }
}
