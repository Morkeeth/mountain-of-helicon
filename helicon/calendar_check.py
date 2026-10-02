"""Narrow, deterministic weekday/full-date checks within one explicit item.

No pairing, model, clock-relative interpretation or choice of intended deadline.
Unsupported or ambiguous prose returns None, not a clean factual verdict.
"""
from datetime import date
import re

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
_MONTH = "(" + "|".join(m + "|" + m[:3] for m in _MONTHS) + ")"
_WEEKDAY = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b", re.I)
_DATES = (
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH + r"\.?\s*,?\s+(\d{4})\b", re.I), "dmy"),
    (re.compile(r"\b" + _MONTH + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I), "mdy"),
)
_DEFER = re.compile(r"\b(not|never|wrong|incorrect|typo|example|quoted?|said|says|claimed|reported|if|unless|would|could|might|before|after|until|since|by|or|every|each|next|last|this|following|previous)\b", re.I)


def calendar_candidate(text: str) -> bool:
    """Recognize unsupported calendar mentions so review coverage can abstain.

    This is not claim admission and never creates a contradiction by itself.
    """
    return bool(re.search(r"\b(?:" + "|".join(WEEKDAYS) + r")s?\b", text, re.I)
                and (re.search(r"\b" + _MONTH + r"\.?\s+\d|\d\s+" + _MONTH + r"\b", text, re.I)
                     or re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}", text)))


def check_weekday_item(text: str) -> dict | None:
    """Check one adjacent English weekday/full-date declaration, Gregorian.

    None means unsupported, ambiguous or non-assertive. An upheld check says
    only that these two calendar fields agree, never that an event is true.
    """
    if not isinstance(text, str) or "\n" in text.strip() or _DEFER.search(text):
        return None
    if any(c in text for c in '`"\'“”‘’') or re.search(r"\b\d{1,2}/\d{1,2}\b", text):
        return None
    weekdays = list(_WEEKDAY.finditer(text))
    dates = [(m, kind) for rx, kind in _DATES for m in rx.finditer(text)]
    if len(weekdays) != 1 or len(dates) != 1:
        return None
    # A second month mention may be a yearless date; do not silently attach it.
    if len(re.findall(r"\b" + _MONTH + r"\b", text, re.I)) > 1:
        return None
    wd, (m, kind) = weekdays[0], dates[0]
    if wd.end() <= m.start():
        gap = text[wd.end():m.start()]
        adjacent = re.fullmatch(r"[\s,:(]*", gap) is not None
    else:
        gap = text[m.end():wd.start()]
        adjacent = m.end() <= wd.start() and re.fullmatch(r"[\s,)]*(?:(?:is|falls on|lands on)\s+)?", gap, re.I) is not None
    if not adjacent:
        return None
    try:
        if kind == "iso":
            day = date(int(m[1]), int(m[2]), int(m[3]))
        else:
            month, number = (m[2], m[1]) if kind == "dmy" else (m[1], m[2])
            month_number = next(i for i, name in enumerate(_MONTHS, 1) if name[:3].lower() == month[:3].lower())
            day = date(int(m[3]), month_number, int(number))
    except (ValueError, StopIteration):
        return None
    expected = WEEKDAYS[day.weekday()]
    claimed = wd[0].capitalize()
    return dict(date=day.isoformat(), claimed_weekday=claimed, calculated_weekday=expected,
                verdict="upheld" if claimed == expected else "contradicted",
                basis="Python datetime.date.weekday; proleptic Gregorian calendar",
                detail=f"{day.isoformat()} computes to {expected}; this item says {claimed}.")
