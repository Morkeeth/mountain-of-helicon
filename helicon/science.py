"""Agent Science — grade the LIVE store against PUBLISHED thresholds.

Mountain of Helicon compares a document's claim about your running system against
the system (R13). Agent Science points that same move outward: it compares the
*field's* claim about all systems against yours. The literature is public; the
store is Oscar's; that pairing is the product.

The unit of work is a THRESHOLD: a published, falsifiable claim of the shape
`<metric>` degrades past `<scale>` unless `<mitigation>` is present. Each entry
carries the claim, the source, its date, whether the source is a vendor with an
interest in the number (§7: a threshold quoted back at you is still a claim with
an author), the scale it bites at, the mitigation, and a PROBE that reads the
live store and returns a verdict:

  INSIDE        past the scale under every reading AND lacks the mitigation
  CLEAR         not past the scale (mitigation is moot)
  UNMEASURABLE  the scale's unit has no single reading in this store — name
                which reading is missing, never guess

The wedge (PRD §1c): the field publishes thresholds whose UNIT it never defines.
"Interactions" has at least five defensible readings of one store, spanning 529x.
So the verdict is a function of how the readings sit against the scale:

  * one unambiguous reading   -> compare it to the scale.
  * many readings, all on the SAME side of the scale -> the ambiguity is moot;
    return that side's verdict (you are clear/past under every reading).
  * many readings that STRADDLE the scale -> UNMEASURABLE. The answer depends on
    the unit, and the source never said which one it meant. This is the wedge:
    nobody can check their system against the number, including who published it.

Versioning is honest-v1: a threshold is a claim with a date, and `source_date`
carries it. A model upgrade that moves a threshold is a new entry with a new date.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Optional

# Verdicts
INSIDE = "INSIDE"
CLEAR = "CLEAR"
UNMEASURABLE = "UNMEASURABLE"


@dataclass
class Reading:
    """One defensible way to count a threshold's unit against this store.

    `sql` is the exact query that produced `value`, so every printed number
    names the command that reproduces it (PRD §6)."""
    name: str
    value: int
    sql: str


@dataclass
class ProbeResult:
    verdict: str
    readings: list[Reading]
    mitigation_present: Optional[bool]  # None = not determined (or moot)
    mitigation_note: str = ""
    unit_note: str = ""  # for UNMEASURABLE: which reading/unit is unresolved


@dataclass
class Threshold:
    id: str
    claim: str  # stated as PUBLISHED — never our inversion of it
    metric: str
    scale_it_bites_at: int
    scale_unit: str
    mitigation: str
    source: str
    source_date: str
    source_is_vendor: bool
    source_note: str
    probe: Callable  # (conn, config) -> ProbeResult
    reproduce: str = "helicon science"


# --- verdict logic: the wedge, made executable ------------------------------

def classify(readings: list[Reading], scale: int,
             mitigation_present: Optional[bool]) -> str:
    """The verdict, from how the readings sit against the scale.

    Kept pure and free of any DB so it is the unit-testable core: the probes
    below only gather readings and hand them here. `mitigation_present` rescues
    an otherwise-INSIDE stack; None means we could not read it (and, past the
    scale, we cannot assert INSIDE's 'lacks the mitigation', so we say so)."""
    if not readings:
        return UNMEASURABLE
    past = [r.value >= scale for r in readings]
    if not any(past):
        # clear under every reading — ambiguity of the unit is moot
        return CLEAR
    if all(past):
        # past under every reading — only the mitigation can rescue it
        if mitigation_present is True:
            return CLEAR
        if mitigation_present is False:
            return INSIDE
        return UNMEASURABLE  # cannot assert "lacks the mitigation" unmeasured
    # the readings straddle the scale: the answer depends on the undefined unit
    return UNMEASURABLE


# --- readings shared across the interaction-scaled thresholds ---------------

def interaction_readings(conn) -> list[Reading]:
    """The five defensible readings of one word the field never defines.

    'Interactions' is uncheckable as published (PRD §1c). Rather than force one,
    every threshold whose scale is 'interactions' prints the store's number under
    each reading, and the verdict falls out of whether they straddle the scale."""
    specs = [
        ("logged retrievals", "SELECT COUNT(*) FROM retrieval_log"),
        ("human rulings on findings",
         "SELECT COUNT(*) FROM audit_log "
         "WHERE human_decision IS NOT NULL AND human_decision != ''"),
        ("live memories",
         "SELECT COUNT(*) FROM helicon_cubes "
         "WHERE review_status IN ('approved','pending','revised') "
         "AND merged_into IS NULL"),
        ("all review events", "SELECT COUNT(*) FROM reviews"),
        ("all memories ever", "SELECT COUNT(*) FROM helicon_cubes"),
    ]
    out = []
    for name, sql in specs:
        out.append(Reading(name, int(conn.execute(sql).fetchone()[0]), sql))
    return out


def _has_reranker(config: dict) -> bool:
    """Whether retrieval reranks, read from config offline.

    Mirrors embeddings._embed_provider exactly: reranking (qwen3-rerank) is only
    available when the embeddings backend is Qwen-native, i.e. an `embeddings`
    block carrying both api_key and base_url. No network call — a print command
    must not depend on a remote model answering."""
    e = config.get("embeddings") or {}
    return bool(e.get("api_key") and e.get("base_url"))


# --- the probes -------------------------------------------------------------

def _probe_rag_vectors(conn, config) -> ProbeResult:
    n = int(conn.execute("SELECT COUNT(*) FROM cube_embeddings").fetchone()[0])
    reading = Reading("vectors in the store",
                      n, "SELECT COUNT(*) FROM cube_embeddings")
    has_rr = _has_reranker(config)
    verdict = classify([reading], THRESHOLD_RAG.scale_it_bites_at,
                       has_rr)
    note = ("a reranker IS configured (embeddings block is Qwen-native)"
            if has_rr else
            "no reranker configured — retrieval uses the hybrid order")
    return ProbeResult(verdict, [reading], has_rr, note)


def _probe_memory_interactions(conn, config) -> ProbeResult:
    readings = interaction_readings(conn)
    # a validation gate = humans actually ruling on findings before they are
    # trusted; the store's audit-ruling flow is exactly that. Informational here
    # because the unit straddles the scale, which decides the verdict first.
    ruled = next((r.value for r in readings
                  if r.name == "human rulings on findings"), 0)
    gate = ruled > 0
    verdict = classify(readings, THRESHOLD_MEMORY.scale_it_bites_at, gate)
    note = (f"a validation gate is in use ({ruled} human rulings on findings)"
            if gate else "no human rulings found — no validation gate detected")
    unit = ""
    if verdict == UNMEASURABLE:
        unit = ("'interactions' is undefined by the source; your readings "
                "straddle the 10K line, so the threshold cannot say which side "
                "you are on")
    return ProbeResult(verdict, readings, gate, note, unit)


def _probe_hybrid_composition(conn, config) -> ProbeResult:
    readings = interaction_readings(conn)
    verdict = classify(readings, THRESHOLD_HYBRID.scale_it_bites_at, None)
    # every reading is far below 1M, so the ambiguity is moot and the verdict is
    # CLEAR without our having to resolve the unit — the honest opposite face of
    # the memory threshold, same undefined word.
    return ProbeResult(verdict, readings, None,
                       "hybrid composition is the mitigation the claim credits; "
                       "moot below the scale under every reading")


# --- the registry -----------------------------------------------------------
#
# All three thresholds come from one secondary blog aggregation. Per PRD §7 that
# source is one of the two vendor blogs (mem0 is the other, and it sells memory);
# a threshold from a blog that is not the primary benchmark is marked as such so
# the number is never quoted back as if it were peer-reviewed ground truth.

_RANKSQUIRE = "ranksquire.com — 'Agent Memory vs RAG: what breaks at scale'"
_RANKSQUIRE_DATE = "2026-03-31"
_RANKSQUIRE_NOTE = ("secondary blog aggregation, not a primary benchmark; "
                    "treat the exact number as a claim with an author")

THRESHOLD_RAG = Threshold(
    id="rag-precision-500k",
    claim="RAG precision drops below 80% past 500K vectors without a reranker.",
    metric="RAG retrieval precision",
    scale_it_bites_at=500_000,
    scale_unit="vectors",
    mitigation="a reranker (two-stage retrieval)",
    source=_RANKSQUIRE,
    source_date=_RANKSQUIRE_DATE,
    source_is_vendor=True,
    source_note=_RANKSQUIRE_NOTE,
    probe=_probe_rag_vectors,
)

THRESHOLD_MEMORY = Threshold(
    id="memory-accuracy-10k",
    claim="Agent memory accuracy drops below 85% past 10K interactions "
          "without a validation gate.",
    metric="agent memory accuracy",
    scale_it_bites_at=10_000,
    scale_unit="interactions",
    mitigation="a validation gate",
    source=_RANKSQUIRE,
    source_date=_RANKSQUIRE_DATE,
    source_is_vendor=True,
    source_note=_RANKSQUIRE_NOTE,
    probe=_probe_memory_interactions,
)

THRESHOLD_HYBRID = Threshold(
    id="hybrid-1m",
    claim="Hybrid composition (RAG for documents, agent memory for experience, "
          "in-context for session, recursive summarisation) holds 90%+ "
          "reliability at 1M interactions.",
    metric="stack reliability",
    scale_it_bites_at=1_000_000,
    scale_unit="interactions",
    mitigation="hybrid composition",
    source=_RANKSQUIRE,
    source_date=_RANKSQUIRE_DATE,
    source_is_vendor=True,
    source_note=_RANKSQUIRE_NOTE,
    probe=_probe_hybrid_composition,
)

REGISTRY: list[Threshold] = [THRESHOLD_RAG, THRESHOLD_MEMORY, THRESHOLD_HYBRID]


# --- rendering --------------------------------------------------------------

def _repro_sql(db_path: str, sql: str) -> str:
    esc = sql.replace('"', '\\"')
    return f'sqlite3 {db_path} "{esc}"'


def render(conn, config: dict, db_path: str) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append("Agent Science — which published threshold is your stack on "
                 "the wrong side of?")
    lines.append("A threshold quoted back at you is still a claim with an "
                 "author. Sources and dates below; [vendor] is flagged.")
    lines.append("")

    counts = {INSIDE: 0, CLEAR: 0, UNMEASURABLE: 0}
    for t in REGISTRY:
        res = t.probe(conn, config)
        counts[res.verdict] = counts.get(res.verdict, 0) + 1
        vendor = " [vendor]" if t.source_is_vendor else ""
        lines.append(f"── {t.id} ─ verdict: {res.verdict}")
        lines.append(f"   published: {t.claim}")
        lines.append(f"   source:    {t.source}, {t.source_date}{vendor}")
        lines.append(f"              ({t.source_note})")
        lines.append(f"   scale:     {t.scale_it_bites_at:,} {t.scale_unit}  "
                     f"·  mitigation: {t.mitigation}")
        if len(res.readings) == 1:
            r = res.readings[0]
            lines.append(f"   your number: {r.value:,} {t.scale_unit}")
            lines.append(f"     reproduce: {_repro_sql(db_path, r.sql)}")
        else:
            lines.append(f"   your number: '{t.scale_unit}' has "
                         f"{len(res.readings)} defensible readings — printed "
                         f"under each, never forced into one:")
            for r in res.readings:
                mark = " (> scale)" if r.value >= t.scale_it_bites_at else ""
                lines.append(f"     - {r.name:28s} {r.value:>8,}{mark}")
                lines.append(f"         reproduce: {_repro_sql(db_path, r.sql)}")
        if res.mitigation_note:
            lines.append(f"   mitigation:  {res.mitigation_note}")
        if res.unit_note:
            lines.append(f"   why {UNMEASURABLE}: {res.unit_note}")
        lines.append(f"   reproduce this line: {t.reproduce}")
        lines.append("")

    lines.append(f"Verdicts: {counts[INSIDE]} INSIDE · {counts[CLEAR]} CLEAR · "
                 f"{counts[UNMEASURABLE]} UNMEASURABLE  "
                 f"(across {len(REGISTRY)} thresholds)")
    lines.append("")
    return "\n".join(lines)


def run(config: dict) -> str:
    from helicon.db import init_db
    db_path = config["db_path"]
    conn = init_db(db_path)
    return render(conn, config, db_path)


def collect(conn, config: dict, db_path: str) -> dict:
    """Structured probe results for Firestore / JSON witnesses."""
    verdicts = []
    counts = {INSIDE: 0, CLEAR: 0, UNMEASURABLE: 0}
    for t in REGISTRY:
        res = t.probe(conn, config)
        counts[res.verdict] = counts.get(res.verdict, 0) + 1
        readings = [
            {
                "name": r.name,
                "value": r.value,
                "sql": r.sql,
                "repro": _repro_sql(db_path, r.sql),
                "past_scale": r.value >= t.scale_it_bites_at,
            }
            for r in res.readings
        ]
        span = None
        if len(readings) > 1:
            vals = [r["value"] for r in readings]
            lo, hi = min(vals), max(vals)
            span = (hi / lo) if lo > 0 else None
        verdicts.append({
            "id": t.id,
            "verdict": res.verdict,
            "claim": t.claim,
            "scale": t.scale_it_bites_at,
            "scale_unit": t.scale_unit,
            "mitigation": t.mitigation,
            "source": t.source,
            "source_date": t.source_date,
            "source_is_vendor": t.source_is_vendor,
            "readings": readings,
            "reading_span": span,
            "mitigation_present": res.mitigation_present,
            "mitigation_note": res.mitigation_note,
            "unit_note": res.unit_note,
            "repro_command": t.reproduce,
        })
    return {
        "verdicts": verdicts,
        "inside_count": counts[INSIDE],
        "clear_count": counts[CLEAR],
        "unmeasurable_count": counts[UNMEASURABLE],
    }
