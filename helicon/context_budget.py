"""Context-budget / context-rot guard — treat the window as a finite attention
budget, not free storage.

The 2026 research backbone (why this exists):

  · Every frontier model degrades as its window fills — "context rot" — well
    before the hard token limit. The Chroma 2025 study (18 models) and Anthropic's
    "effective context engineering" both frame the window as a finite *attention
    budget* with diminishing returns; independent write-ups put the practical
    onset near ~32k tokens. Redis and others prescribe the same fix: keep the
    working set small and pull detail in on demand (write / select / compress /
    isolate).

Helicon's honesty rule holds here: we do NOT report a measured accuracy or an
invented "you have lost X%%" number — that would be the fabricated figure this
repo exists to catch. We report a BUDGET STATUS, the headroom to the rot onset,
and the action the research prescribes, so a human can compress/select/isolate
BEFORE a run's context rots. The threshold is stated and overridable, never
presented as a law of nature.
"""

# Where degradation is commonly observed to begin. A planning threshold, not a
# measurement of this store — overridable per call / per config.
ONSET_TOKENS = 32_000

# The band just below onset where the honest move is "plan to trim", not "act now".
WATCH_FRACTION = 0.75


def assess(tokens, *, onset: int = ONSET_TOKENS, budget: int | None = None) -> dict:
    """Assess a context size (in tokens) against the rot onset and an optional
    explicit budget. Pure and deterministic.

    status:
      healthy — well within the attention budget
      watch   — in the band below onset; plan to compress/select
      over    — past the onset (or over an explicit budget); act before this run
    """
    tokens = max(int(tokens or 0), 0)
    onset = max(int(onset), 1)
    watch_at = int(onset * WATCH_FRACTION)

    over_budget = budget is not None and tokens > int(budget)
    over_onset = tokens >= onset
    if over_budget or over_onset:
        status = "over"
    elif tokens >= watch_at:
        status = "watch"
    else:
        status = "healthy"

    headroom = onset - tokens  # negative once past onset — the overshoot

    if status == "healthy":
        note = (f"{tokens:,} tokens — well within the ~{onset:,}-token attention "
                f"budget ({headroom:,} to the context-rot onset).")
    elif status == "watch":
        note = (f"{tokens:,} tokens — approaching the ~{onset:,}-token context-rot "
                f"onset ({headroom:,} to go); plan to compress or select.")
    elif over_budget and not over_onset:
        note = (f"{tokens:,} tokens — over the set budget of {int(budget):,}; "
                f"compress, select, or isolate before this run.")
    else:
        over_by = tokens - onset
        note = (f"{tokens:,} tokens — {over_by:,} past the ~{onset:,}-token "
                f"context-rot onset; compress, select, or isolate before this run "
                f"(rot degrades recall well before the hard limit).")

    return {
        "tokens": tokens,
        "onset": onset,
        "watch_at": watch_at,
        "budget": int(budget) if budget is not None else None,
        "status": status,
        "over_onset": over_onset,
        "over_budget": over_budget,
        "headroom_to_onset": headroom,
        "note": note,
    }
