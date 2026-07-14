"""Auto-attribution: output failure -> the memory that caused it.

The edge SUBMISSION.md admits is not airtight. `review --terminals` catches a
contradicted output; `resolve_review` writes a correction. But neither points at
the pre-existing MEMORY whose content made the agent assert the false thing, so
the rot survives. This closes that: given a flagged output claim, retrieve the
cube(s) that assert the same thing (deterministic FTS, no LLM, no guess), so the
human can retire the actual cause in one ruling. output -> attribute -> rule ->
law, as one path.
"""
import json
import re

_STOP = {"the", "a", "an", "is", "are", "was", "were", "and", "or", "of", "to",
         "in", "on", "for", "not", "no", "it", "this", "that", "with", "as", "at",
         "verified", "unverified", "contradicted", "claims", "claim", "test", "tests"}


def _keywords(text: str) -> list[str]:
    """FTS-safe content words from a claim (drop punctuation + stopwords)."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_./-]{2,}", text.lower())
    seen, out = set(), []
    for w in words:
        w = w.strip("./-")                      # keep path/version dots inside, not trailing
        if len(w) < 3 or w in _STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out[:8]


def attribute_finding(conn, finding_row, limit: int = 5) -> dict:
    """The causal trace: memory cubes whose content asserts the flagged claim.
    Deterministic FTS retrieval; excludes our own output-review corrections and
    already-retired memory. Returns the candidates a human would retire."""
    try:
        d = json.loads(finding_row["details"] or "{}")
    except (json.JSONDecodeError, TypeError):
        d = {}
    finding = finding_row["finding"] or ""
    claim = finding.split(":", 1)[-1].strip() if ":" in finding else finding
    kws = _keywords(claim)
    if not kws:
        return {"claim": claim, "keywords": [], "candidates": []}
    query = " OR ".join(kws)
    from helicon.db import search_cubes
    try:
        hits = search_cubes(conn, query, limit=limit * 3)
    except Exception:
        hits = []
    out = []
    for h in hits:
        if h.get("source") == "output-review":     # our own corrections, not causes
            continue
        out.append({
            "id": h["id"], "title": h.get("title", ""), "source": h.get("source", ""),
            "source_ref": h.get("source_ref", ""),
            "snippet": " ".join((h.get("content") or "").split())[:140],
        })
        if len(out) >= limit:
            break
    return {"claim": claim, "keywords": kws, "candidates": out,
            "terminal": finding_row["target_id"] if "target_id" in finding_row.keys() else d.get("terminal")}


def retire_cube(conn, cube_id: str, superseded_by: str, reason: str = "") -> bool:
    """Retire a memory cube: mark it superseded and point it at what replaced it,
    so retrieval (which excludes superseded) stops serving the rot. Reversible via
    review_status. Returns False if the cube does not exist."""
    row = conn.execute("SELECT id FROM helicon_cubes WHERE id = ?", (cube_id,)).fetchone()
    if row is None:
        return False
    conn.execute(
        "UPDATE helicon_cubes SET review_status = 'superseded', merged_into = ? "
        "WHERE id = ?", (superseded_by, cube_id))
    conn.commit()
    return True
