"""The registry gate: every project you own should have a row, and a row that
points at a repo must point at one that exists.

The gate runs every morning, so the tests pin the two ways it dies: crying wolf
on rows that are not code (the 39-row wall that gets it closed on day two), and
matching so loosely that a real gap is absorbed by an unrelated row.
"""
from helicon.registry import audit_registry, matches, slug


def _registry(tmp_path, body):
    p = tmp_path / "registry.md"
    p.write_text("| # | Initiative | Vector | Shape | Progress | Next |\n"
                 "|---|---|---|:---:|---|---|\n" + body, encoding="utf-8")
    return str(p)


def _repo(name, archived=False, fork=False, updated="2026-08-01"):
    return {"name": name, "isArchived": archived, "isFork": fork,
            "updatedAt": updated + "T00:00:00Z", "description": ""}


def test_a_repo_with_no_row_is_the_gap(tmp_path):
    reg = _registry(tmp_path, "| 001 | Wave Radio | CREATIVE | 🟢 | prose | next |\n")
    res = audit_registry(reg, str(tmp_path), repos=[_repo("warrant")])
    assert [e["name"] for e in res["unlisted"]] == ["warrant"]
    assert not res["clean"]


def test_the_alias_counts_as_a_row(tmp_path):
    """Row titles carry the human name; the repo is usually named by the alias.
    Matching only the title reports a false gap for most of the table."""
    reg = _registry(tmp_path, "| 011 | HL tool _(dashboard)_ / **REKT Capital** | MONEY | 🔵 | p | n |\n")
    res = audit_registry(reg, str(tmp_path), repos=[_repo("rekt-capital")])
    assert res["unlisted"] == []


def test_a_longer_repo_name_still_matches_its_row(tmp_path):
    """Row 056 reads THE AGENT WORK RECORD WITNESS; the repo carries a suffix."""
    reg = _registry(tmp_path, "| 056 | **THE AGENT WORK RECORD WITNESS** | BUILD | 🟢 | p | n |\n")
    res = audit_registry(reg, str(tmp_path),
                         repos=[_repo("agent-work-record-witness-ata")])
    assert res["unlisted"] == []


def test_archived_and_forked_repos_are_excluded_and_counted(tmp_path):
    """Archiving IS the decision, and a fork is not a project. Both excluded,
    both counted, so the denominator stays visible."""
    reg = _registry(tmp_path, "| 001 | Nothing | X | 🟢 | p | n |\n")
    res = audit_registry(reg, str(tmp_path), repos=[
        _repo("old-thing", archived=True),
        _repo("someone-elses", fork=True),
        _repo("real-gap"),
    ])
    assert [e["name"] for e in res["unlisted"]] == ["real-gap"]
    assert res["excluded_archived"] == 1 and res["excluded_forks"] == 1
    assert res["repos_live"] == 1


def test_prose_mention_is_counted_not_flagged(tmp_path):
    """Mentioned inside another row's paragraph is weak coverage: real, and not
    the same as owning a row. It must not be reported as a gap."""
    reg = _registry(tmp_path,
                    "| 001 | Something | X | 🟢 | we vendored `fleet-ops` here | n |\n")
    res = audit_registry(reg, str(tmp_path), repos=[_repo("fleet-ops")])
    assert res["unlisted"] == []
    assert [e["name"] for e in res["prose_only"]] == ["fleet-ops"]


def test_a_row_pointing_at_a_missing_repo_is_flagged(tmp_path):
    """The opposite drift. This is the red light for rows_without_project — the
    real registry currently has zero, and a check that has never been watched
    firing is a claim, not a control."""
    reg = _registry(tmp_path,
                    "| 042 | Ghost | BUILD | 🟢 | repo `~/CODE/does-not-exist` | n |\n")
    res = audit_registry(reg, str(tmp_path), repos=[])
    assert len(res["rows_without_project"]) == 1
    assert res["rows_without_project"][0]["ghosts"] == ["doesnotexist"]
    assert not res["clean"]


def test_a_non_code_row_is_never_flagged(tmp_path):
    """Journaling, Wave Radio and Job hunt own no repo and never should.
    Flagging them is the wall that kills the check."""
    reg = _registry(tmp_path,
                    "| 001 | Journaling + scrapbook | CREATIVE | 🧍 | analog | yours |\n"
                    "| 015 | Job hunt | CAREER | 🟡 | reactivated | tighten |\n")
    res = audit_registry(reg, str(tmp_path), repos=[])
    assert res["rows_without_project"] == []
    assert res["clean"]


def test_short_names_do_not_match_by_containment(tmp_path):
    """Over-matching HIDES gaps, which is worse than reporting one. A short slug
    inside a longer one is a coincidence, so containment has a floor."""
    assert not matches(slug("zup"), {slug("zuppa-inglese-tracker")})
    assert matches(slug("nullspace-dbt"), {slug("nullspace")})


def test_clean_registry_is_clean(tmp_path):
    reg = _registry(tmp_path, "| 001 | warrant | BUILD | 🟢 | p | n |\n")
    res = audit_registry(reg, str(tmp_path), repos=[_repo("warrant")])
    assert res["clean"] and res["unlisted"] == []
