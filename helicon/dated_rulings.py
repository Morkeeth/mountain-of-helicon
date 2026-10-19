"""Dated rulings on record: the operator's own quoted decisions, read at ask time.

`helicon ask` answered "no ruling covers this topic" for a question whose answer sat in
the operator's ruling log. The ruling engine only knew factual resolutions (topic =
value) made inside Helicon's own audit log. A decision like "Free Lunch is killed" is
recorded elsewhere, as one JSON line with the operator's words, a date and a source.

This module reads that log, read only, and returns the rulings that match a question,
current one first. It never writes and returns nothing when the log is absent.

A row marked `"private": true` is dropped at load. Private rows hold matters the
operator keeps off every agent surface, so the MCP server can never read them. The
one opt-in is the keyword `include_private`, which only the operator's own terminal
command (`helicon ask --include-private`) passes.

A private row can still be the newest decision on a subject. Dropping it would leave
an older public ruling standing as current, which is a wrong answer shown as the
latest word. So the matcher weighs the private rows too, shows none of them, and
when one is newer on the same subject it marks the public rulings
`possibly_superseded` with `newer_hidden`. Nothing else about the private row
leaves: no text, title, quote, source, date or count.

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
SAME_SUBJECT = 0.75  # a ruling this close to the best cover is about the same subject
BODY_SHARE = 0.5  # a question word found only after the lead counts this much of a word in the lead
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


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


def load_rulings(path=None, include_private=False):
    """Every well-formed ruling in the log that is not private.

    A broken line is skipped, never guessed. A row with `"private": true` is dropped
    unless `include_private` is set; no agent-facing caller sets it.
    """
    return _load(path, private=None if include_private else False)


def load_hidden(path=None):
    """The private rows only. For the matcher's newer-exists check, never for output."""
    return _load(path, private=True)


def _load(path, private):
    """Rows of the log. `private` False keeps public rows, True private ones, None all."""
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
            if private is not None and bool(row.get("private")) is not private:
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


def _bags(ruling):
    """(lead words, all words) of a ruling.

    The lead is the title and the first sentence of the text: where a ruling says what
    it decides. A word that only comes later, or only in the quote, is a mention.
    """
    first = _SENTENCE_END.split(ruling["text"].strip(), maxsplit=1)[0]
    lead = set(_words(f"{ruling['title']} {first}"))
    return lead, lead | set(_words(f"{ruling['text']} {ruling['quote']}"))


def _named(question):
    """Words the asker wrote with a capital inside the sentence: the named things."""
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]+", question or "")
    return {_stem(t.lower()) for t in tokens[1:] if t[0].isupper() and t.lower() not in _STOP}


def match_rulings(question, rulings=None, limit=3, include_private=False, hidden=None):
    """Rulings that cover the question, with the current one marked.

    Lexical on purpose: each question word is weighted by how rare it is across the
    log, a named thing counts double, and a ruling scores the share of that weight it
    contains. It will miss a ruling phrased with none of the question's words; that
    miss is measurable.

    Topic before recency: a word in the ruling's lead (title and first sentence) counts
    in full, a word found only later counts BODY_SHARE. Without this a later ruling
    that only mentions the same names scored like the ruling that decides the matter,
    and being newer it took the label current. Every such row that the log gained
    cost a right answer: 15 of 20 at 272 rows fell to 11 at 1,221.

    Which ruling is current: only rulings that cover the question about as well as
    the best one (SAME_SUBJECT of its score) are treated as the same subject. The
    newest of those is current, and every ruling of that same day with it. A weaker
    match is listed after them as related, whatever its date, so a later ruling about
    something else cannot pass for the latest word on this subject.

    `hidden` holds the private rows the caller may not read. They are weighed with the
    public word weights, so they change no public score, and none is returned. When
    one is on the same subject and newer than the current public ruling, the public
    rulings on that subject get the standing `possibly_superseded` and `newer_hidden`.
    Read from the log, `hidden` is filled here unless the caller may read private rows.
    """
    if rulings is None:
        rulings = load_rulings(include_private=include_private)
        if hidden is None and not include_private:
            hidden = load_hidden()
    asked = set(_words(question))
    if not rulings or not asked:
        return []
    named = _named(question)
    bags = [_bags(r) for r in rulings]
    total = len(rulings)
    weight = {}
    for word in asked:
        seen = sum(1 for _, bag in bags if word in bag)
        base = math.log((total + 1) / (seen + 1)) + 1.0 if seen else 0.0
        weight[word] = base * (2.0 if word in named else 1.0)
    full = sum(weight.values())
    if not full:
        return []

    def cover(lead, bag):
        return sum(weight[w] * (1.0 if w in lead else BODY_SHARE) for w in asked if w in bag) / full

    scored = []
    for ruling, (lead, bag) in zip(rulings, bags):
        hit = sorted(w for w in asked if w in bag)
        score = cover(lead, bag)
        if score >= MIN_SCORE:
            scored.append({**ruling, "score": round(score, 3), "matched": hit})
    if not scored:
        return []
    scored.sort(key=lambda r: (r["score"], r["date"]), reverse=True)
    floor = scored[0]["score"] * SAME_SUBJECT
    same = sorted((r for r in scored if r["score"] >= floor), key=lambda r: r["date"], reverse=True)
    related = [r for r in scored if r["score"] < floor]
    newest_day = same[0]["date"]
    newer_hidden = False
    for row in hidden or ():
        if row["date"] > newest_day:
            if cover(*_bags(row)) >= floor:
                newer_hidden = True
                break
    out = []
    for ruling in same + related:
        on_subject = ruling["score"] >= floor
        ruling["standing"] = (
            "related" if not on_subject
            else "possibly_superseded" if newer_hidden
            else "current" if ruling["date"] == newest_day
            else "older"
        )
        ruling["newest"] = ruling["standing"] == "current"
        if newer_hidden and on_subject:
            ruling["newer_hidden"] = True
        out.append(ruling)
    return out[:limit]


HIDDEN_NOTICE = (
    "A newer ruling on this subject exists that this caller cannot read. "
    "No ruling shown here is confirmed current. Ask the operator before acting on one."
)


def hidden_notice(matched):
    """The sentence an answer carries when a shown ruling may be superseded, else ''."""
    return HIDDEN_NOTICE if any(r.get("newer_hidden") for r in matched or ()) else ""
