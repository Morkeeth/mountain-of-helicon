"""Versioned, default-deny sensitivity classifier for context packets.

The privacy guarantee is a property of the BUILDER, not of the operator
remembering: anything not explicitly allowlisted as public/internal is treated as
private and excluded from a packet. Hard-private material (journal, finance,
wallet, credentials) can never enter a packet regardless of source.

This is additive and local — it changes no existing behaviour and calls nothing.
"""
import re

CLASSIFICATION_POLICY_VERSION = "cp-2026-07-19.1"

# Sources allowlisted to enter a LOCAL packet as 'internal'. Nothing is 'public'
# by default — a packet is local, so 'internal' is the ceiling here.
_INTERNAL_SOURCES = {"claude-code", "chatgpt", "obsidian", "git", "skills", "demo"}

# Hard-private markers: if any appears in the source ref, scope, or content, the
# item is private and excluded, no matter how it was sourced.
_HARD_PRIVATE = re.compile(
    r"\b(journal|diary|finance|financ|wallet|seed[\s_-]?phrase|private[\s_-]?key|"
    r"salary|passport|ssn|password|credential|bank|balance|net[\s_-]?worth)\b",
    re.IGNORECASE,
)


def classify(source: str = "", scope: str = "", source_ref: str = "", content: str = "") -> str:
    """Return 'public' | 'internal' | 'private'. Default-deny: an unrecognized
    source, or any hard-private marker, yields 'private'."""
    haystack = f"{scope} {source_ref} {content}"
    if _HARD_PRIVATE.search(haystack):
        return "private"
    if (source or "").strip().lower() in _INTERNAL_SOURCES:
        return "internal"
    return "private"  # unmatched source -> private (default-deny)


def eligible_for_local_packet(sensitivity: str) -> bool:
    """Only public/internal items may enter a local packet; private never does."""
    return sensitivity in ("public", "internal")
