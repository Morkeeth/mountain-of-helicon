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
import re
import sqlite3
from datetime import datetime, timezone

# The rule buckets, declared. `total` and the history point count THESE, so a
# non-rule key added to the gather dict can never silently inflate the law.
SECTIONS = ("canon", "renames", "triage", "precedents", "resolutions",
            "taste", "feedback")

RULE_MAX = 120


def _clip(text: str, limit: int = RULE_MAX) -> str:
    """Clip at a word boundary and mark the cut. A rule chopped mid-word still
    reads as a finished sentence, so the law asserts something the human never
    said — the exact failure this file exists to prevent."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    head = text[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (head or text[:limit - 1].rstrip()) + "…"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def _slug_names(source_ref: str) -> tuple[str, str]:
    """('feedback_no_em_dashes', 'no_em_dashes') from a memory's source_ref."""
    stem = re.sub(r"\.md$", "", os.path.basename(source_ref or ""))
    slug = _norm(re.sub(r"^memory_", "", stem))
    return slug, re.sub(r"^feedback_?", "", slug)


def _first_prose(content: str) -> str:
    """The first real sentence of a memory body. Frontmatter and headings are
    labels; the rule is the prose under them.

    The strip is done by hand rather than by regex because a regex anchored on
    '---\\n...---\\n' misses CRLF bodies, a body whose frontmatter runs to EOF
    with no trailing newline, and a leading blank line. Each of those leaked the
    first frontmatter FIELD through as prose, so `date: 2026-07-01` compiled into
    the law as a standing rule."""
    if not content:
        return ""
    body = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\n")
    if body.startswith("---"):
        end = body.find("\n---", 3)
        body = body[end + 4:] if end != -1 else ""
    lines = [ln.strip() for ln in body.splitlines()]
    prose = [ln for ln in lines
             if ln and not ln.startswith(("#", ">", "|", "---", "```", "*_"))]
    if prose:
        return prose[0].lstrip("-*+ ").strip()
    heads = [ln.lstrip("# ").strip() for ln in lines if ln.startswith("#")]
    return heads[0] if heads else ""


def _feedback_rule(title: str, summary: str, content: str,
                   source_ref: str) -> tuple[str | None, str | None]:
    """(rule, warning) for a standing-feedback memory.

    The title is a LABEL the connector truncates, not a guaranteed rule, and it
    lies in three ways: it can be empty (which compiled a BLANK line into the
    law), it can be a bare filename echo, and splitting it on its first colon
    chops the headline off any title whose colon is punctuation rather than a
    slug separator. So strip only an exact slug echo, fall back to summary then
    content, and refuse to emit an empty rule."""
    slug, body = _slug_names(source_ref)
    t = " ".join((title or "").split())
    if ":" in t:
        head, tail = t.split(":", 1)
        if _norm(head) in (slug, body) and tail.strip():
            t = tail.strip()
    # A title that is only its own FILENAME states no rule (feedback_index
    # compiled to the rule "feedback_index"). But the echo test must be narrow:
    # matching on the normalised form alone deletes real rules, because a terse
    # title legitimately normalises to its own slug ("No hype" ->  no_hype for
    # feedback_no_hype.md), and a non-ASCII title normalises to "" and hit the
    # same branch. A filename echo has no spaces; prose does.
    if not t or (" " not in t and _norm(t) in (slug, body)):
        t = ""
    for text, warn in ((t, None),
                       (" ".join((summary or "").split()),
                        "empty title — compiled from the summary"),
                       (_first_prose(content),
                        "empty title and summary — compiled from the content")):
        if text:
            return _clip(text), warn
    return None, "no title, summary or content — refused to compile a blank rule"


def gather(conn: sqlite3.Connection, config: dict) -> dict:
    g: dict = {k: [] for k in SECTIONS}
    g["_warnings"] = []

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

    taste_raw = []
    for r in conn.execute(
        "SELECT id, audit_type, finding, details, resolved_at, human_decision FROM audit_log "
        "WHERE human_decision IS NOT NULL ORDER BY resolved_at"
    ):
        try:
            d = json.loads(r["details"]) if r["details"] else {}
        except (json.JSONDecodeError, TypeError):
            d = {}
        if r["audit_type"] == "taste":
            taste_raw.append(d)
            continue
        when = (r["resolved_at"] or "")[:10]
        atype, hd = r["audit_type"], r["human_decision"]
        if atype == "identity" and hd.startswith("resolved:"):
            # R11: a forked entity ruled to one canonical definition. The ruling
            # becomes a standing rule the generator obeys — what a store can't do.
            truth = hd.split(":", 1)[1]
            name = (d.get("name") or "?").title()
            # name the LOSING framing (any genus that isn't the canonical one) —
            # genus_b can coincide with the winner, so scan all genera to be sure.
            cg = d.get("canonical_genus")
            losing = next((gen for gen in [d.get("genus_b"), *(d.get("genera") or {})]
                           if gen and gen != cg), "")
            tail = f"; the '{losing}' framing is wrong" if losing else ""
            g["resolutions"].append({
                "rule": f"{name} IS {truth} (ruled canonical){tail} — a competing "
                        f"definition re-alarms if it returns",
                "prov": f"identity ruling on finding #{r['id']}, {when}"})
        elif atype == "provenance" and hd == "resolved:phantom":
            # R12: a relation ruled ungrounded becomes a "do not assert this" rule.
            subj = (d.get("subj") or "?").title()
            obj = (d.get("obj") or "?").title()
            pred = d.get("predicate") or "→"
            g["resolutions"].append({
                "rule": f"{subj} {pred} {obj} is a phantom association (ruled "
                        f"ungrounded) — do not treat it as fact; re-alarms if re-asserted",
                "prov": f"phantom ruling on finding #{r['id']}, {when}"})
        elif atype == "provenance" and hd == "resolved:real":
            pass  # ruled real is a clearance, not a guard — emits no standing rule
        elif hd.startswith("resolved:"):
            truth = hd.split(":", 1)[1]
            subj = f"{d.get('person', '?')} {d.get('topic', '?')}"
            g["resolutions"].append({
                "rule": f"{subj} = {truth}; the competing value(s) "
                        f"{', '.join(v for v in d.get('dates', []) if v != truth)} "
                        f"are ruled wrong and re-alarm if they return",
                "prov": f"ruling on finding #{r['id']}, {when}"})
        elif hd == "dismissed" and d.get("dismiss_reason"):
            g["precedents"].append({
                "rule": "NOT rot: " + _clip(r["finding"], 118),
                "why": _clip(d["dismiss_reason"], 140),
                "prov": f"dismissed finding #{r['id']}, {when}"})

    # taste verdicts -> "avoid this shape" rules the generator obeys
    from collections import Counter as _C
    _kills, _sends = _C(), _C()
    _KILL = {"kill", "killed", "reject", "rejected"}
    _SEND = {"send", "sent", "approve", "approved", "exceptional"}
    for d in taste_raw:
        move = d.get("move", "")
        if not move:
            continue
        key = (d.get("kind", ""), move)
        v = d.get("human_verdict", "")
        if v in _KILL:
            _kills[key] += 1
        elif v in _SEND:
            _sends[key] += 1
    for key, n in _kills.items():
        if n >= 2 and n > _sends[key]:
            kind, move = key
            g["taste"].append({
                "rule": f"avoid the '{move}' move" + (f" for {kind}" if kind else "")
                        + f" — ruled kill {n}x (sent {_sends[key]}x)",
                "prov": "taste verdicts remembered from Taste Machine"})

    for r in conn.execute(
        "SELECT title, summary, content, source_ref FROM helicon_cubes "
        "WHERE source_ref LIKE '%feedback_%' AND merged_into IS NULL "
        "AND review_status IN ('pending', 'approved', 'revised') "
        "AND source = 'claude-code' ORDER BY source_ref"
    ):
        name = os.path.basename(r["source_ref"]).replace("memory_", "")
        rule, warn = _feedback_rule(r["title"], r["summary"], r["content"],
                                    r["source_ref"])
        if warn:
            g["_warnings"].append(f"{name}: {warn}")
        if rule is None:
            continue
        g["feedback"].append({"rule": rule, "prov": name})

    # feedback files appear once per scan-shape; dedupe by provenance
    seen = set()
    g["feedback"] = [f for f in g["feedback"]
                     if not (f["prov"] in seen or seen.add(f["prov"]))]
    return g


def compile_gold(conn: sqlite3.Connection, config: dict) -> str:
    return _compile_from(gather(conn, config))


def _compile_from(g: dict) -> str:
    total = sum(len(g.get(k, [])) for k in SECTIONS)
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
    section("Taste — output shapes to avoid", g["taste"],
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
             **{k: len(g.get(k, [])) for k in SECTIONS},
             "total": sum(len(g.get(k, [])) for k in SECTIONS)}
    hist = gold_history(config, limit=1)
    counts_changed = not hist or any(
        hist[-1].get(k) != point[k] for k in point if k != "ts")
    if counts_changed:
        with open(_history_path(config), "a", encoding="utf-8") as f:
            f.write(json.dumps(point) + "\n")
    return {"path": out, "chars": len(md), "md": md,
            "warnings": g["_warnings"], **point}


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
