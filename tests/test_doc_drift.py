"""Stale docs fail the build: README numeric claims must match source truth.

This is the dogfood check made permanent — on Jul 4 the README claimed 8 MCP
tools while source had 11. Now that class of drift is a test failure.
"""
from helicon.docdrift import check_readme


def test_readme_claims_match_source():
    results = check_readme()
    drifted = [r for r in results if not r["ok"]]
    assert not drifted, "README drifted from source: " + "; ".join(
        f"{r['claim']}: {r['why']}" for r in drifted
    )
