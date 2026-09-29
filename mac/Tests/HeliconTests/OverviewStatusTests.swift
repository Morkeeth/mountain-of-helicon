import XCTest
@testable import Helicon

final class OverviewStatusTests: XCTestCase {
    func testSeparateMetersDecodeUnmeasuredWithoutZero() throws {
        let json = #"""
        {
          "schema":"helicon.overview-status/1",
          "observed_at":"2026-09-29T12:00:00+00:00",
          "metrics":[{
            "id":"retrieval","label":"Retrieval evidence","state":"unmeasured",
            "value":null,"numerator":null,"denominator":13,
            "formula":"cited hits / queries","source":"eval_runs","observed_at":"2026-08-15T12:00:00",
            "limit":"old","unmeasured":"No current evaluation.",
            "points":[{"at":"2026-08-15T12:00:00","value":61.5,"numerator":8,"denominator":13}]
          }],
          "setup_drift":{"status":"tracking_started","baseline_observed_at":null,"message":"No baseline.","components":{"added":[],"removed":[],"changed":[]},"edges":{"added":[],"removed":[],"changed":[]}},
          "unresolved":{"total":15,"critical":9,"source":"audit_log"},
          "inventory":{"harnesses":["claude","codex","cursor"],"index_files":[],"routes":[],"stores":[]}
        }
        """#.data(using: .utf8)!
        let value = try JSONDecoder().decode(OverviewStatus.self, from: json)
        XCTAssertNil(value.metrics[0].value)
        XCTAssertEqual(value.metrics[0].state, "unmeasured")
        XCTAssertEqual(value.metrics[0].points[0].numerator, 8)
        XCTAssertEqual(value.setupDrift.status, "tracking_started")
    }

    func testOverviewCommandUsesSourceCheckoutAndExplicitBaseline() throws {
        let command = try OverviewStatusLoader(environment: [
            "HELICON_SOURCE_ROOT": "/repo/helicon",
            "HELICON_SETUP_PROJECT": "/repo/product",
            "HELICON_SETUP_PREVIOUS": "/snapshots/setup.json"
        ], home: URL(fileURLWithPath: "/Users/test", isDirectory: true)).command()
        XCTAssertEqual(command.executable.path, "/usr/bin/env")
        XCTAssertEqual(command.arguments.suffix(6), [
            "overview", "--json", "--project", "/repo/product", "--previous", "/snapshots/setup.json"
        ])
    }
}
