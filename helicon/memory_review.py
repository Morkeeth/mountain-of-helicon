"""Read-only memory operating review. Measurements are not a health grade."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from helicon.db import search_cubes

LIVE = "merged_into IS NULL AND review_status NOT IN ('killed','superseded')"


def memory_review(conn, trace_db=None):
    checks = []
    trace = Path(trace_db) if trace_db is not None else Path.home() / ".trace/trace.db"
    trace_sql = "SELECT count(*) AS messages, count(DISTINCT session_id) AS sessions, sum(cwd IS NULL OR trim(cwd)='') AS missing_project_paths, sum(julianday(ts) IS NULL) AS invalid_event_times, strftime('%Y-%m-%dT%H:%M:%fZ',max(julianday(ts))) AS latest_event FROM messages"
    try:
        def stamp():
            if any(p.exists() and p.stat().st_size for p in (Path(str(trace) + "-wal"), Path(str(trace) + "-journal"))):
                raise ValueError("Index has a write journal; retry after it settles")
            stat = trace.stat()
            return stat.st_ino, stat.st_size, stat.st_mtime_ns
        before = stamp()
        with sqlite3.connect(trace.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as index:
            cur = index.execute(trace_sql)
            rows = [dict(zip([c[0] for c in cur.description], cur.fetchone()))]
        if stamp() != before:
            raise ValueError("Index changed during the reading; retry")
        checks.append(dict(id="transcript-index", question="What does the transcript index actually cover?", status="measured",
            rows=rows, query=str(trace) + "\n" + trace_sql,
            interpretation="Stored messages and their latest event time, not raw-source completeness. Refreshing this review does not advance that watermark.",
            action="Compare with raw harness receipts; do not call complete fields a complete index."))
    except (OSError, sqlite3.Error, ValueError) as exc:
        checks.append(dict(id="transcript-index", question="What does the transcript index actually cover?", status="unmeasured",
            rows=[], query=str(trace), interpretation=str(exc), action="Connect a stable transcript index; missing is not empty."))

    def measure(key, question, sql, interpretation, action):
        try:
            cur = conn.execute(sql)
            columns = [c[0] for c in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            checks.append(dict(id=key, question=question, status="measured", rows=rows,
                               interpretation=interpretation, action=action, query=sql))
        except sqlite3.Error as exc:
            checks.append(dict(id=key, question=question, status="unmeasured", rows=[],
                               interpretation=str(exc), action=action, query=sql))

    measure("population", "What memory is actually live?",
            "SELECT review_status, count(*) AS memories FROM helicon_cubes WHERE merged_into IS NULL GROUP BY review_status",
            "Live excludes killed, superseded and merged memories. Review coverage is not correctness.",
            "Inspect source coverage before interpreting store totals.")
    measure("sources", "Which sources feed live memory?",
            f"SELECT source, count(*) AS live_memories, max(last_seen) AS last_seen, max(source_mtime) AS latest_source_time FROM helicon_cubes WHERE {LIVE} GROUP BY source",
            "A scan time is not a source event time. Last-seen alone does not establish freshness.",
            "Compare each source watermark with its live source; investigate missing sources.")
    measure("scans", "Did ingestion complete, and what failed?",
            "SELECT started_at, completed_at, connectors_used, cubes_added, cubes_merged, cubes_skipped, errors FROM scan_log ORDER BY id DESC LIMIT 5",
            "These are the last five recorded scans, not proof all source material was captured.",
            "Resolve scan errors and compare raw-source counts with indexed counts.")
    measure("embeddings", "Can semantic retrieval cover live memory?",
            f"SELECT count(*) AS live_memories, sum(EXISTS(SELECT 1 FROM cube_embeddings e WHERE e.cube_id=c.id)) AS with_embeddings FROM helicon_cubes c WHERE {LIVE}",
            "Coverage counts embeddings for live IDs only. It does not measure relevance or vector freshness.",
            "Inspect missing live embeddings and confirm model compatibility before rebuilding.")
    measure("embedding-models", "Are vector models mixed?",
            f"SELECT e.model, e.dim, count(*) AS live_vectors, max(e.embedded_at) AS latest_embedding FROM cube_embeddings e JOIN helicon_cubes c ON c.id=e.cube_id WHERE {LIVE} GROUP BY e.model,e.dim",
            "Different model spaces are not interchangeable, even when dimensions match.",
            "Check the configured query model against the indexed model before judging semantic results.")
    measure("duplicates", "Does live memory repeat exact content?",
            f"SELECT count(*) AS duplicate_groups, coalesce(sum(n-1),0) AS extra_copies FROM (SELECT count(*) n FROM helicon_cubes WHERE {LIVE} AND content_hash IS NOT NULL AND content_hash!='' GROUP BY content_hash HAVING count(*)>1)",
            "Exact stored-hash duplicates only; semantic redundancy remains unmeasured.",
            "Compare provenance before consolidating duplicate memories.")
    measure("retrieval", "Is memory being retrieved and used?",
            "SELECT count(*) AS recorded_events, coalesce(sum(was_surfaced),0) AS marked_surfaced, coalesce(sum(was_acted_on),0) AS marked_acted_on, max(retrieved_at) AS latest_event FROM retrieval_log",
            "These are instrumentation records, not a relevance score or coverage of every agent retrieval.",
            "Link retrieved IDs to real runs and independently reviewed outcomes.")

    probes = []
    for query in ("ZUP", "Helicon", "memory"):
        try:
            rows = search_cubes(conn, query, 5)
            probes.append(dict(query=query, returned=len(rows), ids=[r["id"] for r in rows],
                               retired_returned=sum(r["review_status"] in ("killed", "superseded") for r in rows),
                               merged_returned=sum(bool(r["merged_into"]) for r in rows)))
        except (sqlite3.Error, KeyError) as exc:
            probes.append(dict(query=query, error=str(exc)))
    checks.append(dict(id="search", question="Does the actual keyword search path return memory?",
        status="unmeasured" if any("error" in p for p in probes) else "measured", rows=probes,
        query="helicon.db.search_cubes(query, limit=5)",
        interpretation="Live smoke probes, not labeled relevance tests. Returned IDs let you inspect the exact memories.",
        action="Evaluate real user questions against independently labeled expected answers; test superseded facts and deliberate no-answer cases."))
    for key, question in (("correctness", "Are retrieved answers correct and current?"),
                          ("contradictions", "Which current beliefs conflict?"),
                          ("benefit", "Did memory improve completed work?")):
        checks.append(dict(id=key, question=question, status="unmeasured", rows=[], query="not run",
            interpretation="No validated measurement is supplied by this review. Absence of a finding is not a clean result.",
            action="Join the relevant evaluation or drift receipts to a fixed population before reporting a score."))
    return dict(schema="helicon.memory-review/1", observed_at=datetime.now(timezone.utc).isoformat(),
                scope="Local transcript index and current memory store; no source writes or model calls", checks=checks)
