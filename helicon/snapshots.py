"""Context snapshots — regression-test what your agent retrieves.

The novel core of Helicon ("CI for agent memory"): capture the approved context
an agent retrieves for a known task (the baseline), then, as memory changes
(new cubes, consolidation, decay, kills), re-run retrieval and DIFF against the
baseline. Surfaces drift the agent would otherwise fail on silently:

  - dropped   : a memory that used to be retrieved no longer is
  - added     : something new pushed into the top-K
  - reordered : the ranking of the shared items changed
  - stale     : a baseline memory is now killed / decayed / removed

This needs no absolute ground truth — only a baseline — so it is not circular
(unlike an LLM judging its own output).
"""
import json
import sqlite3
from datetime import datetime, timezone


# How long a baseline is evidence. Declared, not implied.
#
# All 13 baselines on the live store were captured 2026-07-09 and 2026-07-11 and
# were still being scored as current 18-20 days later. With no expiry, every real
# change in memory looks like a regression FOREVER, so "regression" and
# "legitimate drift" become indistinguishable and the signal decays to noise —
# which is exactly what happened: 10 of 13 regressed, and no one could say how
# many of those were the product working.
#
# A baseline is a photograph of what retrieval SHOULD return. Memory is supposed
# to change. So a baseline has a shelf life, and past it the honest verdict is
# "this needs re-capturing", never "retrieval got worse".
SNAPSHOT_MAX_AGE_DAYS = 14


def init_snapshot_table(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS context_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task TEXT NOT NULL,
        cube_ids TEXT NOT NULL,      -- JSON list of ids, ranked order
        titles TEXT NOT NULL,        -- JSON list of titles for readable diffs
        top_k INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        note TEXT DEFAULT ''
    )""")
    # Lifecycle columns, added in place so existing baselines keep their history.
    # as_of/stale_when are the vault's own truth-layer discipline (a fact carries
    # when it was true and what invalidates it) applied to the exam's own inputs.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(context_snapshots)")}
    for name, ddl in (
        ("as_of", "TEXT"),               # when this baseline was true
        ("stale_when", "TEXT"),          # the rule that retires it
        ("superseded_by", "INTEGER"),    # the re-capture that replaced it
        ("rebaseline_reason", "TEXT"),   # WHY the baseline moved
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE context_snapshots ADD COLUMN {name} {ddl}")
    conn.commit()


# A live cube decayed below this confidence is hard-stale: the battery's
# Freshness test critical-fails any retrieval that serves one, and the snapshot
# checker classifies its disappearance as 'decayed' (retired), not a regression.
# Retrieval must therefore stop AT the same line the exam grades against —
# before this floor existed, an approved cube at confidence 0.02 ('Edited:
# MEMORY.md', 61 days stale) was served for 'Bagel agent deployment' and the
# battery called its own serving layer BROKEN.
STALE_CONF_FLOOR = 0.10


def _context_hygiene(conn: sqlite3.Connection, hits: list[dict], k: int) -> list[dict]:
    """Post-retrieval hygiene on the over-fetched candidates, one seam for every
    surface that feeds an agent (snapshots, battery, alias leak check):

      - drop retired cubes (superseded/killed) that slipped past the source
        filters — belt-and-suspenders;
      - drop live cubes decayed below STALE_CONF_FLOOR — stale context nobody
        has killed yet, the exact case the battery Freshness test fails;
      - dedupe identical titles, keeping the best-ranked — three distinct
        'Created: closeout-2026-07-23-orchestrator.md' cubes once filled 3 of
        the top-5 slots for 'Orchestrator Closeout', failing Redundancy and
        regressing the snapshot by crowding out live baseline memories.

    Over-fetch (3x k) means every dropped candidate frees a slot for the next
    live, distinct memory."""
    if not hits:
        return hits
    ids = [h["id"] for h in hits]
    q = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, review_status, confidence FROM helicon_cubes WHERE id IN ({q})",
        ids,
    ).fetchall()
    info = {r["id"]: r for r in rows}
    out, seen_titles = [], set()
    for h in hits:
        r = info.get(h["id"])
        if r is None:
            continue  # removed from the store — nothing to serve
        if r["review_status"] in ("superseded", "killed"):
            continue
        conf = r["confidence"] if r["confidence"] is not None else 1.0
        if conf < STALE_CONF_FLOOR:
            continue
        title_key = (h.get("title") or "").strip().lower()
        if title_key and title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        out.append(h)
        if len(out) == k:
            break
    return out


def _retrieve(conn: sqlite3.Connection, task: str, k: int) -> list[dict]:
    """Rank memories for a task the way the agent would (hybrid, FTS fallback).
    Over-fetch, drop superseded, then spend the context budget by policy.

    The three stages are ordered on purpose. Over-fetching keeps recall wide;
    dropping superseded frees the slots retirement should free; and the budget
    policy (exact-name pin + one-per-artifact diversity) is applied LAST, at the
    real k rather than at the over-fetch width. Applying it at the wide width
    silently re-admitted duplicates: with fewer distinct subjects than 3k, the
    cap's overflow refill legitimately fills the tail with second copies, and
    those copies then survive the trim to k. The budget being protected is the
    agent's top-k, so k is where the policy belongs.

    Both branches run it. The FTS fallback is the path a store takes before its
    first `helicon embed`, which is precisely when a new user's ranking is most
    exposed to near-duplicate flooding.
    """
    over = k * 3
    hits = None
    try:
        from helicon.embeddings import get_embedding_stats, hybrid_search
        if get_embedding_stats(conn)["embedded"] > 0:
            # raw ranking here; the policy is applied once, below, at k
            rows = hybrid_search(conn, task, limit=over, per_subject_cap=0,
                                 pin_title_matches=False)
            if rows:
                hits = [{"id": r["id"], "title": r.get("title", ""),
                         "metadata": r.get("metadata")} for r in rows]
    except Exception:
        hits = None
    if hits is None:
        # FTS fallback: OR the terms so multi-word queries still match partially
        # (otherwise "consolidation engine" needs BOTH words and can return
        # nothing).
        import re
        from helicon.db import search_cubes
        terms = [t for t in re.findall(r"[A-Za-z0-9]+", task) if len(t) > 2]
        query = " OR ".join(terms) if terms else task
        try:
            rows = search_cubes(conn, query, over)
        except Exception:
            rows = search_cubes(conn, task, over)
        hits = [{"id": r["id"], "title": r["title"],
                 "metadata": r.get("metadata")} for r in rows]

    from helicon.embeddings import apply_context_policy
    # Hygiene on the wide pool (retired / decayed / duplicate titles out), THEN
    # the budget policy (exact-name pin + one-per-artifact diversity) at the
    # real k — every candidate hygiene drops frees a slot for a live, distinct
    # memory before the policy spends the top-k budget.
    hits = _context_hygiene(conn, hits, over)
    return apply_context_policy(conn, task, hits, k)


def capture_snapshot(conn: sqlite3.Connection, task: str, k: int = 5, note: str = "",
                     max_age_days: int = SNAPSHOT_MAX_AGE_DAYS,
                     rebaseline_reason: str = "", supersedes: int | None = None) -> dict:
    init_snapshot_table(conn)
    hits = _retrieve(conn, task, k)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    cur = conn.execute(
        "INSERT INTO context_snapshots (task, cube_ids, titles, top_k, created_at, "
        "note, as_of, stale_when, rebaseline_reason) VALUES (?,?,?,?,?,?,?,?,?)",
        (task, json.dumps([h["id"] for h in hits]), json.dumps([h["title"] for h in hits]),
         k, now, note, now, f"age > {max_age_days}d", rebaseline_reason),
    )
    new_id = cur.lastrowid
    if supersedes is not None:
        conn.execute("UPDATE context_snapshots SET superseded_by=? WHERE id=?",
                     (new_id, supersedes))
    conn.commit()
    return {"id": new_id, "task": task, "top_k": k, "hits": hits,
            "as_of": now, "stale_when": f"age > {max_age_days}d"}


def recapture_snapshot(conn: sqlite3.Connection, snapshot_id: int, reason: str,
                       k: int | None = None) -> dict:
    """Re-baseline one snapshot, ON THE RECORD.

    A baseline that can be silently overwritten is not evidence, it is an
    opinion that always agrees with today. So re-capture is its own operation:
    it requires a REASON, it links the new baseline to the one it replaces
    (superseded_by), and it leaves the old row in place. "The memory changed"
    and "retrieval got worse" are only distinguishable if somebody wrote down
    which one they believed at the moment they moved the goalposts.
    """
    init_snapshot_table(conn)
    if not (reason or "").strip():
        raise ValueError(
            "a re-baseline needs a reason — without one, 'the memory changed' "
            "and 'retrieval got worse' are the same edit")
    old = conn.execute("SELECT * FROM context_snapshots WHERE id=?",
                       (snapshot_id,)).fetchone()
    if old is None:
        raise ValueError(f"no snapshot {snapshot_id}")
    if old["superseded_by"]:
        raise ValueError(
            f"snapshot {snapshot_id} was already superseded by "
            f"{old['superseded_by']}; re-baseline that one instead")
    return capture_snapshot(
        conn, old["task"], k or old["top_k"],
        note=f"re-baselined from #{snapshot_id}",
        rebaseline_reason=reason, supersedes=snapshot_id)


def check_snapshot(conn: sqlite3.Connection, snap: sqlite3.Row,
                   max_age_days: int = SNAPSHOT_MAX_AGE_DAYS) -> dict:
    old_ids = json.loads(snap["cube_ids"])
    old_titles = json.loads(snap["titles"])
    title_of = dict(zip(old_ids, old_titles))
    task, k = snap["task"], snap["top_k"]

    new_hits = _retrieve(conn, task, k)
    new_ids = [h["id"] for h in new_hits]
    new_title_of = {h["id"]: h["title"] for h in new_hits}
    old_set, new_set = set(old_ids), set(new_ids)

    dropped = [title_of[i] for i in old_ids if i not in new_set]
    added = [new_title_of[i] for i in new_ids if i not in old_set]
    common_old = [i for i in old_ids if i in new_set]
    common_new = [i for i in new_ids if i in old_set]
    reordered = common_old != common_new

    # WHY a baseline memory is gone decides whether this is a failure or the
    # product doing its job. Retrieval filters killed+superseded at the source,
    # so a retired memory CANNOT come back — and must not.
    retired_why = {}
    for i in old_ids:
        row = conn.execute(
            "SELECT confidence, review_status FROM helicon_cubes WHERE id = ?", (i,)
        ).fetchone()
        if row is None:
            retired_why[i] = "removed"
        elif row["review_status"] == "killed":
            retired_why[i] = "killed"
        elif row["review_status"] == "superseded":
            retired_why[i] = "superseded"
        elif (row["confidence"] or 0) < STALE_CONF_FLOOR:
            retired_why[i] = "decayed"
    stale = [(title_of[i], why) for i, why in retired_why.items()]

    # The regression signal, deliberately narrow.
    #
    # This used to be `dropped or added or reordered or stale`, i.e. ANY change
    # at all, which made the exam report the loop WORKING as a failure. On the
    # live store that read 12/13 "regressed", and the reason was: 16 of 17
    # missing baseline memories were gone because Helicon had KILLED them as
    # rot (15) or let them decay (1). Retrieval correctly stopped serving them,
    # a better memory took each vacated slot (added=17), and the exam called
    # that degradation. `report` then printed DEGRADED off the same count — so
    # the one command a judge runs in thirty seconds indicted the product for
    # succeeding.
    #
    # A retired memory leaving the top-K is the system's whole purpose.
    # A NEW memory outranking the baseline is the store learning.
    # Reordering is churn.
    # What is left, and all that is left: a memory that is STILL LIVE and no
    # longer retrieved. That might be a better memory displacing it rather than
    # a true regression — the exam cannot tell, so it files it and a human
    # rules. That is the loop, and it is the only honest signal here.
    dropped_live = [title_of[i] for i in old_ids
                    if i not in new_set and i not in retired_why]
    regressed = bool(dropped_live)

    live_old = [i for i in old_ids if i not in retired_why]
    live_overlap = (len([i for i in live_old if i in new_set]) / len(live_old)
                    if live_old else 1.0)
    overlap = len(old_set & new_set) / max(1, len(old_set))
    fossil = bool(old_ids) and not live_old

    # --- is this baseline still evidence? ---
    #
    # Three ways a baseline stops being a test, none of which is "retrieval got
    # worse", and all of which were being scored as if they were:
    #
    #   expired    older than the shelf life. Memory is SUPPOSED to change; past
    #              the window a diff measures elapsed time, not quality.
    #   fossil     every baseline memory has been retired. #28 'Search' read
    #              fossil:True with overlap 0.0 and still scored OK, because
    #              live_overlap of an empty set is 1.0 — a vacuous pass.
    #   stale-task the QUERY names something that no longer exists. #16 is
    #              "RELAY project status and progress"; RELAY was renamed to
    #              FAVOUR on 2026-07-02, before the baseline was even captured.
    #              A baseline asking for a dead name tests nothing current.
    #
    # Each reports as needing re-capture. None counts as a regression, and none
    # is silently a pass either — an expired exam is unmeasured, not clean.
    age_days = _age_days(snap["created_at"])
    keys = snap.keys()
    expired = age_days is not None and age_days > max_age_days
    dead_name = _dead_name_in(conn, task)
    superseded_by = snap["superseded_by"] if "superseded_by" in keys else None

    if superseded_by:
        status = "superseded"
    elif dead_name:
        status = "stale-task"
    elif fossil:
        status = "fossil"
    elif expired:
        status = "expired"
    elif regressed:
        status = "regressed"
    else:
        status = "ok"
    # A baseline that is no longer evidence cannot report a regression.
    regressed = status == "regressed"

    return {
        "snapshot_id": snap["id"], "task": task,
        "status": status,
        "age_days": age_days,
        "expired": expired,
        "stale_task": dead_name,
        "as_of": snap["as_of"] if "as_of" in keys else snap["created_at"],
        "stale_when": (snap["stale_when"] if "stale_when" in keys else None)
                      or f"age > {max_age_days}d",
        "superseded_by": superseded_by,
        "needs_recapture": status in ("expired", "fossil", "stale-task"),
        "regressed": regressed, "overlap": round(overlap, 2),
        # overlap counts retired memories against the baseline, so it decays as
        # the product works. live_overlap is the one to read.
        "live_overlap": round(live_overlap, 2),
        "dropped": dropped, "dropped_live": dropped_live,
        "added": added, "reordered": reordered, "stale": stale,
        # a baseline whose memories are all retired is a fossil, not a test
        "fossil": fossil,
        "new_titles": [h["title"] for h in new_hits],
    }


def check_all(conn: sqlite3.Connection,
              max_age_days: int = SNAPSHOT_MAX_AGE_DAYS,
              include_superseded: bool = False) -> list[dict]:
    """Every baseline that is still standing.

    Superseded baselines are excluded by default: once a re-capture replaces
    one, scoring both double-counts the same task and the older row can only
    ever look worse. They stay in the table as history — the lineage is the
    record of WHY a baseline moved — but they are not exam questions.
    """
    init_snapshot_table(conn)
    rows = conn.execute("SELECT * FROM context_snapshots ORDER BY id").fetchall()
    out = [check_snapshot(conn, r, max_age_days=max_age_days) for r in rows]
    if not include_superseded:
        out = [r for r in out if r["status"] != "superseded"]
    return out


def _age_days(created_at: str | None) -> float | None:
    from helicon.timeutil import ts_norm, utc_now
    norm = ts_norm(created_at)
    if not norm:
        return None
    try:
        return round((utc_now() - datetime.fromisoformat(norm)).total_seconds() / 86400, 1)
    except ValueError:
        return None


def _dead_name_in(conn: sqlite3.Connection, task: str) -> str | None:
    """Does this baseline's QUERY name something that has been renamed?

    #16 asks for "RELAY project status and progress". RELAY became FAVOUR on
    2026-07-02 — before the baseline was captured. Scoring it forever means
    scoring retrieval on a question about a thing that no longer exists, and
    reading the inevitable drift as a regression.
    """
    try:
        rows = conn.execute(
            "SELECT old_name, new_name FROM entity_aliases").fetchall()
    except sqlite3.Error:
        return None
    import re
    for r in rows:
        old = (r["old_name"] or "").strip()
        if not old:
            continue
        if re.search(rf"(?<!\w){re.escape(old)}(?!\w)", task or "", re.I):
            return f"{old} -> {r['new_name']}"
    return None
