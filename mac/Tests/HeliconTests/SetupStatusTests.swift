import XCTest
@testable import Helicon

final class SetupStatusTests: XCTestCase {
    func testTrackingStartedDecodesWithoutInventingDelta() throws {
        let json = #"""
        {
          "schema":"helicon.setup-status/1",
          "snapshot":{
            "schema":"helicon.setup-snapshot/1",
            "observed_at":"2026-09-29T10:00:00+00:00",
            "project":"/tmp/project",
            "scope":"read-only",
            "coverage":{"status":"partial","observed":["skill files"],"unknown":["effective model context"]},
            "components":[{"id":"harness:codex","kind":"harness","name":"codex"}],
            "edges":[],
            "findings":[]
          },
          "comparison":{
            "status":"tracking_started",
            "baseline_observed_at":null,
            "message":"Tracking started. No previous snapshot was supplied, so no change is claimed.",
            "components":{"added":[],"removed":[],"changed":[]},
            "edges":{"added":[],"removed":[],"changed":[]}
          }
        }
        """#.data(using: .utf8)!
        let value = try JSONDecoder().decode(SetupStatus.self, from: json)
        XCTAssertEqual(value.comparison.status, "tracking_started")
        XCTAssertNil(value.comparison.baselineObservedAt)
        XCTAssertEqual(value.comparison.components.count, 0)
        XCTAssertEqual(value.snapshot.coverage.unknown, ["effective model context"])
    }

    func testCommandUsesExplicitBaselineOnlyWhenProvided() throws {
        let home = URL(fileURLWithPath: "/Users/test", isDirectory: true)
        let command = try SetupStatusLoader(environment: [
            "HELICON_SOURCE_ROOT": "/repo/helicon",
            "HELICON_SETUP_PROJECT": "/repo/product",
            "HELICON_SETUP_PREVIOUS": "/snapshots/week-1.json"
        ], home: home).command()
        XCTAssertEqual(command.executable.path, "/usr/bin/env")
        XCTAssertEqual(command.arguments.suffix(6), [
            "status", "--json", "--project", "/repo/product", "--previous", "/snapshots/week-1.json"
        ])
    }

    func testNoBaselineArgumentIsAddedByDefault() throws {
        let command = try SetupStatusLoader(environment: [
            "HELICON_SOURCE_ROOT": "/repo/helicon"
        ], home: URL(fileURLWithPath: "/Users/test", isDirectory: true)).command()
        XCTAssertFalse(command.arguments.contains("--previous"))
        XCTAssertEqual(command.arguments.suffix(4), ["status", "--json", "--project", "/Users/test"])
    }
}
