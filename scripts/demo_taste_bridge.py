#!/usr/bin/env python3
"""Taste Machine × Helicon bridge — the never-twice guarantee, applied to taste.

Zero setup. Simulates Taste Machine emitting verdicts (the human ruling drafts),
then shows Helicon's guard predicting the ruling BEFORE a human is asked again —
so a shape that keeps getting killed stops reaching the review queue.
"""
import os
import tempfile

from helicon.db import init_db
from helicon.taste import ingest_verdict, taste_guard


def v(h, verdict, move, reason=""):
    return {"artifact_hash": h, "human_verdict": verdict, "move": move,
            "kind": "x-reply", "reason": reason, "content": f"draft {h}"}


def main() -> int:
    db = os.path.join(tempfile.gettempdir(), "helicon-taste-demo.db")
    if os.path.exists(db):
        os.remove(db)
    conn = init_db(db)

    print("Taste Machine rules a batch of drafts; Helicon remembers each verdict:\n")
    ruled = [
        v("d1", "kill", "lived-example", "shoehorned a personal story"),
        v("d2", "kill", "lived-example", "shoehorn again"),
        v("d3", "kill", "lived-example", "same move, forced"),
        v("d4", "send", "question", ""),
        v("d5", "send", "question", ""),
    ]
    for r in ruled:
        ingest_verdict(conn, r)
        print(f"  {r['human_verdict']:>4}  move={r['move']:<14} {r['reason']}")

    print("\nNow a NEW draft arrives. Before asking the human, TM consults Helicon:\n")
    for move in ("lived-example", "question"):
        g = taste_guard(conn, move=move)
        if g["already_ruled"]:
            print(f"  move '{move}': SUPPRESS — {g['reason']}")
        else:
            print(f"  move '{move}': show it — no strong prior")

    print("\nThe kill-prone shape never reaches the human again; the safe one still does.")
    print("That is never-twice — Taste Machine decides, Helicon remembers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
