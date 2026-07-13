"""R12 — Relation Provenance / Phantom Association gate.

A relation asserted between two entities that no source ever grounded ("Yieldbound
rides the agent-payments wave → World") looks plausible and propagates. R1 (scalar
contradiction) and R11 (definition fork) are both blind to it — there is no value
slot and no forked genus, just a confident edge nobody backs.

R12 distinguishes an ASSERTED relation from a GROUNDED one. Deterministic and high
precision by construction: BOTH endpoints must be known entities, joined by an
explicit relational verb; and it fires only when the relation rests on a SINGLE
speculative source (idea / draft / session) with NO independent corroboration
(no other source even co-mentions the two entities). That is a phantom.
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from helicon.db import insert_audit
from helicon.models import AuditResult
from helicon.pairing import _cube_scope

# Explicit relational predicates joining two named entities. CONCEPTUAL / business
# relations only — code keywords (extends, wraps, implements, built on/into) are
# deliberately excluded, they fire on class declarations, not phantom associations.
_REL_VERBS = (
    r"integrates with|rides the wave to|rides|powered by|acquired by|merged with|"
    r"partners with|competes with|spun out of|part of|is part of|owned by|"
    r"belongs to|feeds into|plugs into|is built on top of"
)
_NAME = r"([A-Z][A-Za-z0-9][A-Za-z0-9.\-]{1,30})"
_REL_RE = re.compile(rf"\b{_NAME}\s+(?:{_REL_VERBS})\s+(?:the\s+|an?\s+)?{_NAME}\b")

# A cube whose claim is a guess until grounded elsewhere.
_SPECULATIVE_TYPES = {"idea", "draft", "session", "session_summary"}
_SPECULATIVE_REF = ("/03 ideas", "session_", "session-", "/ideas", "brainstorm", "speculat")
# A memory (incl. a Mem0/store memory) tagged as a guess reads as speculative even
# though its type is generic — an LLM-extracted "thesis"/"prediction" isn't grounded.
_SPECULATIVE_TAGS = {"idea", "thesis", "prediction", "speculation", "hypothesis",
                     "brainstorm", "guess", "bet"}
# Entity names too generic/junky to anchor a relation.
_JUNK = {"at", "the", "and", "for", "with", "this", "that", "it", "a", "an", "of"}


def _known_entities(conn) -> set[str]:
    """Lowercased known-entity names (the precision gate). Filters junk rows."""
    out = set()
    for row in conn.execute("SELECT name FROM entities"):
        n = (row["name"] or "").strip().lower()
        if len(n) >= 3 and n not in _JUNK:
            out.add(n)
    return out


def _grounding(row) -> str:
    typ = (row["type"] or "").lower()
    ref = (row["source_ref"] or "").lower()
    tags = []
    try:
        if "tags" in row.keys() and row["tags"]:
            tags = [str(t).lower() for t in json.loads(row["tags"])]
    except (ValueError, TypeError):
        tags = []
    if (typ in _SPECULATIVE_TYPES or any(k in ref for k in _SPECULATIVE_REF)
            or any(t in _SPECULATIVE_TAGS for t in tags)):
        return "speculative"
    return "grounded"


def _mentions(text_lower: str, name: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\b", text_lower) is not None


def extract_relations(content: str, title: str = "", known: set[str] | None = None) -> list[dict]:
    """Explicit relation triples where BOTH endpoints are known entities."""
    text = f"{title}. {content}" if title else content
    out, seen = [], set()
    for m in _REL_RE.finditer(text):
        subj, obj = m.group(1).lower(), m.group(2).lower()
        if subj == obj:
            continue
        if known is not None and (subj not in known or obj not in known):
            continue
        key = (subj, obj)
        if key in seen:
            continue
        seen.add(key)
        pred = re.sub(rf"^{_NAME}\s+", "", m.group(0))
        pred = re.sub(rf"\s+{_NAME}$", "", pred).strip()
        out.append({"subj": subj, "obj": obj, "predicate": pred[:40], "gloss": m.group(0)[:120]})
    return out


def _corroborated_elsewhere(conn, subj: str, obj: str, asserting_scope: str) -> bool:
    """Does any OTHER source even co-mention both entities? Substring match is
    deliberately generous here — over-corroboration means we DON'T flag, the safe
    direction (never falsely accuse a real-but-undocumented relation)."""
    rows = conn.execute(
        "SELECT source, source_ref FROM helicon_cubes "
        "WHERE review_status IN ('pending', 'revised', 'approved') AND merged_into IS NULL "
        "AND lower(title || ' ' || content) LIKE ? AND lower(title || ' ' || content) LIKE ?",
        (f"%{subj}%", f"%{obj}%")).fetchall()
    return any(_cube_scope(r) != asserting_scope for r in rows)


def find_phantom_relations(conn) -> list[dict]:
    """Relations that rest on a single speculative source with no corroboration.
    Precision from: a narrow relational-verb list + both endpoints capitalized +
    the single-speculative-source filter + the no-corroboration check."""
    rows = conn.execute(
        "SELECT id, title, content, source, source_ref, type, tags, review_status "
        "FROM helicon_cubes "
        "WHERE review_status IN ('pending', 'revised', 'approved') "
        "AND merged_into IS NULL"
    ).fetchall()

    resolved = _resolved_relation_keys(conn)
    asserts: dict = {}                       # (subj,obj) -> record
    for row in rows:
        scope = _cube_scope(row)
        for r in extract_relations(row["content"] or "", row["title"] or ""):
            rec = asserts.setdefault((r["subj"], r["obj"]), {
                "predicate": r["predicate"], "gloss": r["gloss"],
                "scopes": set(), "grounding": set(), "cubes": []})
            rec["scopes"].add(scope)
            rec["grounding"].add(_grounding(row))
            rec["cubes"].append(row["id"])

    phantoms = []
    for (subj, obj), rec in asserts.items():
        if f"relation|{subj}|{obj}" in resolved:
            continue                          # ruled (phantom or real) → stays settled
        if len(rec["scopes"]) != 1:
            continue                          # multiple sources assert it → not phantom
        if "speculative" not in rec["grounding"]:
            continue                          # a grounded source stated it
        asserting_scope = next(iter(rec["scopes"]))
        if _corroborated_elsewhere(conn, subj, obj, asserting_scope):
            continue                          # another source connects them → not phantom
        phantoms.append({
            "subj": subj, "obj": obj, "predicate": rec["predicate"],
            "gloss": rec["gloss"], "pair_key": f"relation|{subj}|{obj}",
            "scope": asserting_scope, "cubes": rec["cubes"],
        })
    return phantoms


def _upsert_entity(conn, name: str) -> str:
    """Entity id for `name`, created if absent (lowercased key)."""
    from helicon.graph import make_id
    row = conn.execute("SELECT id FROM entities WHERE lower(name) = ?",
                       (name.lower(),)).fetchone()
    if row:
        return row["id"]
    eid = make_id()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn.execute("INSERT INTO entities (id, name, entity_type, mention_count, "
                 "first_seen, last_seen) VALUES (?, ?, 'concept', 1, ?, ?)",
                 (eid, name, now, now))
    return eid


def store_asserts_edges(conn) -> dict:
    """Write each extracted relation as an 'asserts' edge with provenance in
    edges.metadata {subj, obj, asserted_by_cube, predicate, source_scope, grounding}.
    Idempotent by (source, target). build_graph preserves 'asserts' edges."""
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    # a pair a human already ruled phantom stays retired even after regeneration
    phantom_ruled = set()
    for row in conn.execute("SELECT details FROM audit_log WHERE audit_type = 'provenance' "
                            "AND human_decision = 'resolved:phantom'"):
        try:
            d = json.loads(row["details"])
            phantom_ruled.add((d.get("subj"), d.get("obj")))
        except (json.JSONDecodeError, TypeError):
            pass
    rows = conn.execute(
        "SELECT id, title, content, source, source_ref, type, tags "
        "FROM helicon_cubes WHERE review_status IN ('pending', 'revised', 'approved') "
        "AND merged_into IS NULL").fetchall()
    written = 0
    for row in rows:
        scope, grounding = _cube_scope(row), _grounding(row)
        for r in extract_relations(row["content"] or "", row["title"] or ""):
            sid, tid = _upsert_entity(conn, r["subj"]), _upsert_entity(conn, r["obj"])
            if conn.execute("SELECT 1 FROM edges WHERE source_id = ? AND target_id = ? "
                            "AND relation = 'asserts'", (sid, tid)).fetchone():
                continue
            meta = json.dumps({"subj": r["subj"], "obj": r["obj"],
                               "asserted_by_cube": row["id"], "predicate": r["predicate"],
                               "source_scope": scope, "grounding": grounding,
                               "retired": (r["subj"], r["obj"]) in phantom_ruled})
            conn.execute(
                "INSERT INTO edges (source_id, target_id, source_kind, target_kind, "
                "relation, weight, created_at, metadata) "
                "VALUES (?, ?, 'entity', 'entity', 'asserts', 1.0, ?, ?)",
                (sid, tid, now, meta))
            written += 1
    conn.commit()
    return {"asserts_edges": written}


def _retire_asserts_edge(conn, subj: str, obj: str) -> list[str]:
    """A ruled phantom retires its 'asserts' edge and flags the cube that made the
    claim (so retrieval/graph stop treating the ungrounded relation as real)."""
    flagged = []
    for erow in conn.execute("SELECT id, metadata FROM edges WHERE relation = 'asserts'"):
        try:
            m = json.loads(erow["metadata"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if m.get("subj") == subj and m.get("obj") == obj and not m.get("retired"):
            m["retired"] = True
            conn.execute("UPDATE edges SET metadata = ? WHERE id = ?",
                         (json.dumps(m), erow["id"]))
            cid = m.get("asserted_by_cube")
            if cid:
                conn.execute(
                    "UPDATE helicon_cubes SET metadata = json_set("
                    "CASE WHEN metadata IS NULL OR metadata = '' THEN '{}' ELSE metadata END, "
                    "'$.phantom_flagged', 1) WHERE id = ?", (cid,))
                flagged.append(cid)
    return flagged


def _resolved_relation_keys(conn) -> set[str]:
    """pair_keys of phantom findings a human has already ruled (phantom or real)."""
    keys = set()
    for row in conn.execute(
        "SELECT details FROM audit_log WHERE audit_type = 'provenance' "
        "AND human_decision IS NOT NULL"
    ):
        try:
            k = json.loads(row["details"]).get("pair_key")
            if k:
                keys.add(k)
        except (json.JSONDecodeError, TypeError):
            pass
    return keys


def resolve_relation(conn, audit_id: int, verdict: str = "phantom") -> dict:
    """Rule a phantom-association finding. verdict 'phantom' = confirmed ungrounded
    (writes an approved correction cube recording the ruling so the store carries the
    counter-evidence); any other verdict (e.g. 'real') just closes it as real-but-
    undocumented. Either way the pair stays settled — the scan won't re-file it."""
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (audit_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": f"no audit finding #{audit_id}"}
    if row["audit_type"] != "provenance":
        return {"ok": False, "error": f"finding #{audit_id} is not a phantom-association finding"}
    if row["human_decision"]:
        return {"ok": False, "error": f"finding #{audit_id} already decided: "
                                      f"{row['human_decision']}"}
    try:
        d = json.loads(row["details"])
    except (json.JSONDecodeError, TypeError):
        d = {}
    subj, obj = d.get("subj", ""), d.get("obj", "")
    verdict = (verdict or "phantom").strip().lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn.execute("UPDATE audit_log SET human_decision = ?, resolved_at = ? WHERE id = ?",
                 (f"resolved:{verdict}", now, audit_id))
    cube_id, flagged = None, []
    if verdict == "phantom":
        from helicon.models import HeliconCube
        from helicon.scanner import make_id, content_hash as _hash
        from helicon.db import insert_cube
        content = (f"The association '{subj} {d.get('predicate', '')} {obj}' is a PHANTOM — "
                   f"human-ruled ungrounded (finding #{audit_id}, {now[:10]}). No source "
                   f"grounds it; do not treat {subj} and {obj} as related on this basis.")
        cube = HeliconCube(
            id=make_id(), source="human-resolution", source_ref=f"audit:{audit_id}",
            type="decision", title=f"Phantom association ruled: {subj} ↛ {obj}",
            content=content, summary="", content_hash=_hash(content),
            created_at=now, valid_from=now, last_reinforced=now,
            confidence=1.0, review_status="approved")
        insert_cube(conn, cube)
        cube_id = cube.id
        flagged = _retire_asserts_edge(conn, subj, obj)
    conn.commit()
    return {"ok": True, "audit_id": audit_id, "subj": subj, "obj": obj,
            "verdict": verdict, "correction_cube": cube_id, "flagged_cubes": flagged}


def _existing_relation_keys(conn) -> set[str]:
    keys = set()
    for row in conn.execute("SELECT details FROM audit_log WHERE audit_type = 'provenance'"):
        try:
            k = json.loads(row["details"]).get("pair_key")
            if k:
                keys.add(k)
        except (json.JSONDecodeError, TypeError):
            pass
    return keys


def relation_scan(conn) -> dict:
    """File one finding per phantom relation (idempotent by pair_key)."""
    existing = _existing_relation_keys(conn)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    filed, skipped = [], []
    for p in find_phantom_relations(conn):
        if p["pair_key"] in existing:
            skipped.append(p["pair_key"])
            continue
        text = (f"Phantom association: '{p['subj']}' {p['predicate']} '{p['obj']}' is "
                f"asserted by a single speculative source with no corroboration — "
                f"a relation no other source grounds")
        finding = AuditResult(
            audit_type="provenance",
            target_type="relation",
            target_id=f"{p['subj']}|{p['obj']}",
            finding=text,
            severity="warning",
            proposed_action="flag",
            details={
                "pair_key": p["pair_key"], "subj": p["subj"], "obj": p["obj"],
                "predicate": p["predicate"], "line_a": p["gloss"],
                "scopes": [p["scope"]], "judged_by": "deterministic",
            },
            audited_at=now,
        )
        if insert_audit(conn, finding) is not None:
            filed.append({"pair_key": p["pair_key"], "finding": finding.finding})
    conn.commit()
    return {"phantoms_found": len(filed) + len(skipped),
            "filed": filed, "already_filed": skipped}
