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
