"""Time has one space in this store, and it is UTC-naive.

`datetime.utcnow()` is deprecated and scheduled for REMOVAL, so it had to go —
but the obvious replacement, `datetime.now(datetime.UTC)`, is WRONG here. It
returns an aware datetime whose .isoformat() carries '+00:00', and those strings
would be written into a store whose comparisons are naive. timeutil.ts_norm
exists because raw string compare across dialects (2,309 'Z' stamps, 500
'+HH:MM' offsets, ~420 naive, one literal '{{date}}') misfiled the ±2h band
around a rename and broke R4's history/current-claim split.

A wrong timestamp is the hardest kind of bug to see: it looks fine.
"""
import pathlib
import re
from datetime import datetime

from helicon.timeutil import ts_norm, utc_now, utc_now_iso

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_utc_now_is_naive():
    assert utc_now().tzinfo is None
    assert "+00:00" not in utc_now_iso()
    assert not utc_now_iso().endswith("Z")


def test_utc_now_is_actually_utc_not_merely_naive():
    """Naive, but naive-UTC — never naive-LOCAL. A local-clock stamp in a UTC
    store is wrong by the machine's offset, silently, and looks perfectly
    well-formed. This machine runs at +02:00, which is exactly the band that
    misfiled the rename."""
    from datetime import timezone
    reference = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((utc_now() - reference).total_seconds()) < 2


def test_utc_now_round_trips_through_ts_norm_unchanged():
    """The invariant that matters: a stamp we write must already be in the
    space ts_norm normalizes to, so normalizing it is a no-op."""
    now = utc_now_iso()
    assert ts_norm(now) == now


def test_an_aware_stamp_would_not_round_trip():
    """Why datetime.now(UTC) was not the fix — kept as executable evidence."""
    from datetime import timezone
    aware = datetime.now(timezone.utc).isoformat()
    assert "+00:00" in aware
    assert ts_norm(aware) != aware


def test_no_deprecated_utcnow_anywhere_in_the_tree():
    """The system fix, not a one-off cleanup: 162 deprecation warnings were how
    this got missed for so long. Only timeutil may NAME it, in the docstring
    that explains the migration."""
    offenders = []
    for path in list(ROOT.glob("helicon/**/*.py")) + list(ROOT.glob("tests/*.py")) \
            + list(ROOT.glob("scripts/*.py")):
        # timeutil explains the migration; this file states the rule. Both
        # must NAME the dead call to be readable.
        if path.name in ("timeutil.py", "test_timeutil_naive.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\butcnow\s*\(", text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"datetime.utcnow() is scheduled for removal: {offenders}"
