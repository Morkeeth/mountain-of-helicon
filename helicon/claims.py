"""Claim conflicts — R1 beyond person-dates.

The Jul 5 manual audit of the operator's vault showed what cross-source
contradiction looks like in a real second brain: a hackathon win count that
is 8, 9 and 10 in three files; a podcast recording numbered ep25 in one doc
and released as ep29 in another; a security audit still saying 'NOT patched'
while the status file says 'merged to main'. None of those are person+date
facts, so the pairing selector was blind to all of them.

Two deterministic extractors, same contract as pairing (selector finds,
zero LLM, findings share the audit_log shape so FINDINGS / rot / resolve
work unchanged):

  metric claims   (metric, value, qualifier-tokens) — a counted thing.
                  Conflict: same metric, overlapping qualifier, different
                  values, >=2 source files.
  status claims   polar phrase pairs (merged vs pending-merge/NOT patched).
                  Conflict: both poles asserted about overlapping subject
                  tokens from >=2 source files.

Qualifier overlap is the subject binding: '9 hackathon wins' and '8
hackathon wins' share 'hackathon'; 'release/2026-07-04 is MERGED' and
'release/2026-07-04 pending merge' share the release token. No overlap =
different subjects = silence. Precision over recall, as everywhere: a
missed claim is a named gap, a false one teaches the human to ignore
the feed.
"""
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime

from helicon.models import AuditResult
from helicon.db import insert_audit
from helicon.reconcile import source_ref_scope

METRIC_PATTERNS = [
    ("wins", re.compile(r"\b(\d{1,3})\s+(?:hackathon\s+)?wins?\b", re.IGNORECASE)),
    ("episode", re.compile(r"\bep(?:isode)?\.?\s*(\d{1,3})\b", re.IGNORECASE)),
    ("placings", re.compile(r"\b(\d{1,3})\s+(?:podium|placings?|placements?)\b", re.IGNORECASE)),
]

# Polar status phrases. One pair, chosen because it moves real money and
# real deadlines: is the thing merged or not.
STATUS_POLES = {
    "merged": re.compile(r"\b(?:merged to main|all fixes merged|is merged|MERGED)\b",
                         re.IGNORECASE),
    "unmerged": re.compile(r"\b(?:pending merge|not (?:yet )?merged|unmerged|"
                           r"NOT patched|awaiting merge)\b", re.IGNORECASE),
}

_WORD = re.compile(r"[A-Za-z0-9/\-_.]{4,}")
_STOP = {"this", "that", "with", "from", "have", "been", "will", "were",
         "into", "below", "above", "still", "list", "line", "item", "items",
         "note", "notes", "update", "status", "the", "and", "for", "are",
         # metric words and their furniture must not bind subjects — every
         # win-count line contains 'wins', that's not a shared subject
         "wins", "win", "episode", "episodes", "merge", "merged", "merging",
         "pending", "patched", "hackathon.", "released", "recording",
         # per-corpus generic nouns that lump unrelated clusters together
         "radio", "wave", "audience", "project", "projects",
         # generic adjectives that fragment one fact into many clusters
         # ('episode [edited]', 'episode [live]', 'episode [real]' were all
         # the same ep25-vs-ep29 conflict on the live store)
         "live", "real", "final", "edited", "next", "last", "first", "new",
         "old", "tonight", "today", "queued", "guest", "week", "month"}
WINDOW = 60


def _qualifier(text: str, start: int, end: int) -> frozenset:
    window = text[max(0, start - WINDOW): end + WINDOW].lower()
    return frozenset(w for w in _WORD.findall(window)
                     if w not in _STOP and not w.isdigit())


def extract_metric_claims(content: str, title: str = "") -> list[dict]:
    claims = []
    for line in f"{title}\n{content or ''}".splitlines():
        for metric, rx in METRIC_PATTERNS:
            for m in rx.finditer(line):
                q = _qualifier(line, m.start(), m.end())
                if not q:
                    continue
                # 'hackathon wins' / episode numbers are specific claim
                # forms: the match itself names the fact
                strong = (metric == "episode"
                          or "hackathon" in m.group(0).lower()
                          or "podium" in m.group(0).lower())
                claims.append({"metric": metric, "value": m.group(1),
                               "qualifier": q, "strong": strong,
                               "line": line.strip()})
    return claims


def extract_status_claims(content: str, title: str = "") -> list[dict]:
    claims = []
    for line in f"{title}\n{content or ''}".splitlines():
        for pole, rx in STATUS_POLES.items():
            for m in rx.finditer(line):
                q = _qualifier(line, m.start(), m.end())
                if not q:
                    continue
                claims.append({"metric": "merge-status", "value": pole,
                               "qualifier": q, "line": line.strip()})
    return claims


def _cube_scope(row) -> str:
    return f"{row['source']}:{source_ref_scope(row['source_ref'] or '')}"


def find_claim_conflicts(conn: sqlite3.Connection) -> list[dict]:
    """Group claims by metric; report the best-supported pair of values
    whose qualifiers overlap but whose values disagree, across >=2 files."""
    rows = conn.execute(
        "SELECT id, title, content, source, source_ref, created_at "
        "FROM helicon_cubes WHERE review_status IN ('pending', 'revised', 'approved') "
        "AND merged_into IS NULL"
    ).fetchall()

    by_metric: dict = {}
    for row in rows:
        for c in (extract_metric_claims(row["content"], row["title"])
                  + extract_status_claims(row["content"], row["title"])):
            by_metric.setdefault(c["metric"], []).append({
                **c, "cube_id": row["id"], "cube_title": row["title"],
                "scope": _cube_scope(row)})

    conflicts = []
    for metric, claims in by_metric.items():
        # Every disagreeing cross-file pair with a shared subject BINDING.
        # Binding strength is specificity, not count: two generic tokens, or
        # one identifier-ish token (digits/slash/dot: release/2026-07-04,
        # ep29.md), or an inherently specific claim form on both sides
        # ('9 hackathon wins'). A single shared word like 'oscar' or
        # 'built' is coincidence, not the same fact.
        pairs = []
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                a, b = claims[i], claims[j]
                if a["value"] == b["value"]:
                    continue
                shared = a["qualifier"] & b["qualifier"]
                strong = (len(shared) >= 2
                          or any(re.search(r"[\d/.]", t) for t in shared)
                          or (a.get("strong") and b.get("strong") and shared))
                if not shared or not strong:
                    continue
                if a["scope"] == b["scope"]:
                    continue  # one file arguing with itself is not R1
                pairs.append((len(shared), a, b, shared))
        # One conflict per SUBJECT-CLUSTER, not per metric: the security
        # audit's merge fight and the funding flow's merge fight are two
        # different facts and file as two findings. Greedy: strongest
        # binding first; a pair joins a cluster it shares tokens with.
        clusters = []
        for n, a, b, shared in sorted(pairs, key=lambda p: -p[0]):
            for cl in clusters:
                # join on the SEED pair's signature only — growing the
                # signature lets clusters chain-absorb unrelated subjects
                # (every Wave Radio episode ended up in one megacluster)
                if cl["sig"] & shared:
                    cl["claims"].extend([a, b])
                    break
            else:
                clusters.append({"sig": set(shared), "claims": [a, b],
                                 "top": (a, b, shared)})
        for cl in clusters:
            a, b, shared = cl["top"]
            members = {id(c): c for c in cl["claims"]}.values()
            values = sorted({c["value"] for c in members})
            support = Counter(c["value"] for c in members)
            subject = "/".join(sorted(shared)[:4])
            conflicts.append({
                "metric": metric,
                "subject": subject,
                "values": values,
                "support": dict(support),
                "scopes": sorted({c["scope"] for c in members}),
                "cube_ids": sorted({c["cube_id"] for c in members}),
                "pair_key": f"claim|{metric}|{subject}",
                "a": {k: a[k] for k in ("value", "line", "cube_id", "scope")},
                "b": {k: b[k] for k in ("value", "line", "cube_id", "scope")},
            })
    return conflicts


def _existing_keys(conn: sqlite3.Connection) -> set[str]:
    keys = set()
    for row in conn.execute(
        "SELECT details FROM audit_log WHERE audit_type = 'factual' "
        "AND details LIKE '%pair_key%'"
    ):
        try:
            k = json.loads(row["details"]).get("pair_key")
            if k:
                keys.add(k)
        except (json.JSONDecodeError, TypeError):
            pass
    return keys


def claim_scan(conn: sqlite3.Connection) -> dict:
    """File each new claim conflict once (idempotent by pair_key), same
    audit shape as pairing so FINDINGS / rot R1 / resolve work unchanged."""
    existing = _existing_keys(conn)
    now = datetime.utcnow().isoformat()
    filed, skipped = [], []
    for c in find_claim_conflicts(conn):
        if c["pair_key"] in existing:
            skipped.append(c["pair_key"])
            continue
        finding = AuditResult(
            audit_type="factual",
            target_type="cube",
            target_id=c["a"]["cube_id"],
            finding=(f"Cross-source claim conflict: {c['metric']} "
                     f"[{c['subject']}] — "
                     + " vs ".join(f"{v} ({c['support'].get(v, 0)} claim(s))"
                                   for v in c["values"])),
            severity="critical",
            proposed_action="flag",
            details={
                "pair_key": c["pair_key"], "person": c["subject"],
                "topic": c["metric"], "dates": c["values"],
                "all_dates": c["values"], "support": c["support"],
                "cube_a": c["a"]["cube_id"], "cube_b": c["b"]["cube_id"],
                "line_a": c["a"]["line"], "line_b": c["b"]["line"],
                "value_a": c["a"]["value"], "value_b": c["b"]["value"],
                "scope_a": c["a"]["scope"], "scope_b": c["b"]["scope"],
                "scopes": sorted({c["a"]["scope"], c["b"]["scope"]}),
                "judged_by": "deterministic",
            },
            audited_at=now,
        )
        insert_audit(conn, finding)
        filed.append({"pair_key": c["pair_key"], "finding": finding.finding})
    conn.commit()
    return {"conflicts_found": len(filed) + len(skipped),
            "filed": filed, "already_filed": skipped}
