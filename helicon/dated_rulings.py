"""Dated rulings on record: the operator's own quoted decisions, read at ask time.

`helicon ask` answered "no ruling covers this topic" for a question whose answer sat in
the operator's ruling log. The ruling engine only knew factual resolutions (topic =
value) made inside Helicon's own audit log. A decision like "Free Lunch is killed" is
recorded elsewhere, as one JSON line with the operator's words, a date and a source.

This module reads that log, read only, and returns the rulings that match a question,
newest first. It never writes, always lists the newest matching ruling first, and returns nothing when the log is absent.

The log path comes from HELICON_RULINGS_FILE. With the variable unset, the shared
fleet log is used when it exists. Set it to an empty string to turn the reader off.
"""

import json
import math
import os
import re

DEFAULT_PATH = os.path.join("~", ".local", "state", "fleet", "rulings.jsonl")

_STOP = frozenset(
    "a an and are as at be been being but by can could did do does for from had has "
    "have how i if in into is it its may me my of on or our should so still than that "
    "the their them then there these they this to up us was we were what when where "
    "which who why will with would you your about again all also any before now only "
    "out over same some such too very yet not no yes".split()
)
_WORD = re.compile(r"[a-z0-9][a-z0-9'\-]{1,}")
MIN_SCORE = 0.34  # share of the question's weighted words a ruling must cover


def rulings_path():
    """The ruling log to read, or None when the reader is off or the file is absent."""
    raw = os.environ.get("HELICON_RULINGS_FILE")
    if raw == "":
        return None
    path = os.path.expanduser(raw or DEFAULT_PATH)
    return path if os.path.isfile(path) else None


def _stem(word):
    """Fold plural and common verb endings so "emails" meets "email"."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _words(text):
    return [_stem(w) for w in _WORD.findall((text or "").lower()) if w not in _STOP]


def load_rulings(path=None):
    """Every well-formed ruling in the log. A broken line is skipped, never guessed."""
    path = path or rulings_path()
    if not path:
        return []
    out = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or not row.get("text"):
                continue
            out.append(
                {
                    "line": number,
                    "date": str(row.get("ts") or "")[:10],
                    "text": str(row["text"]),
                    "quote": str(row.get("quote") or ""),
                    "source": str(row.get("source") or ""),
                    "title": str(row.get("title") or ""),
                }
            )
    return out


def match_rulings(question, rulings=None, limit=3):
    """Rulings that cover the question, best cover first, newest first on a tie.

    Lexical on purpose: each question word is weighted by how rare it is across the
    log, and a ruling scores the share of that weight it contains. It will miss a
    ruling phrased with none of the question's words; that miss is measurable.
    """
    rulings = load_rulings() if rulings is None else rulings
    asked = set(_words(question))
    if not rulings or not asked:
        return []
    bags = [set(_words(f"{r['title']} {r['text']} {r['quote']}")) for r in rulings]
    total = len(rulings)
    weight = {}
    for word in asked:
        seen = sum(1 for bag in bags if word in bag)
        weight[word] = math.log((total + 1) / (seen + 1)) + 1.0 if seen else 0.0
    full = sum(weight.values())
    if not full:
        return []
    scored = []
    for ruling, bag in zip(rulings, bags):
        hit = sorted(w for w in asked if w in bag)
        score = sum(weight[w] for w in hit) / full
        if score >= MIN_SCORE:
            scored.append({**ruling, "score": round(score, 3), "matched": hit})
    scored.sort(key=lambda r: (r["score"], r["date"]), reverse=True)
    best = scored[:limit]
    # Shown newest first: a later decision on the subject replaces an earlier one, and
    # the reader must meet it first. Each older row says so.
    best.sort(key=lambda r: r["date"], reverse=True)
    for position, ruling in enumerate(best):
        ruling["newest"] = position == 0
    return best
