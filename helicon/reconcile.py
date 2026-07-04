"""Reconciliation — retire memory a re-scan no longer sees.

The gap this closes: ingestion is insert-only (dedup by content_hash), so when
a source is re-scanned after an edit, the *old* version of an edited/removed
section lingers as an orphan cube. Retrieval then returns stale duplicates —
the same failure that makes cross-session memory diverge (a rule you fixed in
one session still surfaces from another's stale copy).

reconcile_scan marks the orphans as 'superseded': cubes in the SAME source and
scope whose content_hash is not in the current scan. It never deletes (history
is auditable) and never touches human-reviewed cubes ('approved'/'killed' are
left alone — a person's call outranks a re-scan).
"""
import sqlite3


def source_ref_scope(source_ref: str) -> str:
    """The file-level scope of a section cube: 'repo/CLAUDE.md' from
    'repo/CLAUDE.md#some-heading'."""
    return source_ref.split("#", 1)[0]


def reconcile_scan(
    conn: sqlite3.Connection,
    source: str,
    present_hashes: set[str],
    scope_prefix: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Mark cubes in `source` (optionally scoped to a source_ref file prefix)
    whose content_hash is absent from `present_hashes` as superseded.

    Only touches cubes still in an unreviewed/auto state so a human decision is
    never overridden. Returns the retired cubes (id, title) and a count.
    """
    # Never override a human decision; superseded cubes are already done.
    where = ["source = ?", "review_status NOT IN ('approved', 'killed', 'revised', 'superseded')"]
    params: list = [source]
    if scope_prefix:
        where.append("source_ref LIKE ?")
        params.append(f"{scope_prefix}%")
    rows = conn.execute(
        f"SELECT id, title, content_hash, review_status FROM helicon_cubes "
        f"WHERE {' AND '.join(where)}",
        params,
    ).fetchall()

    retired = [
        {"id": r["id"], "title": r["title"]}
        for r in rows
        if r["content_hash"] not in present_hashes
    ]
    if retired and not dry_run:
        ids = [r["id"] for r in retired]
        q = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE helicon_cubes SET review_status = 'superseded', "
            f"confidence = MIN(confidence, 0.05) WHERE id IN ({q})",
            ids,
        )
        conn.commit()
    return {"retired": retired, "count": len(retired), "dry_run": dry_run}
