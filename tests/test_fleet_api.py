"""The fleet route: what is running, without inventing what it meant."""
import pytest
from fastapi.testclient import TestClient

from helicon.api.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_fleet_answers_and_names_its_window(client):
    r = client.get("/api/fleet", params={"days": 7})
    assert r.status_code == 200
    d = r.json()
    for key in ("running", "running_count", "observed_count", "spend",
                "spend_window_days", "unreviewed", "efficiency"):
        assert key in d, f"fleet payload missing {key}"
    assert d["spend_window_days"] == 7
    assert d["running_count"] == len(d["running"])


def test_an_observed_run_never_reports_a_drift_signal(client):
    """The honesty invariant the whole bridge rests on.

    A session captured after the fact never froze an objective, so it cannot have
    drifted from one. fleet.running() refuses to compute a signal for those — but
    only if they are marked. The first version of govern_captures() did not set
    task_class, so all 36 observed runs arrived looking governed and the fleet
    would have shown a drift score measured against an objective that was
    reconstructed from the session's own first prompt. That is a fabricated
    contract, which is the one thing this module says it will not do.
    """
    d = client.get("/api/fleet").json()
    for run in d["running"]:
        if run["observed"]:
            assert run["drift"]["checkable"] is False
            assert "no objective was frozen" in run["drift"]["reason"]


def test_observed_count_is_a_subset_of_running(client):
    d = client.get("/api/fleet").json()
    assert 0 <= d["observed_count"] <= d["running_count"]
    assert d["observed_count"] == sum(1 for r in d["running"] if r["observed"])


def test_window_is_clamped_not_trusted(client):
    """A caller-supplied window is bounded; an unbounded scan is a denial of
    service on a store that grows every night."""
    assert client.get("/api/fleet", params={"days": 9999}).json()["spend_window_days"] == 90
    assert client.get("/api/fleet", params={"days": 0}).json()["spend_window_days"] == 1
