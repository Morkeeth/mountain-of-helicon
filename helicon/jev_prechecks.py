"""Transport-free pair rules extracted from jev-cascade f504a8d.

These narrow rules describe one relation. A matching relation is never a
whole-pair factual verdict. Unsupported language defers. No model/config/store.
Original experimental coverage and limits: Jev HELICON-CASCADE report.
"""
from __future__ import annotations
import datetime as dt
import re
from typing import Callable

MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
_MON = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
_MON_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

STOP = set("""a an the and or of for in on at to by with from as is are was were be been
being it its this that these those there here has have had do does did not no so
than then into onto over under about after before again all any each every few more
most other some such only own same too very can will just should now our your their
his her we you they he she i me my us them which who whom what when where why how
up down out off per also still any one""".split())

HEDGE_WORDS = {"about", "around", "roughly", "approximately", "approx", "nearly", "almost",
               "circa", "some"}
APPROX = re.compile(r"\b(about|around|roughly|approximately|approx|nearly|almost|circa|some)\b|~")
BOUND = re.compile(r"\b(more than|less than|fewer than|at least|at most|over|under|up to|"
                   r"above|below|upwards of|exceeds?|beyond|or more|or less|plus)\b|\+|<|>")


def _norm(s: str) -> str:
    return (s.replace("’", "'").replace(" ", " ").replace(" ", " "))


def _stem(w: str) -> str:
    w = w.lower().strip("'")
    if w.endswith("'s"):
        w = w[:-2]
    for suf in ("ies",):
        if w.endswith(suf) and len(w) > 4:
            return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    return w


def _words(s: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", s)
            if w.lower() not in STOP and len(w) > 1}


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    # 2026-10-02
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    # 2 October 2026, 2 Oct 2026, 2nd October 2026
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MON_RE + r",?\s+(\d{4})\b", re.I), "dmy"),
    # October 2, 2026 / Oct 2 2026
    (re.compile(r"\b" + _MON_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I), "mdy"),
]
# day and month with no year: a dated mention whose weekday is unknowable
_PARTIAL_DATE = [
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MON_RE + r"(?!\w)", re.I),
    re.compile(r"\b" + _MON_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!\s*,?\s*\d{4})", re.I),
]
_SLASH_DATE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")


def find_dates(s: str) -> list[tuple[dt.date, tuple[int, int]]]:
    """Full dates with a year. Returns (date, span) for every mention."""
    out = []
    for rx, kind in _DATE_PATTERNS:
        for m in rx.finditer(s):
            try:
                if kind == "iso":
                    d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif kind == "dmy":
                    d = dt.date(int(m.group(3)), _MON[m.group(2).lower()[:3]], int(m.group(1)))
                else:
                    d = dt.date(int(m.group(3)), _MON[m.group(1).lower()[:3]], int(m.group(2)))
            except (ValueError, KeyError):
                continue
            out.append((d, m.span()))
    return out


def _strip_dates(s: str) -> str:
    for rx, _ in _DATE_PATTERNS:
        s = rx.sub(" DATE ", s)
    for rx in _PARTIAL_DATE:
        s = rx.sub(" DATE ", s)
    s = _SLASH_DATE.sub(" DATE ", s)
    return s


def _partial_dates(s: str) -> int:
    s2 = s
    for rx, _ in _DATE_PATTERNS:
        s2 = rx.sub(" ", s2)
    n = sum(len(rx.findall(s2)) for rx in _PARTIAL_DATE)
    return n + len(_SLASH_DATE.findall(s2))


# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------

SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6,
         "b": 1e9, "bn": 1e9, "billion": 1e9}
TIME = {"second": 1, "seconds": 1, "sec": 1, "secs": 1, "minute": 60, "minutes": 60,
        "min": 60, "mins": 60, "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
        "h": 3600, "day": 86400, "days": 86400}

# A number not glued to a letter, '#', '.', '/' or ':' on the left (so Q1, v2,
# #412, 1.2.3, 10:30 are labels, not quantities). Comma groups allowed.
_QTY = re.compile(
    r"(?<![\w#./:\-])(\$|EUR\s?|€|£)?"
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(k|K|M|B|bn|mn|thousand|million|billion)\b)?"
    r"(?![\w.]*\d)(?!\.\d)(%|\s?percent\b)?")


def find_quantities(s: str) -> list[dict]:
    """Quantities in s after dates are removed. Each: value (scaled), raw,
    scaled (bool), currency, pct (bool), next_word, time_unit, span."""
    s = _strip_dates(_norm(s))
    out = []
    for m in _QTY.finditer(s):
        cur, num, scale, pct = m.group(1), m.group(2), m.group(3), m.group(4)
        # glued suffix like 4.8M or 48,000k: _QTY allows it via \s? already
        tail = s[m.end():]
        if re.match(r"[A-Za-z]", tail) and not scale:
            continue  # 3rd, 2x, 10am: not a plain quantity
        val = float(num.replace(",", ""))
        sc = SCALE.get((scale or "").lower(), 1.0) if scale else 1.0
        nxt = re.match(r"\s*([A-Za-z][A-Za-z\-']*)", tail)
        nxt_w = nxt.group(1).lower() if nxt else ""
        out.append({"value": val * sc, "raw": num, "base": val, "scaled": bool(scale),
                    "currency": (cur or "").strip(), "pct": bool(pct),
                    "next_word": nxt_w, "time_unit": TIME.get(nxt_w),
                    "decimals": len(num.split(".")[1]) if "." in num else 0,
                    "span": m.span(), "text": s})
    return out


def _precision(q: dict) -> float:
    """Smallest step the written number can resolve, in absolute units."""
    raw = q["raw"].replace(",", "")
    if "." in raw:
        step = 10 ** (-len(raw.split(".")[1]))
    else:
        tz = len(raw) - len(raw.rstrip("0"))
        step = 10 ** tz if raw.strip("0") else 1
    return step * (q["value"] / q["base"] if q["base"] else 1)


_PERIOD_WORDS = {"today", "yesterday", "tomorrow", "tonight", "day", "daily", "week", "weekly",
                 "weekend", "month", "monthly", "quarter", "quarterly", "year", "yearly",
                 "annual", "annually", "fortnight", "semester", "season", "ytd", "mtd"}


def _periods(s: str) -> set[str]:
    """Time scope markers: full dates, years, months, quarters, period words.
    Two numbers about different periods are different facts."""
    s = _norm(s)
    out = {d.isoformat() for d, _ in find_dates(s)}
    rest = s
    for rx, _ in _DATE_PATTERNS:
        rest = rx.sub(" ", rest)
    out |= set(re.findall(r"\b(?:19|20)\d{2}\b", rest))
    low = rest.lower()
    out |= {m[:3] for m in re.findall(r"\b(" + "|".join(MONTHS + [m[:3] for m in MONTHS]) + r")\b", low)}
    out |= {q.lower() for q in re.findall(r"\b([QH][1-4])\b", rest)}
    for w in re.findall(r"[a-z]+", low):
        w2 = {"quarterly": "quarter", "monthly": "month", "weekly": "week", "daily": "day",
              "yearly": "year", "annual": "year", "annually": "year"}.get(w, w)
        if w2 in _PERIOD_WORDS or w2.rstrip("s") in _PERIOD_WORDS:
            out.add(w2.rstrip("s") if w2.rstrip("s") in _PERIOD_WORDS else w2)
    return out


def _same_period(a: str, b: str) -> bool:
    return _periods(a) == _periods(b)


def _hedge(text: str) -> str:
    t = text.lower()
    if BOUND.search(t):
        return "bound"
    if APPROX.search(t):
        return "approx"
    return ""


# ---------------------------------------------------------------------------
# Pre-checks. Each returns None (defer) or
#   {"verdict": "contradiction"|"consistent", "rule": name, "reason": str}
# ---------------------------------------------------------------------------

TOTAL_WORDS = re.compile(r"\b(adds? up to|add up to|sums? to|sum of|in total|totals?|totalling|"
                         r"totaling|combined|altogether|all together|together)\b", re.I)
NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "both": 2}


# Negated, conditional and qualified language needs a semantic judge. Do not
# erase these operators as stopwords when binding an arithmetic relation.
_UNSUPPORTED = re.compile(r"\b(not|no|never|neither|nor|without|except|unless|if|may|might|could|would|should|must|can|either|or)\b|n['’]t\b", re.I)


def _ordered(text: str) -> str:
    return " ".join(_norm(text).lower().strip().rstrip(".").split())


def _guard(a: str, b: str) -> bool:
    return not _UNSUPPORTED.search(a + " " + b) and "\n" not in a + b


def check_sum(a: str, b: str) -> dict | None:
    if not _guard(a, b):
        return None
    for x, y in ((a, b), (b, a)):
        r = _check_sum_dir(x, y)
        if r:
            return {**r, "arithmetic_relation": r["verdict"], "verdict": "unknown",
                    "reason": r["reason"] + "; subject/metric binding is unproved (arithmetic candidate only)."}
    return None


def _check_sum_dir(parts_text: str, total_text: str) -> dict | None:
    if not TOTAL_WORDS.search(total_text) or TOTAL_WORDS.search(parts_text):
        return None
    tq = [q for q in find_quantities(total_text)]
    pq = [q for q in find_quantities(parts_text)]
    if len(tq) != 1 or len(pq) < 2:
        return None
    t = tq[0]
    if t["pct"] or any(q["pct"] for q in pq):
        return None
    # all parts share one unit system: same currency, same scaled-ness of suffix
    # family, no time units mixed in
    if len({q["currency"] for q in pq} | {t["currency"]}) != 1:
        return None
    if any(q["time_unit"] for q in pq) or t["time_unit"]:
        return None
    # if the total sentence names how many parts, it must match
    for w, n in NUM_WORDS.items():
        if re.search(rf"\b{w}\b", total_text, re.I) and n != len(pq):
            return None
    if not (_words(parts_text) & _words(total_text)):
        return None
    # every quantity measures the same noun (or none is named): "5 engineers
    # shipped 3 features" is not a list of parts
    if len({_stem(q["next_word"]) for q in pq + [t] if q["next_word"]} - {"and"}) > 1:
        return None
    pp, tp = _periods(parts_text), _periods(total_text)
    if any(x in pp for x in ("q1", "q2", "q3", "q4")):
        pp = pp | {"quarter"}
    if not tp <= pp:
        return None
    hedge = _hedge(TOTAL_WORDS.sub(" ", total_text))
    if hedge == "bound":
        return None
    total = sum(q["value"] for q in pq)
    diff = abs(total - t["value"])
    why = f"parts {[q['value'] for q in pq]} sum to {total:g}; claim says {t['value']:g}"
    if hedge == "approx":
        rel = diff / max(abs(total), 1e-9)
        if rel <= 0.02:
            return {"verdict": "consistent", "rule": "sum", "reason": why}
        if rel >= 0.10:
            return {"verdict": "contradiction", "rule": "sum", "reason": why}
        return None
    step = _precision(t)
    if diff < 1e-9 * max(1, abs(total)):
        return {"verdict": "consistent", "rule": "sum", "reason": why}
    if diff > step:
        return {"verdict": "contradiction", "rule": "sum", "reason": why}
    return None


_FRAC = re.compile(r"(?<![\w.,])(\d+)\s+(?:of|out of)\s+(?:the\s+|all\s+|our\s+)?(\d+)\b(?!\s*%)", re.I)


def check_percent(a: str, b: str) -> dict | None:
    if not _guard(a, b):
        return None
    for x, y in ((a, b), (b, a)):
        r = _check_percent_dir(x, y)
        if r:
            return r
    return None


def _check_percent_dir(frac_text: str, pct_text: str) -> dict | None:
    fr = _FRAC.findall(_strip_dates(frac_text))
    if len(fr) != 1 or _FRAC.search(_strip_dates(pct_text)):
        return None
    pq = [q for q in find_quantities(pct_text) if q["pct"]]
    if len(pq) != 1 or any(q["pct"] for q in find_quantities(frac_text)):
        return None
    if len(find_quantities(pct_text)) != 1:
        return None
    if not _same_period(frac_text, pct_text):
        return None
    num, den = int(fr[0][0]), int(fr[0][1])
    if den == 0 or num > den:
        return None
    # Exact ordered assertion frame, preserving subject, predicate and scope.
    # Supported grammar: "30 of 100 users are registered" / "30% of users are registered".
    fm = re.fullmatch(r"(\d+) (?:of|out of) (\d+) (.+)", _ordered(frac_text))
    pm = re.fullmatch(r"\d+(?:\.\d+)?(?:%| percent) of (.+)", _ordered(pct_text))
    if not fm or not pm or fm.group(3) != pm.group(1):
        return None
    hedge = _hedge(pct_text)
    if hedge == "bound":
        return None
    pct = 100.0 * num / den
    z = pq[0]["base"]
    diff = abs(pct - z)
    why = f"{num}/{den} = {pct:.1f}%; claim says {z:g}%"
    ok = 1.5 if hedge == "approx" else 0.5 + 1e-9
    if pq[0]["decimals"]:
        ok = max(ok, 0.5 * 10 ** -pq[0]["decimals"] + 1e-9)
    if diff <= ok:
        return {"verdict": "consistent", "rule": "percent", "reason": why}
    if diff >= 5:
        return {"verdict": "contradiction", "rule": "percent", "reason": why}
    return None


def _frame(text: str, q: dict) -> str:
    """Ordered exact assertion with only the measured quantity/unit replaced."""
    t = q["text"]
    start, end = q["span"]
    if q["time_unit"]:
        unit = re.match(r"\s*" + re.escape(q["next_word"]) + r"\b", t[end:], re.I)
        if not unit:
            return ""
        end += unit.end()
    return _ordered(t[:start] + " MEASUREMENT " + t[end:])


def check_unit_scale(a: str, b: str) -> dict | None:
    if not _guard(a, b):
        return None
    qa, qb = find_quantities(a), find_quantities(b)
    if len(qa) != 1 or len(qb) != 1:
        return None
    x, y = qa[0], qb[0]
    if not _same_period(a, b):
        return None
    if x["pct"] or y["pct"] or x["currency"] != y["currency"]:
        return None
    timey = bool(x["time_unit"]) and bool(y["time_unit"])
    scaled = (x["scaled"] or y["scaled"]) and not (x["time_unit"] or y["time_unit"])
    if not (timey or scaled):
        return None
    if timey and x["time_unit"] == y["time_unit"]:
        return None  # same unit, plain value comparison, Jev handles it
    if scaled and x["scaled"] and y["scaled"] and x["value"] / x["base"] == y["value"] / y["base"]:
        return None  # same suffix on both sides: plain value comparison
    if scaled:
        # the noun right after the number must be the same thing
        nx = x["next_word"] if x["next_word"] not in SCALE else ""
        ny = y["next_word"] if y["next_word"] not in SCALE else ""
        if not nx or _stem(nx) != _stem(ny):
            return None
    fx, fy = _frame(a, x), _frame(b, y)
    if not fx or not fy:
        return None
    if fx != fy:
        return None
    hedges = {_hedge(a), _hedge(b)}
    if "bound" in hedges:
        return None
    va = x["value"] * (x["time_unit"] or 1)
    vb = y["value"] * (y["time_unit"] or 1)
    rel = abs(va - vb) / max(abs(va), abs(vb), 1e-9)
    why = f"{x['raw']}{' ' + x['next_word'] if timey else ''} = {va:g} vs {y['raw']} = {vb:g}"
    tight = 0.10 if "approx" in hedges else 0.005
    if rel <= tight:
        return {"verdict": "consistent", "rule": "unit_scale", "reason": why}
    if rel >= (0.5 if "approx" in hedges else 0.05):
        return {"verdict": "contradiction", "rule": "unit_scale", "reason": why}
    return None


_RATE = [
    # every user registers exactly 2 devices / each user has 3 devices
    re.compile(r"\b(?:every|each)\s+([a-z]+)\s+(?:[a-z]+\s+){0,3}?(?:exactly\s+)?(\d+(?:\.\d+)?)\s+([a-z]+)", re.I),
    # 2 devices per user / 2 devices for every user
    re.compile(r"\b(\d+(?:\.\d+)?)\s+([a-z]+)\s+(?:per|for every|for each)\s+([a-z]+)", re.I),
]


def check_rate(a: str, b: str) -> dict | None:
    if not _guard(a, b):
        return None
    for x, y in ((a, b), (b, a)):
        r = _check_rate_dir(x, y)
        if r:
            return {**r, "arithmetic_relation": r["verdict"], "verdict": "unknown",
                    "reason": r["reason"] + "; subject/metric binding is unproved (arithmetic candidate only)."}
    return None


def _check_rate_dir(rate_text: str, claim_text: str) -> dict | None:
    t = _strip_dates(_norm(rate_text))
    rate = None
    m = _RATE[0].search(t)
    if m:
        rate = (_stem(m.group(1)), float(m.group(2)), _stem(m.group(3)), m)
    else:
        m = _RATE[1].search(t)
        if m:
            rate = (_stem(m.group(3)), float(m.group(1)), _stem(m.group(2)), m)
    if not rate:
        return None
    per_noun, k, out_noun, m = rate
    if not _same_period(rate_text, claim_text):
        return None
    if re.search(r"\b(up to|at most|at least|on average|average|about|around|roughly|"
                 r"approximately|some|most|many|or more|or fewer)\b", t, re.I):
        return None
    # the base count: a quantity in rate_text whose next word is the per-noun
    base = [q for q in find_quantities(rate_text)
            if _stem(q["next_word"]) == per_noun and not q["pct"]]
    if len(base) != 1:
        return None
    claims = [q for q in find_quantities(claim_text) if not q["pct"]]
    if len(claims) != 1 or _stem(claims[0]["next_word"]) != out_noun:
        return None
    # the claim text must not itself contain a count of the per-noun
    if any(_stem(q["next_word"]) == per_noun for q in find_quantities(claim_text)):
        return None
    if _hedge(claim_text):
        return None
    # same subject: share a content word other than the nouns themselves
    if not ((_words(rate_text) & _words(claim_text)) - {per_noun, out_noun}):
        return None
    expect = base[0]["value"] * k
    got = claims[0]["value"]
    rel = abs(expect - got) / max(abs(expect), abs(got), 1e-9)
    why = f"{base[0]['value']:g} {per_noun} x {k:g} {out_noun} = {expect:g}; claim says {got:g}"
    if rel <= 0.005:
        return {"verdict": "consistent", "rule": "rate", "reason": why}
    if rel >= 0.05:
        return {"verdict": "contradiction", "rule": "rate", "reason": why}
    return None


_WD_CLAIM = re.compile(
    r"(?<!every )(?<!each )(?<!next )(?<!last )(?<!this )(?<!following )(?<!previous )"
    r"\b(?:on|is|falls on|lands on|happens on|takes place on|was|will be)\s+(?:a\s+)?"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b(?!s)", re.I)
_WD_ANY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b", re.I)
_WD_ADJ = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+$", re.I)


def check_weekday(a: str, b: str) -> dict | None:
    if not _guard(a, b):
        return None
    a, b = _norm(a), _norm(b)
    both = a + "\n" + b
    if len(_WD_ANY.findall(both)) != 1:
        return None
    dates = find_dates(a) + find_dates(b)
    if len({d for d, _ in dates}) != 1:
        return None
    if _partial_dates(a) + _partial_dates(b):
        return None
    d = dates[0][0]
    wd, wd_idx = None, None
    for idx, text in enumerate((a, b)):
        m = _WD_CLAIM.search(text)
        if m:
            wd, wd_idx = m.group(1).lower(), idx
        else:
            # "Monday, 5 October 2026" / "Monday 2026-10-05"
            for _, (s, _) in find_dates(text):
                m2 = _WD_ADJ.search(text[:s])
                if m2:
                    wd, wd_idx = m2.group(1).lower(), idx
    if not wd:
        return None
    if re.search(r"\b(every|each|next|last|this|following|previous|until|by|before|after|"
                 r"since|or)\s+" + wd, both, re.I):
        return None
    # the weekday and the date must sit in different items: a weekday that
    # disagrees with a date in its own item is that item contradicting itself,
    # not the pair contradicting each other (seen on a real memory that says
    # "Sunday April 27, 2026"; that day is a Monday)
    if find_dates((a, b)[wd_idx]):
        return None
    # Explicit ordered subject/predicate frame; shared words do not bind events.
    weekday_text = (a, b)[wd_idx]
    date_text = (a, b)[1 - wd_idx]
    wm = re.fullmatch(r"(.+) is on (" + "|".join(WEEKDAYS) + r")", _ordered(weekday_text))
    dm = re.fullmatch(r"(.+) is on (\d{4}-\d{2}-\d{2})", _ordered(date_text))
    if not wm or not dm or wm.group(1) != dm.group(1):
        return None
    true_wd = WEEKDAYS[d.weekday()]
    why = f"{d.isoformat()} is a {true_wd.capitalize()}; claim says {wd.capitalize()}"
    if true_wd == wd:
        return {"verdict": "consistent", "rule": "weekday", "reason": why}
    return {"verdict": "contradiction", "rule": "weekday", "reason": why}


PRECHECKS: list[Callable[[str, str], dict | None]] = [
    check_sum, check_percent, check_unit_scale, check_rate, check_weekday]


def precheck(a: str, b: str) -> dict | None:
    """Run every pre-check. A contradiction from any rule wins; a consistency
    result is returned only when no rule found a contradiction. A rule that
    raises defers."""
    found = []
    for fn in PRECHECKS:
        try:
            r = fn(a or "", b or "")
        except Exception:  # noqa: BLE001 - a broken rule defers, never decides
            r = None
        if r:
            found.append(r)
    for r in found:
        if r["verdict"] == "contradiction":
            return r
    return found[0] if found else None
