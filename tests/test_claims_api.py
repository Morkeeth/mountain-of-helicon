"""The verification ladder: an unverified claim must not look like a verified one."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from helicon.api.app import app
from helicon.api.claims import LEVELS, classify


def _row(**kw):
    base = {"verification_outcome": None, "verification_receipt": None,
            "human_acceptance": "pending", "task_class": None}
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_a_self_reported_claim_is_not_checked():
    """The whole spec in one assertion. On 2026-08-10 every `verified` run in the
    live store carried human_acceptance='pending' and a receipt whose source was
    'attached' — the agent's own evidence. That must not render as verified."""
    level, why = classify(_row(verification_outcome="verified",
                               verification_receipt=json.dumps({"source": "attached"})))
    assert level == "SELF_REPORTED"
    assert "no human has ruled" in why


def test_an_independent_receipt_outranks_a_self_reported_one():
    level, _ = classify(_row(verification_outcome="verified",
                             verification_receipt=json.dumps({"source": "adversarial-judge"})))
    assert level == "INDEPENDENTLY_CHECKED"
    assert LEVELS.index(level) > LEVELS.index("SELF_REPORTED")


def test_an_observed_run_makes_no_claim_and_is_not_a_failure():
    level, why = classify(_row(task_class="auto-observed"))
    assert level == "NO_CLAIM"
    assert "declared before the work" in why


def test_missing_verification_is_no_data_never_a_pass():
    """The rule this suite's own bug taught it."""
    level, why = classify(_row())
    assert level == "NO_DATA"
    assert LEVELS.index(level) == 0
    assert "no verification outcome" in why


def test_a_human_rollback_still_counts_as_ruled():
    """Ruled-and-rejected is knowledge. Only unruled is absence."""
    assert classify(_row(human_acceptance="rollback"))[0] == "HUMAN_RULED"


def test_cost_is_unknown_not_zero_when_the_run_has_no_card():
    """A run with no cost card must report cost_known=False. Rendering an unjoined
    run as 0 would make the most expensive unmeasured work look free."""
    d = client_payload = None
    with TestClient(app) as c:
        d = c.get("/api/claims").json()
    for claim in d["claims"]:
        if not claim["cost_known"]:
            assert claim["cost"] is None


def test_the_headline_counts_only_independent_checks(client):
    """CI has an empty store; a developer machine does not.

    This assertion used to demand a number in the headline unconditionally, so it
    passed on Oscar's populated store and failed on every clean checkout — red on
    9 consecutive pushes while the suite reported 792 passing locally. That is the
    stranger problem this project exists to catch, inside its own test file. Both
    branches are asserted now, and which one applies is decided by the data.
    """
    d = client.get("/api/claims").json()
    expected = d["counts"]["INDEPENDENTLY_CHECKED"] + d["counts"]["HUMAN_RULED"]
    assert d["independently_checked"] == expected
    if d["total"] == 0:
        assert d["headline"].startswith("NO DATA")
        assert "not a pass" in d["headline"]
    else:
        assert str(expected) in d["headline"]
        assert "checked by something other than the agent" in d["headline"]


def test_an_empty_store_reports_no_data_not_clean(tmp_path):
    """Never a reassuring summary over an empty table."""
    from helicon.api.claims import claims as claims_route
    import asyncio
    from helicon.db import init_db
    conn = init_db(str(tmp_path / "empty.db"))
    import helicon.api.claims as mod
    original = mod._conn
    mod._conn = lambda: conn
    try:
        d = asyncio.run(claims_route(limit=50))
    finally:
        mod._conn = original
    assert d["total"] == 0
    assert d["headline"].startswith("NO DATA")
    assert "not a pass" in d["headline"]
