"""One store, four timestamp dialects.

The live DB carries 2,309 'Z'-suffixed stamps, 500 '+HH:MM' offsets, ~420
naive ISO strings, and at least one literal '{{date}}' template that was
ingested as-is. Raw string comparison across these is wrong by up to the
offset (and '{' sorts after every digit, so template garbage compares as
the FUTURE). Every cross-timestamp comparison goes through ts_norm:
UTC-naive ISO out; naive input is treated as already-UTC; unparseable
input becomes "" — which sorts as oldest, and oldest is always the safe
side (history, not current-claim; pre-resolution, not resurfaced).
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Now, as a UTC-NAIVE datetime — the store's comparison space.

    `datetime.utcnow()` is deprecated and scheduled for removal, but the obvious
    replacement is wrong here. `datetime.now(datetime.UTC)` returns an AWARE
    datetime whose .isoformat() carries a '+00:00' suffix, and those strings
    would be written into a store whose comparisons are naive: ts_norm exists
    precisely because raw string compare across dialects misfiled the ±2h band
    around a rename and broke R4's history/current-claim split. Swapping the
    call without preserving naiveté would silently reintroduce that bug in the
    one place hardest to notice — a timestamp that looks fine.

    So: aware internally (correct clock), naive on the way out (correct space).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def ts_norm(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat()
