"""The reading — open the record and it tells you who you are.

Not a dashboard of numbers. A portrait, composed from what your memory actually
holds: who and what recur, the kind of work you make, how much of the record is
still true, and the three moves the record itself argues for.

The digest is deterministic and free (counts, entities, output mix, health).
Qwen does one thing: turn that digest into a grounded reading, in the Court's
voice, inventing nothing the digest does not contain.
"""
import re
import sqlite3
from collections import Counter

from helicon.lenses import detect_lens

_LENS_NAME = {
    "frontend": "interfaces", "code": "systems", "config": "infrastructure",
    "social": "writing in public", "slides": "decks", "docs": "documentation",
    "default": "notes",
}


def _top_entities(conn: sqlite3.Connection, limit: int = 14) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT name, entity_type, mention_count FROM entities "
            "WHERE mention_count > 1 ORDER BY mention_count DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"name": r["name"], "type": r["entity_type"], "n": r["mention_count"]} for r in rows]
    except sqlite3.Error:
        return []


def _output_mix(conn: sqlite3.Connection, cap: int = 2500) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT title, source, source_ref, summary FROM helicon_cubes "
        "WHERE merged_into IS NULL AND review_status != 'killed' "
        "ORDER BY created_at DESC LIMIT ?", (cap,)
    ).fetchall()
    c = Counter()
    for r in rows:
        c[detect_lens(r["title"] or "", r["source"] or "", r["source_ref"] or "", r["summary"] or "")] += 1
    return c.most_common()


def _areas(conn: sqlite3.Connection, limit: int = 8) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT source_ref FROM helicon_cubes WHERE merged_into IS NULL "
        "AND source_ref LIKE '%01 Projects/%'"
    ).fetchall()
    c = Counter()
    for r in rows:
        m = re.search(r"01 Projects/([^/]+)/", r["source_ref"] or "")
        if m:
            c[m.group(1)] += 1
    return c.most_common(limit)


def _recent(conn: sqlite3.Connection, limit: int = 8) -> list[str]:
    rows = conn.execute(
        "SELECT title FROM helicon_cubes WHERE merged_into IS NULL "
        "AND source IN ('obsidian','chatgpt','memory') AND title != '' "
        "ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    out, seen = [], set()
    for r in rows:
        t = (r["title"] or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _health(conn: sqlite3.Connection, config: dict) -> dict:
    from helicon.rot import run_rot_exam
    from helicon.score import compute_score
    from helicon.volatility import find_suspects
    score = compute_score(conn)
    rot = run_rot_exam(conn)
    try:
        gold = conn.execute("SELECT COUNT(*) FROM rules WHERE status = 'approved'").fetchone()[0]
    except sqlite3.Error:
        gold = 0
    return {
        "live": score.get("total", 0),
        "reviewed_pct": score.get("score", 0),
        "rot_classes": rot.get("rot_found", 0),
        "rot_total": rot.get("classes", 10),
        "volatile": len(find_suspects(conn)),
        "gold_rules": gold,
    }


def build_digest(conn: sqlite3.Connection, config: dict) -> dict:
    mix = _output_mix(conn)
    total_mix = sum(n for _, n in mix) or 1
    return {
        "entities": _top_entities(conn),
        "output_mix": [{"kind": _LENS_NAME.get(k, k), "pct": round(100 * n / total_mix)}
                       for k, n in mix if n],
        "areas": [{"name": a, "n": n} for a, n in _areas(conn)],
        "recent": _recent(conn),
        "health": _health(conn, config),
        "sources": [r["source"] for r in conn.execute(
            "SELECT DISTINCT source FROM helicon_cubes WHERE merged_into IS NULL").fetchall()],
    }


_SYS = (
    "You are the Court of record for an AI builder's memory, giving them a reading of "
    "who the record shows they are. You are given a DIGEST of their actual stored memory: "
    "recurring people/projects, the mix of work they produce, the areas they invest in, what "
    "they touched recently, and the health of the record. Compose a short, grounded portrait.\n\n"
    "Voice: quiet, precise, a little literary, like an archivist who has read everything and "
    "respects the person. Ground every claim in the digest. Invent nothing. No hype, no "
    "flattery, no buzzwords, and never use an em dash.\n\n"
    "Return JSON: {\n"
    "  opening: one evocative line naming what this record is (<=14 words),\n"
    "  who: 2 sentences on who the record shows they are (from recurring entities + areas),\n"
    "  builder: 2 sentences on the kind of builder they are (from the output mix + areas),\n"
    "  standing: 1 sentence, honest, on how trustworthy the record is right now (from health: "
    "reviewed %, rot classes firing, volatile facts, golden rules),\n"
    "  moves: array of exactly 3 {title (<=6 words), why (1 sentence, cite the digest)}\n"
    "}"
)


def build_portrait(conn: sqlite3.Connection, config: dict, client=None) -> dict:
    import json
    digest = build_digest(conn, config)
    if client is None:
        return {"digest": digest, "keyless": True, "reading": None}
    from helicon.qwen import complete_json
    model = (config.get("qwen_models") or {}).get("plus", "qwen3.6-plus")
    reading = complete_json(
        client, _SYS, "DIGEST:\n" + json.dumps(digest, ensure_ascii=False),
        model=model, operation="portrait")
    return {"digest": digest, "keyless": False, "reading": reading if isinstance(reading, dict) else None}
