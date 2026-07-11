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
from datetime import datetime, timezone

from helicon.models import AuditResult
from helicon.db import insert_audit
from helicon.reconcile import source_ref_scope

METRIC_PATTERNS = [
    ("wins", re.compile(r"\b(\d{1,3})\s+(?:hackathon\s+)?wins?\b", re.IGNORECASE)),
    ("episode", re.compile(r"\bep(?:isode)?\.?\s*(\d{1,3})\b", re.IGNORECASE)),
    ("placings", re.compile(r"\b(\d{1,3})\s+(?:podium|placings?|placements?)\b", re.IGNORECASE)),
]

# Polar status phrases. Two built-in pairs: merge status (moves real code)
# and decision status (a decision presented as open after it was executed —
# the FAVOUR-rebrand class from the Jul 5 vault audit).
STATUS_POLES = {
    "merge-status": {
        # Anchored to a merge PHRASE, never the bare word "merged": a lowercase
        # "merged" is a code variable (generate_markdown(merged, config)) or
        # unrelated prose ("two sessions merged") far more often than a status.
        # The all-caps MERGED stamp stays case-SENSITIVE (a deliberate label),
        # so IGNORECASE no longer drags every "merged" token into the claim.
        "merged": re.compile(r"\b(?:merged (?:to|into) main|all fixes merged|is merged|"
                             r"(?-i:MERGED))\b", re.IGNORECASE),
        "unmerged": re.compile(r"\b(?:pending merge|not (?:yet )?merged|unmerged|"
                               r"NOT patched|awaiting merge)\b", re.IGNORECASE),
    },
    "decision-status": {
        "executed": re.compile(r"\b(?:executed|shipped|launched|went live|"
                               r"decision:?\s*(?:done|made|final))\b",
                               re.IGNORECASE),
        "open": re.compile(r"\b(?:open decisions?|undecided|decision pending|"
                           r"not (?:yet )?decided|to be decided)\b", re.IGNORECASE),
    },
}


def load_domain_patterns(config: dict | None) -> tuple[list, dict]:
    """The domain lexicon is CONFIG, not code. A new corpus (an enterprise
    wiki, a research vault) declares its own counted things and polar
    statuses in config.json and gets the same conflict machinery:

      "claims": {
        "metrics": {"headcount": "\\\\b(\\\\d{2,5})\\\\s+employees\\\\b"},
        "statuses": {"contract": {"live": "\\\\bcontract (?:is )?live\\\\b",
                                   "expired": "\\\\bcontract expired\\\\b"}}
      }

    Built-ins always apply; config extends them. A bad regex is reported
    once and skipped, never fatal."""
    metrics = list(METRIC_PATTERNS)
    statuses = dict(STATUS_POLES)
    cc = (config or {}).get("claims", {})
    for name, pattern in cc.get("metrics", {}).items():
        try:
            metrics.append((name, re.compile(pattern, re.IGNORECASE)))
        except re.error as e:
            print(f"  [!] claims.metrics.{name}: bad regex skipped ({e})")
    for name, poles in cc.get("statuses", {}).items():
        compiled = {}
        for pole, pattern in poles.items():
            try:
                compiled[pole] = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                print(f"  [!] claims.statuses.{name}.{pole}: bad regex skipped ({e})")
        if len(compiled) >= 2:
            statuses[name] = compiled
    return metrics, statuses

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


def extract_metric_claims(content: str, title: str = "",
                          metrics: list | None = None) -> list[dict]:
    claims = []
    for line in f"{title}\n{content or ''}".splitlines():
        for metric, rx in (metrics if metrics is not None else METRIC_PATTERNS):
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


def extract_status_claims(content: str, title: str = "",
                          statuses: dict | None = None) -> list[dict]:
    claims = []
    for line in f"{title}\n{content or ''}".splitlines():
        for metric, poles in (statuses if statuses is not None
                              else STATUS_POLES).items():
            # A line matching BOTH poles is a correction or a comparison
            # ("was open, now EXECUTED") — it asserts neither pole. The
            # LOUPE banners that CLOSE decisions were being filed as
            # evidence the decisions were still open.
            hits = {pole: list(rx.finditer(line))
                    for pole, rx in poles.items()}
            if sum(1 for v in hits.values() if v) > 1:
                continue
            for pole, ms in hits.items():
                for m in ms:
                    q = _qualifier(line, m.start(), m.end())
                    if not q:
                        continue
                    claims.append({"metric": metric, "value": pole,
                                   "qualifier": q, "line": line.strip()})
    return claims


def _cube_scope(row) -> str:
    return f"{row['source']}:{source_ref_scope(row['source_ref'] or '')}"


def find_claim_conflicts(conn: sqlite3.Connection,
                         config: dict | None = None) -> list[dict]:
    """Group claims by metric; report the best-supported pair of values
    whose qualifiers overlap but whose values disagree, across >=2 files.
    Domain lexicon = built-ins + whatever config declares."""
    if config is None:
        from helicon.config import load_config
        config = load_config()
    metrics, statuses = load_domain_patterns(config)
    rows = conn.execute(
        "SELECT id, title, content, source, source_ref, created_at "
        "FROM helicon_cubes WHERE review_status IN ('pending', 'revised', 'approved') "
        "AND merged_into IS NULL"
    ).fetchall()

    by_metric: dict = {}
    for row in rows:
        for c in (extract_metric_claims(row["content"], row["title"], metrics)
                  + extract_status_claims(row["content"], row["title"], statuses)):
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
            conflict = {
                "metric": metric,
                "subject": subject,
                "values": values,
                "support": dict(support),
                "scopes": sorted({c["scope"] for c in members}),
                "cube_ids": sorted({c["cube_id"] for c in members}),
                "pair_key": f"claim|{metric}|{subject}",
                "a": {k: a[k] for k in ("value", "line", "cube_id", "scope")},
                "b": {k: b[k] for k in ("value", "line", "cube_id", "scope")},
            }
            # Canonical source: config declares WHERE a fact's truth lives
            # ("canonical": {"wins": "mindmap.md"}). If a canon file speaks
            # in this conflict, the direction is pre-decided: everything
            # disagreeing with canon is the drift. The human confirms
            # instead of adjudicating.
            canon_file = (config.get("claims", {})
                          .get("canonical", {}).get(metric))
            if canon_file:
                import os as _os
                def _is_canon(scope):
                    return _os.path.basename(
                        scope.split(":", 1)[-1]) == canon_file
                # judge canon against ALL of the metric's claims, not just
                # cluster members: a canon file that asserts both values
                # (or an archived near-name copy) must never pre-decide
                canon_vals = {c["value"] for c in claims
                              if _is_canon(c["scope"])}
                if len(canon_vals) == 1:
                    truth = canon_vals.pop()
                    conflict["canonical"] = {
                        "file": canon_file, "truth": truth,
                        "drifted": sorted(v for v in values if v != truth)}
            conflicts.append(conflict)
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


def claim_scan(conn: sqlite3.Connection, config: dict | None = None) -> dict:
    """File each new claim conflict once (idempotent by pair_key), same
    audit shape as pairing so FINDINGS / rot R1 / resolve work unchanged."""
    existing = _existing_keys(conn)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    filed, skipped = [], []
    for c in find_claim_conflicts(conn, config):
        if c["pair_key"] in existing:
            skipped.append(c["pair_key"])
            continue
        canon = c.get("canonical")
        text = (f"Cross-source claim conflict: {c['metric']} "
                f"[{c['subject']}] — "
                + " vs ".join(f"{v} ({c['support'].get(v, 0)} claim(s))"
                              for v in c["values"]))
        if canon:
            text = (f"Drift from canon: {c['metric']} [{c['subject']}] — "
                    f"canon ({canon['file']}) says {canon['truth']}; "
                    f"{', '.join(canon['drifted'])} asserted elsewhere")
        finding = AuditResult(
            audit_type="factual",
            target_type="cube",
            target_id=c["a"]["cube_id"],
            finding=text,
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
                "canonical": canon,
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
