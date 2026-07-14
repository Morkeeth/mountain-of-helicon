"""Live guard: the agent consults the law BEFORE it writes.

Rulings compile into GOLDEN_RULES, but until now the agent was trusted to obey a
pasted file. This checks a proposed output against the law at write time and
returns violations, so a ruled-against claim is caught before it lands, not
audited after. The "ultimate solution": rulings-become-law made enforceable, not
advisory. Exposed as the helicon_guard MCP tool so any agent can call it.

v1 checks the two highest-signal, deterministic classes:
  - dead names (renames): asserting a renamed project's old name as current.
  - ruled identity: asserting a definition a human ruled against.
Both trace to a real ruling; nothing is invented.
"""
import re


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

    return {"text": (text or "")[:200], "violations": violations,
            "clean": not violations,
            "verdict": "blocked" if any(v["severity"] == "critical" for v in violations)
                       else ("warn" if violations else "clean")}


def format_guard(res: dict) -> str:
    if res["clean"]:
        return "\n  ✓ clean — no ruling contradicts this output.\n"
    out = ["", f"  {res['verdict'].upper()} — {len(res['violations'])} ruling(s) contradict this output:", ""]
    for v in res["violations"]:
        out.append(f"    [{v['severity']}] {v['message']}")
        out.append(f"        ↳ {v['provenance']}")
    out.append("")
    return "\n".join(out)
