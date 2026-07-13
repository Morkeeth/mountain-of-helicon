"""R11 — Identity Coherence Gate.

One entity's DEFINITION forks across sources: same name, incompatible genera
(e.g. "Yieldbound is a yield treasury" in one source vs "Yieldbound is a wallet
tracker" in another). R1's contradiction gate is blind to this — it only fires on
a typed scalar slot (date/number/status), and a definition is free prose with no
value slot. R11 catches the fork deterministically: reduce each defining clause to
its head-noun GENUS; if one name carries >=2 distinct genera across >=2 source
scopes, its identity has forked.

Deterministic, LLM-free, high precision — the demo-able core of the identity gate.
Files findings on the same audit_log plumbing as pairing/claims (pair_key namespace
'identity|<name>'), so FINDINGS / rot R11 / resolve work unchanged.
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from helicon.db import insert_audit
from helicon.models import AuditResult
from helicon.pairing import _cube_scope

# A defining clause: <Name> <copula> <predicate>. Name is a proper noun (capitalized,
# >=3 chars, may carry digits/dot/hyphen for product names). Predicate is a lowercase
# noun phrase we reduce to its head noun.
_NAME = r"([A-Z][A-Za-z0-9][A-Za-z0-9.\-]{1,30})"
# Whole words only (no mid-word truncation): 1-8 lowercase words.
_PRED = r"([a-z][a-z0-9\-]*(?:\s+[a-z][a-z0-9\-]*){0,7})"
# Every pattern REQUIRES an article (a / an / the) before the predicate. This is
# the precision gate: "Yieldbound is a yield treasury" (definition) matches, but
# "Relay is live", "node is old", "commit is feat" (status/adjective prose) do not
# — you don't write "is a live". Article-gating turns a noisy copular match into a
# genus-noun match without a POS tagger.
_DEFINE = [
    re.compile(rf"\b{_NAME}\s+is\s+(?:an?|the)\s+{_PRED}"),
    re.compile(rf"\b{_NAME},\s+an?\s+{_PRED}"),
    re.compile(rf"\b{_NAME}\s*:\s+an?\s+{_PRED}"),
]

# Words that end the head phrase — the genus is the head BEFORE these join a
# dependent clause ("protocol FOR spending yield" -> protocol, not yield).
_CUT = {"for", "that", "which", "who", "whose", "to", "with", "on", "in", "of",
        "and", "but", "using", "built", "designed", "meant", "used", "where",
        "when", "so", "as", "from", "by", "at", "until", "unless", "while",
        "once", "after", "before", "since", "not", "just", "only", "still",
        "now", "then", "here", "there", "if", "or", "nor", "yet"}
# Names too generic to be an entity identity (avoid "This is a tool" noise).
_NOT_A_NAME = {"this", "that", "there", "here", "it", "he", "she", "they", "the",
               "and", "but", "helicon", "note", "todo", "done", "fixed", "why",
               "how", "what", "created", "edited", "resolved", "status", "update",
               "oscar", "i", "we", "you", "everything", "nothing", "each", "both"}
# Predicate heads too generic to mean anything (a definition of "a thing" is noise).
_VOID_GENUS = {"thing", "way", "one", "part", "bit", "kind", "type", "set", "lot",
               "place", "case", "point", "idea", "note", "example", "version",
               "result", "reason", "process", "system", "list", "file", "doc",
               # status/adjective words that slip past the article gate
               "live", "old", "new", "dead", "gone", "done", "ready", "good",
               "bad", "open", "closed", "active", "shipped", "running", "banned",
               "real", "fake", "big", "small", "key", "core", "main", "must",
               "win", "loss", "draft", "final", "hit", "miss", "go", "no",
               "remote", "long", "long-time", "same", "one", "first", "last",
               "next", "only", "such", "own", "sole", "single"}


def _genus(pred: str) -> str | None:
    """Reduce a predicate noun phrase to its head-noun genus (singular, lower)."""
    words = pred.strip().lower().split()
    head = []
    for w in words:
        w = w.strip(".,;:!?")
        if not w:
            continue
        if w in _CUT:
            break
        head.append(w)
    if not head:
        return None
    genus = head[-1]                       # English compounds are head-final
    if genus.endswith("s") and len(genus) > 4:
        genus = genus[:-1]                 # crude singularize
    if len(genus) < 3 or genus in _VOID_GENUS:
        return None
    return genus


def extract_glosses(content: str, title: str = "") -> list[dict]:
    """Defining clauses found in the text: [{name, genus, gloss}]."""
    text = f"{title}. {content}" if title else content
    out, seen = [], set()
    for pat in _DEFINE:
        for m in pat.finditer(text):
            name, pred = m.group(1), m.group(2)
            if name.lower() in _NOT_A_NAME:
                continue
            genus = _genus(pred)
            if not genus or genus == name.lower():
                continue
            key = (name.lower(), genus)
            if key in seen:
                continue
            seen.add(key)
            gloss = m.group(0).strip()
            out.append({"name": name, "genus": genus, "gloss": gloss[:120]})
    return out


# Stage-2 gate: two glosses whose embeddings sit below this cosine are genuinely
# different definitions (empirically ~0.31 for treasury/tracker); same-concept
# rephrasings sit ~0.54+ ("verification layer" vs "layer") and are dropped.
SEMANTIC_FORK_THRESHOLD = 0.45


def find_identity_forks(conn, semantic: bool = True) -> list[dict]:
    """Names whose definition forks: >=2 distinct genera across >=2 source scopes,
    and the two genera are attested by DIFFERENT scopes (a real cross-source fork,
    not one cube listing two genera).

    semantic=True adds the stage-2 confirmation: embed the two glosses (local model,
    no LLM) and keep only genuinely-divergent definitions, dropping same-concept
    rephrasings. Falls back to the deterministic genus tier if embeddings are
    unavailable. Pass semantic=False for the fast rot exam and deterministic tests."""
    rows = conn.execute(
        "SELECT id, title, content, source, source_ref, created_at, review_status "
        "FROM helicon_cubes "
        "WHERE review_status IN ('pending', 'revised', 'approved') "
        "AND merged_into IS NULL"
    ).fetchall()

    from helicon.timeutil import ts_norm
    # name -> genus -> {scope: gloss}; and the latest timestamp per (name, genus)
    by_name: dict = defaultdict(lambda: defaultdict(dict))
    latest: dict = defaultdict(lambda: defaultdict(str))
    for row in rows:
        scope = _cube_scope(row)
        ts = ts_norm(row["created_at"]) or (row["created_at"] or "")
        for g in extract_glosses(row["content"] or "", row["title"] or ""):
            n, gen = g["name"].lower(), g["genus"]
            by_name[n][gen].setdefault(scope, g["gloss"])
            if ts > latest[n][gen]:
                latest[n][gen] = ts

    resolutions = _load_identity_resolutions(conn)
    candidates = []
    for name, genera in by_name.items():
        res = resolutions.get(name)
        if res:
            # never-twice: a settled name re-alarms ONLY when a NON-canonical genus
            # is asserted AFTER the ruling. Re-stating the canonical definition, or
            # an old divergent cube that predates the ruling, stays settled.
            cg, rt = res["genus"], res["resolved_at"]
            divergent = [g for g in genera if g != cg and latest[name][g] > rt]
            if not divergent:
                continue
            gb = max(divergent, key=lambda g: len(genera[g]))
            scopes = set(genera[gb]) | (set(genera[cg]) if cg in genera else set())
            candidates.append({
                "name": name,
                "pair_key": f"identity|{name}|resurfaced:{rt}",
                "genera": {gen: sorted(sc) for gen, sc in genera.items()},
                "genus_a": cg, "genus_b": gb,
                "gloss_a": f"canonical: {cg}",
                "gloss_b": next(iter(genera[gb].values())),
                "scopes": sorted(scopes),
                "resurfaced": True,
            })
            continue
        # unresolved: a genuine cross-source fork (>=2 genera from >=2 scopes)
        if len(genera) < 2:
            continue
        all_scopes = set().union(*(set(s) for s in genera.values()))
        if len(all_scopes) < 2:
            continue
        pairs = [(gen, sc) for gen, scopes in genera.items() for sc in scopes]
        cross = any(g1 != g2 and s1 != s2
                    for g1, s1 in pairs for g2, s2 in pairs)
        if not cross:
            continue
        ranked = sorted(genera.items(), key=lambda kv: -len(kv[1]))
        top = ranked[:2]
        candidates.append({
            "name": name,
            "pair_key": f"identity|{name}",
            "genera": {gen: sorted(scopes) for gen, scopes in genera.items()},
            "genus_a": top[0][0], "genus_b": top[1][0],
            "gloss_a": next(iter(top[0][1].values())),
            "gloss_b": next(iter(top[1][1].values())),
            "scopes": sorted(all_scopes),
            "resurfaced": False,
        })

    if not semantic or not candidates:
        return candidates
    # stage 2: semantic confirmation — drop same-concept "forks" (local embeddings,
    # no LLM). If the model is unavailable, keep the genus-tier candidates.
    try:
        import numpy as np
        from helicon.embeddings import embed_text
    except Exception:
        return candidates
    confirmed = []
    for f in candidates:
        if f.get("resurfaced"):
            confirmed.append(f)          # a ruled-out definition returned — never-twice
            continue
        try:
            va, vb = embed_text(f["gloss_a"]), embed_text(f["gloss_b"])
            denom = (float(np.linalg.norm(va)) * float(np.linalg.norm(vb))) or 1.0
            cos = float(np.dot(va, vb)) / denom
        except Exception:
            confirmed.append(f)          # embedding failed → don't silently drop
            continue
        f["cosine"] = round(cos, 3)
        if cos < SEMANTIC_FORK_THRESHOLD:
            confirmed.append(f)
    return confirmed


def _load_identity_resolutions(conn) -> dict:
    """name (lower) -> {'genus': canonical genus, 'resolved_at': normalized ts}."""
    from helicon.timeutil import ts_norm
    out = {}
    for row in conn.execute(
        "SELECT details, resolved_at FROM audit_log WHERE audit_type = 'identity' "
        "AND human_decision LIKE 'resolved:%'"
    ):
        try:
            d = json.loads(row["details"])
        except (json.JSONDecodeError, TypeError):
            continue
        n = (d.get("name") or "").lower()
        if not n:
            continue
        out[n] = {"genus": d.get("canonical_genus", ""),
                  "resolved_at": ts_norm(row["resolved_at"]) or (row["resolved_at"] or "")}
    return out


def resolve_identity(conn, audit_id: int, canonical: str) -> dict:
    """Rule an identity fork with its canonical definition. Writes an approved
    correction cube (full provenance) so retrieval serves the settled identity, and
    closes the finding — find_identity_forks then skips this name (the fork stays
    settled). Re-alarm on a genuinely NEW divergent genus is the next increment."""
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (audit_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": f"no audit finding #{audit_id}"}
    if row["audit_type"] != "identity":
        return {"ok": False, "error": f"finding #{audit_id} is not an identity fork"}
    if row["human_decision"]:
        return {"ok": False, "error": f"finding #{audit_id} already decided: "
                                      f"{row['human_decision']}"}
    canonical = (canonical or "").strip()
    if not canonical:
        return {"ok": False, "error": "canonical definition is empty"}
    try:
        d = json.loads(row["details"])
    except (json.JSONDecodeError, TypeError):
        d = {}
    name = d.get("name", "")
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    # store the canonical GENUS so the never-twice guard can tell a re-assertion of
    # the settled definition (fine) from a genuinely new divergent one (re-alarm)
    canonical_genus = _genus(canonical) or (canonical.split() or [canonical])[-1].lower()
    conn.execute(
        "UPDATE audit_log SET human_decision = ?, resolved_at = ?, "
        "details = json_set(details, '$.canonical_genus', ?) WHERE id = ?",
        (f"resolved:{canonical[:80]}", now, canonical_genus, audit_id))

    from helicon.models import HeliconCube
    from helicon.scanner import make_id, content_hash as _hash
    from helicon.db import insert_cube
    genera = ", ".join(d.get("genera", {}).keys())
    content = (f"{name.title()} is canonically: {canonical} "
               f"(human resolution of identity fork #{audit_id}, {now[:10]}). "
               f"The competing definitions ({genera}) were a fork; this is settled.")
    cube = HeliconCube(
        id=make_id(), source="human-resolution", source_ref=f"audit:{audit_id}",
        type="decision", title=f"Canonical: {name.title()} = {canonical[:60]}",
        content=content, summary="", content_hash=_hash(content),
        created_at=now, valid_from=now, last_reinforced=now,
        confidence=1.0, review_status="approved",
    )
    insert_cube(conn, cube)
    conn.commit()
    return {"ok": True, "audit_id": audit_id, "name": name,
            "canonical": canonical, "correction_cube": cube.id}


def _existing_identity_keys(conn) -> set[str]:
    keys = set()
    for row in conn.execute(
        "SELECT details FROM audit_log WHERE audit_type = 'identity'"
    ):
        try:
            k = json.loads(row["details"]).get("pair_key")
            if k:
                keys.add(k)
        except (json.JSONDecodeError, TypeError):
            pass
    return keys


def identity_scan(conn, semantic: bool = True) -> dict:
    """File one finding per identity fork (idempotent by pair_key)."""
    existing = _existing_identity_keys(conn)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    filed, skipped = [], []
    for fork in find_identity_forks(conn, semantic=semantic):
        if fork["pair_key"] in existing:
            skipped.append(fork["pair_key"])
            continue
        genera_str = " vs ".join(
            f"{g} ({len(s)} source{'s' if len(s) > 1 else ''})"
            for g, s in sorted(fork["genera"].items(), key=lambda kv: -len(kv[1])))
        text = (f"Identity fork: '{fork['name']}' is defined as {genera_str} "
                f"across {len(fork['scopes'])} sources — same name, forked definition")
        finding = AuditResult(
            audit_type="identity",
            target_type="entity",
            target_id=fork["name"],
            finding=text,
            severity="warning",
            proposed_action="flag",
            details={
                "pair_key": fork["pair_key"], "name": fork["name"],
                "genera": fork["genera"],
                "value_a": fork["genus_a"], "value_b": fork["genus_b"],
                "line_a": fork["gloss_a"], "line_b": fork["gloss_b"],
                "scopes": fork["scopes"], "judged_by": "deterministic",
            },
            audited_at=now,
        )
        if insert_audit(conn, finding) is not None:
            filed.append({"pair_key": fork["pair_key"], "finding": finding.finding})
    conn.commit()
    return {"forks_found": len(filed) + len(skipped),
            "filed": filed, "already_filed": skipped}
