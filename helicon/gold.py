"""GOLDEN RULES — the stack's law, compiled from human judgment.

Every surface of Mount Helicon produces decisions with provenance: rulings
on findings, dismissal precedents, approved triage rules, declared renames,
canonical sources, and the operator's standing feedback memories. Scattered,
they are history. Compiled, they are an OPINIONATED, EVOLVING rulebook for
the whole agent stack — the thing a new session should obey and the thing
this tool grows every time you rule.

`helicon gold` compiles GOLDEN_RULES.md into data/ (always safe).
`helicon gold --inject` writes it to ~/.claude/GOLDEN_RULES.md with a .bak,
and tells you the one @import line to add to CLAUDE.md. Never automatic.

Every compile appends a point to data/gold-history.jsonl — the rulebook's
own growth curve, rendered on the dashboard's GOLD surface.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone


def gather(conn: sqlite3.Connection, config: dict) -> dict:
    g: dict = {"canon": [], "renames": [], "triage": [], "precedents": [],
               "resolutions": [], "feedback": []}

    for metric, path in (config.get("claims", {}).get("canonical", {}) or {}).items():
        g["canon"].append({"rule": f"`{metric}` lives in {path}; every other "
                                   f"assertion is drift, direction pre-decided",
                           "prov": "canonical source, config.json"})

    for r in conn.execute("SELECT * FROM entity_aliases ORDER BY renamed_at"):
        g["renames"].append({
            "rule": f"{r['old_name']} -> {r['new_name']} "
                    f"(renamed {r['renamed_at'][:10]}); the old name in a "
                    f"current claim is rot, in history it is history",
            "prov": f"alias #{r['id']}" + (f", {r['note']}" if r["note"] else "")})

    for r in conn.execute("SELECT * FROM rules WHERE status = 'approved' "
                          "ORDER BY approved_at"):
        g["triage"].append({"rule": r["nl_text"],
                            "prov": f"rule #{r['id']}, approved "
                                    f"{(r['approved_at'] or '')[:10]}, "
                                    f"trust {r['trust']:.2f}"})

    for r in conn.execute(
        "SELECT id, finding, details, resolved_at, human_decision FROM audit_log "
        "WHERE human_decision IS NOT NULL ORDER BY resolved_at"
    ):
        try:
            d = json.loads(r["details"]) if r["details"] else {}
        except (json.JSONDecodeError, TypeError):
            d = {}
        when = (r["resolved_at"] or "")[:10]
        if r["human_decision"].startswith("resolved:"):
            truth = r["human_decision"].split(":", 1)[1]
            subj = f"{d.get('person', '?')} {d.get('topic', '?')}"
            g["resolutions"].append({
                "rule": f"{subj} = {truth}; the competing value(s) "
                        f"{', '.join(v for v in d.get('dates', []) if v != truth)} "
                        f"are ruled wrong and re-alarm if they return",
                "prov": f"ruling on finding #{r['id']}, {when}"})
        elif r["human_decision"] == "dismissed" and d.get("dismiss_reason"):
            g["precedents"].append({
                "rule": "NOT rot: " + (r["finding"][:118].rsplit(" ", 1)[0] if len(r["finding"]) > 118 else r["finding"]),
                "why": d["dismiss_reason"][:140],
                "prov": f"dismissed finding #{r['id']}, {when}"})

    for r in conn.execute(
        "SELECT title, source_ref FROM helicon_cubes "
        "WHERE source_ref LIKE '%feedback_%' AND merged_into IS NULL "
        "AND review_status IN ('pending', 'approved', 'revised') "
        "AND source = 'claude-code' ORDER BY source_ref"
    ):
        name = os.path.basename(r["source_ref"]).replace("memory_", "")
        title = r["title"].split(":", 1)[-1].strip()
        g["feedback"].append({"rule": title[:120], "prov": name})

    # feedback files appear once per scan-shape; dedupe by provenance
    seen = set()
    g["feedback"] = [f for f in g["feedback"]
                     if not (f["prov"] in seen or seen.add(f["prov"]))]
    return g


def compile_gold(conn: sqlite3.Connection, config: dict) -> str:
    return _compile_from(gather(conn, config))


def _compile_from(g: dict) -> str:
    total = sum(len(v) for v in g.values())
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()[:16].replace("T", " ")
    L = [
        "# GOLDEN RULES",
        "",
        f"_The opinionated law of this agent stack: {total} rules, every one "
        f"born from a human decision or a declared fact. Compiled {now} UTC "
        f"by Mount Helicon. Regenerate: `helicon gold` · "
        f"Inject: `helicon gold --inject`._",
        "",
    ]

    def section(title, items, fmt):
        if not items:
            return
        L.append(f"## {title}")
        for it in items:
            L.append(fmt(it))
        L.append("")

    section("Single sources of truth", g["canon"],
            lambda it: f"- {it['rule']}  \n  _[{it['prov']}]_")
    section("Renames — dead names are history, never current", g["renames"],
            lambda it: f"- {it['rule']}  \n  _[{it['prov']}]_")
    section("Rulings — facts decided, guarded against recurrence", g["resolutions"],
            lambda it: f"- {it['rule']}  \n  _[{it['prov']}]_")
    section("Triage law — approved, previewed against history", g["triage"],
            lambda it: f"- {it['rule']}  \n  _[{it['prov']}]_")
    section("Precedents — what is NOT rot here", g["precedents"],
            lambda it: f"- {it['rule']}  \n  _why: {it['why']}_  \n  _[{it['prov']}]_")
    section("Standing feedback — the operator's law", g["feedback"],
            lambda it: f"- {it['rule']}  \n  _[{it['prov']}]_")

    L.append("---")
    L.append("_A rule without provenance is a vibe. Everything above has a "
             "receipt in the store._")
    return "\n".join(L)


def _history_path(config: dict) -> str:
    return os.path.join(os.path.dirname(config["db_path"]), "gold-history.jsonl")


def write_gold(conn: sqlite3.Connection, config: dict) -> dict:
    """ONE gather per run: the written file, the history point and the
    returned counts must describe the same compile. History appends only
    when counts CHANGE — the growth curve records growth, not invocations."""
    g = gather(conn, config)
    md = _compile_from(g)
    out = os.path.join(os.path.dirname(config["db_path"]), "GOLDEN_RULES.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    point = {"ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
             **{k: len(v) for k, v in g.items()},
             "total": sum(len(v) for v in g.values())}
    hist = gold_history(config, limit=1)
    counts_changed = not hist or any(
        hist[-1].get(k) != point[k] for k in point if k != "ts")
    if counts_changed:
        with open(_history_path(config), "a", encoding="utf-8") as f:
            f.write(json.dumps(point) + "\n")
    return {"path": out, "chars": len(md), "md": md, **point}


def gold_history(config: dict, limit: int = 60) -> list[dict]:
    try:
        with open(_history_path(config), encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        return [json.loads(l) for l in lines if l.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def inject(conn: sqlite3.Connection, config: dict, apply: bool = False,
           md: str | None = None) -> dict:
    """Write GOLDEN_RULES.md to ~/.claude/ so every session can obey it.
    Dry-run by default; --inject writes with a .bak of any previous version.
    The CLAUDE.md import line is printed, never auto-appended — standing
    context is the operator's budget to spend."""
    md = md if md is not None else compile_gold(conn, config)
    target = os.path.join(os.path.expanduser("~"), ".claude", "GOLDEN_RULES.md")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not apply:
        return {"applied": False, "target": target, "chars": len(md),
                "hint": "run with --inject to write; then add "
                        "'@GOLDEN_RULES.md' to ~/.claude/CLAUDE.md"}
    baked = False
    if os.path.exists(target):
        with open(target, encoding="utf-8") as f:
            old = f.read()
        with open(target + ".bak", "w", encoding="utf-8") as f:
            f.write(old)
        baked = True
    with open(target, "w", encoding="utf-8") as f:
        f.write(md)
    return {"applied": True, "target": target, "chars": len(md), "bak": baked,
            "hint": "add '@GOLDEN_RULES.md' to ~/.claude/CLAUDE.md if not present"}
