"""Store truth — wrong-object ratios re-derived from the live store.

Not a threshold check and not a trend. A handful of ratios where a number is true
about ONE object and false about another — the defect Agent Science exists to catch,
surfaced as plain language with repro SQL on every line.

Ported from the hackathon measurement-bench collab (Claude Lane B); lives here under
a distinct name because `helicon portrait` is the Qwen-narrated identity reading.
"""
from __future__ import annotations

import sqlite3


def _scalar(conn: sqlite3.Connection, sql: str, default: int = -1) -> int:
    try:
        return int(conn.execute(sql).fetchone()[0])
    except Exception:
        return default


def findings(conn: sqlite3.Connection) -> list[dict]:
    """Non-obvious wrong-object ratios, each with repro queries."""
    out: list[dict] = []

    stored = _scalar(conn, "SELECT COUNT(*) FROM helicon_cubes")
    killed = _scalar(conn, "SELECT COUNT(*) FROM helicon_cubes WHERE review_status='killed'")
    retrievals = _scalar(conn, "SELECT COUNT(*) FROM retrieval_log")
    reviews = _scalar(conn, "SELECT COUNT(*) FROM reviews")
    human_reviews = _scalar(
        conn, "SELECT COUNT(*) FROM reviews WHERE session_id LIKE 'cli-human%'")
    auto_reviews = _scalar(
        conn, "SELECT COUNT(*) FROM reviews WHERE session_id='auto-triage'")

    if stored > 0 and retrievals >= 0:
        ratio = stored // max(retrievals, 1)
        out.append({
            "title": "Written and judged, barely read.",
            "lines": [
                (f"{stored:,} memories stored, {killed:,} killed "
                 f"({100 * killed / stored:.0f}%),"),
                f"but only {retrievals} logged retrievals ever.",
            ],
            "point": (
                "the store is a JUDGEMENT engine, not a retrieval one. Any pitch "
                "that sells it as 'memory the agent reads from' is describing the "
                f"wrong object by {ratio:,}x."
            ),
            "repro": (
                "SELECT COUNT(*) FROM helicon_cubes  /  "
                "...WHERE review_status='killed'  /  "
                "SELECT COUNT(*) FROM retrieval_log"
            ),
        })

    if reviews > 0 and human_reviews >= 0:
        item: dict = {
            "title": f"'{reviews:,} reviews' is mostly machine.",
            "lines": [
                f"genuine human CLI reviews: {human_reviews}.  "
                f"auto-triage: {auto_reviews:,}.",
            ],
            "repro": (
                "SELECT COUNT(*) FROM reviews  /  "
                "...WHERE session_id LIKE 'cli-human%'"
            ),
        }
        if human_reviews > 0:
            item["point"] = (
                f"quoting {reviews:,} as HUMAN review is wrong by "
                f"~{reviews // max(human_reviews, 1):,}x. "
                "The real human signal is the ruled audit findings, not the review table."
            )
        else:
            item["point"] = (
                "The real human signal is the ruled audit findings, not the review table."
            )
        out.append(item)

    return out


def render(conn: sqlite3.Connection, db_path: str) -> str:
    lines = [f"store truth — {db_path}", "=" * 72, ""]
    items = findings(conn)
    if not items:
        lines.append("  (no store tables to read yet)")
    for item in items:
        lines.append(f"  {item['title']}")
        for ln in item["lines"]:
            lines.append(f"    {ln}")
        if item.get("point"):
            lines.append(f"    → {item['point']}")
        lines.append(f"    repro: {item['repro']}")
        lines.append("")
    lines += [
        "=" * 72,
        "Each line is a number that is TRUE about one object and FALSE about another.",
        "That is the defect the bench exists to catch — here, caught on your own store.",
        "",
    ]
    return "\n".join(lines)
