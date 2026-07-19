"""Live guard: the agent consults the law BEFORE it writes.

Rulings compile into GOLDEN_RULES, but until now the agent was trusted to obey a
pasted file. This checks a proposed output against the law at write time and
returns violations, so a ruled-against claim is caught before it lands, not
audited after. The "ultimate solution": rulings-become-law made enforceable, not
advisory. Exposed as the helicon_guard MCP tool so any agent can call it.

Checks the highest-signal, deterministic classes, each tracing to a real ruling:
  - dead names (renames): asserting a renamed project's old name as current.
  - ruled identity: asserting a definition a human ruled against.
  - ruled facts: asserting a value a human ruled WRONG for a topic (never-twice
    at write time — the same guard find_conflicts enforces at audit time, now
    also enforced BEFORE the agent writes).
Nothing is invented.
"""
import json
import re

# A date token: YYYY-MM-DD or a bare MM-DD (the granularity the wedding-range
# rulings are stored at). Used to test a partial date against a ruled range.
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}-\d{2}\b")


def _parse_partial_date(s: str):
    """Return a comparable (month, day) tuple from 'YYYY-MM-DD' or 'MM-DD', else
    None. Year is dropped: the ruled ranges are within a single year, and the
    asserted partials carry no year, so month/day is the common granularity."""
    m = re.fullmatch(r"(?:\d{4}-)?(\d{2})-(\d{2})", s.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def _date_in_range(candidate: str, start: str, end: str) -> bool:
    """True if candidate falls within [start, end] inclusive, comparing on
    month/day. All three must parse as partial dates, or it is not a range hit."""
    c, s, e = (_parse_partial_date(x) for x in (candidate, start, end))
    return bool(c and s and e and s <= c <= e)


def guard_output(conn, text: str) -> dict:
    """Check proposed agent output against the compiled law. Returns violations
    (each with the rule, severity, and its provenance) and a clean flag."""
    from helicon.aliases import list_aliases
    from helicon.identity import extract_glosses, _load_identity_resolutions

    violations = []
    low = (text or "").lower()

    # 1. dead names: a renamed project's OLD name asserted (write-time = current claim)
    for a in list_aliases(conn):
        old, new = a["old_name"], a["new_name"]
        if old and re.search(rf"\b{re.escape(old.lower())}\b", low):
            violations.append({
                "rule": "rename", "severity": "warning", "subject": old,
                "message": f"'{old}' is a dead name (renamed to '{new}' "
                           f"{(a.get('renamed_at') or '')[:10]}); use '{new}'.",
                "provenance": a.get("note") or f"alias {old} -> {new}",
            })

    # 2. ruled identity: proposed text asserts a genus a human ruled against
    res = _load_identity_resolutions(conn)
    for g in extract_glosses(text or ""):
        name, genus = g["name"].lower(), g["genus"]
        r = res.get(name)
        if r and genus != r["genus"]:
            violations.append({
                "rule": "identity-ruling", "severity": "critical", "subject": g["name"],
                "message": f"'{g['name']}' was ruled '{r['genus']}', but this asserts "
                           f"'{genus}' — ruled against.",
                "provenance": f"ruling on '{name}' at {(r.get('resolved_at') or '')[:19]}",
            })

    # 3. ruled facts: proposed text asserts a value a human ruled WRONG for a topic
    #    (e.g. "4 hackathon wins" after wins was ruled 9). This is the never-twice
    #    guard that find_conflicts applies at AUDIT time, brought forward to WRITE
    #    time so the wrong value is caught before it lands.
    for r in _load_factual_resolutions(conn):
        te = re.escape(r["topic"].lower())
        fired = None
        for wrong in r["wrong_values"]:
            we = re.escape(wrong.lower())
            # A number quantifies the noun that FOLLOWS it ("4 hackathon wins"):
            # value, then up to 3 words (the subject), then the topic. Adjacency is
            # the precision gate — it fires on "4 ... wins" but NOT on the canonical
            # line "9 hackathon wins, 4 finalist placements", where the 4 quantifies
            # "finalist" and never reaches "wins".
            quant = re.search(rf"\b{we}\b(?:\W+[\w$%.+/-]+){{0,3}}\W+\b{te}\b", low)
            # An explicit assignment sets the topic to the value ("wins: 4", "wins=4").
            assign = re.search(rf"\b{te}\b\s*[:=]\s*{we}\b", low)
            # For a DISTINCTIVE value (a word, a date, a range — not a bare 1-2 digit
            # number that collides by chance), also catch "topic <value>" in either
            # order within a couple of words ("birthday 07-13"). Gated on
            # distinctiveness so it can't reopen the finalist-placements trap.
            distinctive = (bool(re.search(r"[a-z]", wrong.lower()))
                           or "-" in wrong or ".." in wrong
                           or len(re.sub(r"\D", "", wrong)) >= 3)
            loose = distinctive and re.search(
                rf"\b{te}\b(?:\W+[\w$%.+/-]+){{0,2}}\W+\b{we}\b", low)
            if quant or assign or loose:
                fired = wrong
                break
        # A ruled-wrong value can be a DATE RANGE ("08-14..08-22"). A partial date
        # ("08-14") is not a substring of the range string, so the checks above miss
        # it and the guard returns CLEAN on a date the human explicitly ruled wrong.
        # Match a partial date against the range: any date token asserted near the
        # topic that falls inside a ruled-wrong range fires, so every ruling binds.
        if fired is None:
            for wrong in r["wrong_values"]:
                if ".." not in wrong:
                    continue
                start, _, end = wrong.partition("..")
                for cand in _DATE_RE.findall(low):
                    ce = re.escape(cand)
                    near = (re.search(rf"\b{te}\b(?:\W+[\w$%.+/-]+){{0,3}}\W+{ce}\b", low)
                            or re.search(rf"{ce}\b(?:\W+[\w$%.+/-]+){{0,3}}\W+\b{te}\b", low))
                    if near and _date_in_range(cand, start.strip(), end.strip()):
                        fired = f"{cand} (inside ruled-wrong range {wrong})"
                        break
                if fired is not None:
                    break
        if fired is not None:
            subj = f"'{r['subject']}' " if r["subject"] else ""
            subj_for = f"for '{r['subject']}' " if r["subject"] else ""
            violations.append({
                "rule": "ruled-fact", "severity": "critical",
                "subject": "/".join(p for p in (r["subject"], r["topic"]) if p),
                "message": f"{r['topic']} {subj_for}was ruled '{r['true_value']}', "
                           f"but this asserts '{fired}' — ruled wrong "
                           f"(re-alarms if it returns).",
                "provenance": f"ruling #{r['audit_id']} on {subj}{r['topic']} "
                              f"at {(r.get('resolved_at') or '')[:19]}",
            })

    return {"text": (text or "")[:200], "violations": violations,
            "clean": not violations,
            "verdict": "blocked" if any(v["severity"] == "critical" for v in violations)
                       else ("warn" if violations else "clean")}


def _load_factual_resolutions(conn) -> list[dict]:
    """Human-settled topic/subject rulings: each returns the ruled-true value and the
    competing values ruled WRONG. Mirrors identity._load_identity_resolutions but for
    factual (claim/pairing) findings resolved as 'resolved:<value>'. The wrong values
    are every asserted value other than the truth, so a memory re-asserting one is
    caught at write time."""
    from helicon.timeutil import ts_norm
    out = []
    for row in conn.execute(
        "SELECT id, details, human_decision, resolved_at FROM audit_log "
        "WHERE audit_type = 'factual' AND human_decision LIKE 'resolved:%'"
    ):
        try:
            d = json.loads(row["details"])
        except (json.JSONDecodeError, TypeError):
            continue
        topic = (d.get("topic") or "").strip()
        if not topic:
            continue                       # no topic noun to anchor on — skip safely
        true_value = row["human_decision"].split("resolved:", 1)[1].strip()
        candidates = set()
        for key in ("all_dates", "dates"):
            for v in (d.get(key) or []):
                if v:
                    candidates.add(str(v).strip())
        for key in ("value_a", "value_b"):
            if d.get(key):
                candidates.add(str(d[key]).strip())
        wrong = [v for v in candidates if v and v != true_value]
        if not wrong:
            continue
        out.append({
            "topic": topic,
            "subject": (d.get("person") or "").strip(),
            "true_value": true_value,
            "wrong_values": wrong,
            "resolved_at": ts_norm(row["resolved_at"]) or (row["resolved_at"] or ""),
            "audit_id": row["id"],
        })
    return out


def format_guard(res: dict) -> str:
    if res["clean"]:
        return "\n  ✓ clean — no ruling contradicts this output.\n"
    out = ["", f"  {res['verdict'].upper()} — {len(res['violations'])} ruling(s) contradict this output:", ""]
    for v in res["violations"]:
        out.append(f"    [{v['severity']}] {v['message']}")
        out.append(f"        ↳ {v['provenance']}")
    out.append("")
    return "\n".join(out)
