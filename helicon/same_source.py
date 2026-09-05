"""R1b — same-source rule contradiction inside one instruction file.

ROADMAP Camp II: R1 skips pairs from the same file ("one file arguing with
itself is not cross-source"). That is correct for R1 and wrong for the
stranger question "does this CLAUDE.md contradict itself?". Planted
"Always use v1" / "Always use v2" on 2026-08-14 returned CLEAN on the
published wheel. This module is the named class — not folded into R1.

Precision over recall. Only imperative use-rules with a bindable subject:
  Always/Must/Only use X … <subject>
  Never / Don't / Do not use X … <subject>
Two positive use-rules with the same subject and different objects → conflict.
A never/don't-use and an always-use of the same object+subject → conflict.
`Prefer` is intentionally unmeasured (scoped exceptions are common; open question).

No LLM. No DB. Keyless. Wired into helicon.review as the `rules` tier
(JSON key `rules`; implementation lives here so helicon/rules.py — the
prompted-triage compiler — stays untouched).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from helicon.pointers import DEFAULT_INSTRUCTION_FILES

# "Always use v1 of the API." · "Must use npm for installs." · "Never use yarn."
# "Don't use yarn for installs." · "Do not use yarn for installs."
# Object is ONE token (or a backtick span) — never swallow "of the …".
# Prefer stays out: too often scoped ("prefer X; prefer Y for Z").
_USE_RULE = re.compile(
    r"\b(?P<mod>always|must|only|never|don'?t|do\s+not)\s+use\s+"
    r"(?P<obj>`[^`]+`|v?\d+(?:\.\d+)*|[A-Za-z][\w./+-]*)"
    r"(?P<rest>[^.\n]*)",
    re.IGNORECASE,
)

# Subject binders after the object — "of the API", "for installs", "when testing"
_SUBJECT = re.compile(
    r"\b(?:of|for|when|on|in|with)\s+(?:the\s+)?(?P<sub>[\w][\w./+ -]{1,40})",
    re.IGNORECASE,
)

_STOP = {
    "a", "an", "the", "this", "that", "our", "your", "its", "their", "all",
    "any", "each", "new", "old", "same", "both", "either",
}


@dataclass
class RuleClaim:
    modality: str          # always|must|only|never  (don't/do not → never)
    obj: str               # normalized object
    subject: str           # normalized subject key (may be "")
    line_no: int
    line: str
    raw_obj: str


def _norm_obj(raw: str) -> str:
    t = raw.strip().strip("`").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _norm_modality(raw: str) -> str:
    """Collapse don't / do not onto never so conflict kinds stay stable."""
    m = re.sub(r"\s+", " ", (raw or "").strip().lower())
    m = m.replace("'", "")
    if m in ("dont", "do not"):
        return "never"
    return m


def _norm_subject(rest: str) -> str:
    m = _SUBJECT.search(rest or "")
    if not m:
        return ""
    words = [w.lower() for w in re.findall(r"[\w.+-]+", m.group("sub"))]
    words = [w for w in words if w not in _STOP]
    return " ".join(words[:4])


def extract_use_rules(text: str) -> list[RuleClaim]:
    out: list[RuleClaim] = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in _USE_RULE.finditer(line):
            mod = _norm_modality(m.group("mod"))
            raw_obj = m.group("obj")
            obj = _norm_obj(raw_obj)
            if not obj or len(obj) > 60:
                continue
            sub = _norm_subject(m.group("rest") or "")
            out.append(RuleClaim(mod, obj, sub, i, line.strip()[:160], raw_obj.strip()))
    return out


def _positive(mod: str) -> bool:
    return mod in ("always", "must", "only")


def find_conflicts(claims: list[RuleClaim]) -> list[dict]:
    """Return conflict receipts for claims from one file."""
    conflicts: list[dict] = []
    for i, a in enumerate(claims):
        for b in claims[i + 1:]:
            if a.line_no == b.line_no:
                continue
            # Same subject required when either names one; if both empty, bind by
            # object stem family (v1/v2, python3.11/python3.12).
            if a.subject or b.subject:
                if a.subject != b.subject:
                    continue
            else:
                if not _same_family(a.obj, b.obj):
                    continue
            # never X vs always/must/only X
            if {_positive(a.modality), _positive(b.modality)} == {True, False}:
                if a.obj == b.obj:
                    conflicts.append(_receipt(a, b, "never-vs-always"))
                continue
            # two positives, different objects, same subject (or same family)
            if _positive(a.modality) and _positive(b.modality) and a.obj != b.obj:
                conflicts.append(_receipt(a, b, "competing-always-use"))
    return conflicts


def _same_family(a: str, b: str) -> bool:
    """v1/v2, python3.11/python3.12, react18/react19 — cheap stem equality."""
    def stem(x: str) -> str:
        x = x.lower().strip()
        s = re.sub(r"[\d.]+$", "", x)
        return s if s else x
    sa, sb = stem(a), stem(b)
    if sa and sb and sa == sb and a != b:
        return True
    if re.fullmatch(r"v?\d+(?:\.\d+)*", a) and re.fullmatch(r"v?\d+(?:\.\d+)*", b):
        return True
    return False


def _receipt(a: RuleClaim, b: RuleClaim, kind: str) -> dict:
    return {
        "kind": kind,
        "raw": f"{a.raw_obj} vs {b.raw_obj}",
        "line_no": a.line_no,
        "line": a.line,
        "other_line_no": b.line_no,
        "other_line": b.line,
        "subject": a.subject or b.subject or "(version/family)",
        "receipt": (
            f"L{a.line_no} `{a.modality} use {a.obj}` conflicts with "
            f"L{b.line_no} `{b.modality} use {b.obj}`"
            + (f" on subject '{a.subject or b.subject}'" if (a.subject or b.subject) else "")
        ),
    }


def check_same_source_rules(repo_root: str, files: list[str] | None = None) -> dict:
    """Grade same-file use-rule contradictions in instruction files."""
    targets = [f for f in (files or DEFAULT_INSTRUCTION_FILES)
               if os.path.exists(os.path.join(repo_root, f))]
    checked = 0
    receipts: list[dict] = []
    read_files: list[str] = []
    for rel in targets:
        try:
            text = open(os.path.join(repo_root, rel), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        read_files.append(rel)
        claims = extract_use_rules(text)
        checked += len(claims)
        for c in find_conflicts(claims):
            c = dict(c)
            c["file"] = rel
            c["receipt"] = f"{rel}:{c['line_no']}/{c['other_line_no']} — {c['receipt']}"
            receipts.append(c)

    if not read_files:
        verdict = "UNMEASURED"
    elif checked == 0:
        verdict = "UNMEASURED"
    else:
        verdict = "ROT FOUND" if receipts else "CLEAN"

    return {
        "rid": "R1b",
        "name": "Same-source rule contradiction",
        "verdict": verdict,
        "checked": checked,
        "broken": len(receipts),
        "files": read_files,
        "receipts": receipts,
    }


# Alias used by review.py JSON key `rules` (not helicon.rules).
check_rules = check_same_source_rules


def format_same_source_rules(res: dict) -> str:
    head = f"[{res['rid']}] {res['name']}: {res['verdict']}"
    if res["verdict"] == "UNMEASURED":
        return head + "  (no imperative use-rules to compare)"
    head += f"  ({res['checked']} checked, {res['broken']} broken)"
    return "\n".join([head] + [f"  ✗ {r['receipt']}" for r in res["receipts"]])
