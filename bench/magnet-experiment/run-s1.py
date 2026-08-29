#!/usr/bin/env python3
"""EXP-MAGNET-01. Build the flood, run the filter, score against the planted set.

Deterministic end to end: no model calls, no randomness that is not seeded, so a
reader can re-run it and get the same numbers. See PREREGISTRATION.md — the
predictions were written before this ran.
"""
import json, os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from helicon.magnet import inventory, gaps, rank

STACK = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/.claude")
random.seed(20260816)          # seeded: the flood must be identical on re-run

# --- the planted set. Four kinds; two are adversarial by design. -------------
PLANTED = [
    # DIRECT — uses the filter's own vocabulary for an uncovered capability
    {"name": "pdb-navigator", "kind": "direct", "surface": "skills",
     "description": "Debug a failing test by driving pdb, setting breakpoints and bisecting the stack trace to the first bad frame"},
    {"name": "safe-rename", "kind": "direct", "surface": "skills",
     "description": "Refactor across a repo: rename a symbol, extract a function, simplify nested conditionals, per-site review"},
    {"name": "trace-reader", "kind": "direct", "surface": "skills",
     "description": "Read a stack trace, find the repro, and bisect commits to the first failing one"},
    # SYNONYM — fills the SAME gaps, using words the capability list does not hold
    {"name": "fault-localiser", "kind": "synonym", "surface": "skills", "capabilities": ["debug"],
     "description": "Narrow a misbehaving program to the smallest failing input and the exact line responsible"},
    {"name": "code-surgeon", "kind": "synonym", "surface": "skills", "capabilities": ["refactor"],
     "description": "Restructure a module in place without changing behaviour, moving responsibilities between units"},
    {"name": "postmortem-pilot", "kind": "synonym", "surface": "skills", "capabilities": ["debug"],
     "description": "Walk backwards from a crash to the change that caused it, one hypothesis at a time"},
    # SURFACE — targets an empty surface
    {"name": "subagent-fanout", "kind": "surface", "surface": "agents",
     "description": "Define reusable subagents that fan out across a repository and report structured findings"},
    {"name": "reviewer-agent", "kind": "surface", "surface": "agents",
     "description": "A standing agent definition that inspects a change set and returns ranked observations"},
    # DUPLICATE — near-copies of skills already installed; must be DEMOTED
    {"name": "writing-coach", "kind": "duplicate", "surface": "skills",
     "description": "Writing rules for anything with a reader. Draft an email, reply, DM, LinkedIn note, connection request, cover letter, bio or post"},
    {"name": "task-inbox", "kind": "duplicate", "surface": "skills",
     "description": "Task capture, closing and eviction. Add to the task list, push to tasks, put it on the board, triage and prune it"},
]

NOISE_DOMAINS = [
    "generate marketing headlines for a landing page", "convert currencies at live rates",
    "summarise a podcast episode into bullet points", "plan a wedding seating chart",
    "translate subtitles between languages", "track calories from a photo",
    "draft a real estate listing", "tune a guitar by ear",
    "recommend wine pairings for a menu", "score a fantasy football lineup",
    "book a restaurant table", "identify a plant from a leaf",
    "compose a birthday poem", "estimate shipping costs across carriers",
    "generate a colour palette from a photograph", "convert a recipe between units",
    "practise flashcards with spaced repetition", "log a workout set",
    "find a flight under a price threshold", "read a tarot spread",
]
BOOSTER = ["An awesome tool that supercharges your workflow effortlessly.",
           "Unlock seamless productivity with this must-have helper.",
           "Empower your team to move faster than ever before."]

flood = []
for i in range(990):
    d = NOISE_DOMAINS[i % len(NOISE_DOMAINS)]
    extra = BOOSTER[i % len(BOOSTER)] if i % 7 == 0 else ""
    flood.append({"name": f"noise-{i:03d}", "surface": "skills",
                  "description": f"{d}. {extra}".strip(), "kind": "noise"})
# planted dicts already carry their capabilities field; noise carries none
flood.extend(PLANTED)
random.shuffle(flood)

inv = inventory(STACK)
g = gaps(inv)
res = rank(flood, inv, g, top=len(flood))
ranked = res["ranked"]                    # text-verified, trustable tier ONLY
claimed_tier = {r["name"] for r in res["claimed"]}   # declared-unverified tier
order = {r["name"]: i for i, r in enumerate(ranked)}
by_name = {r["name"]: r for r in ranked}
for r in res["demoted"]:
    by_name[r["name"]] = r; order[r["name"]] = 10**6 + len(order)
NO_SIGNAL = res["no_signal"]

def kind_of(n): return next((p["kind"] for p in PLANTED if p["name"] == n), "noise")
should_surface = [p["name"] for p in PLANTED if p["kind"] != "duplicate"]
dupes = [p["name"] for p in PLANTED if p["kind"] == "duplicate"]

top20 = [r["name"] for r in ranked[:20]]
top3 = [r["name"] for r in ranked[:3]]
# Two honest recalls: the trustable primary tier, and primary + author-claims.
found_primary = [n for n in should_surface if n in top20]
recall_primary = len(found_primary) / len(should_surface)
found_either = [n for n in should_surface if n in top20 or n in claimed_tier]
recall_with_claims = len(found_either) / len(should_surface)
recall20 = recall_primary
precision3 = sum(1 for n in top3 if kind_of(n) != "noise") / 3

per_kind = {}
for k in ("direct", "synonym", "surface"):
    names = [p["name"] for p in PLANTED if p["kind"] == k]
    per_kind[k] = {"found": sum(1 for n in names if n in top20), "of": len(names)}

dupe_result = {n: {"score": by_name[n]["score"],
                   "demoted": by_name[n]["score"] < 0} for n in dupes}

result = {
    "experiment": "EXP-MAGNET-01-S1 (declared tags)", "stack": STACK,
    "flood": len(flood), "planted": len(PLANTED), "noise": 990,
    "gaps": {"empty_surfaces": g["empty_surfaces"], "uncovered": g["uncovered"]},
    "recall_primary_at_20": round(recall_primary, 3),
    "recall_with_claims": round(recall_with_claims, 3),
    "precision_at_3": round(precision3, 3),
    "claimed_tier_size": res["claimed_total"],
    "per_kind": per_kind, "duplicates": dupe_result,
    "top20": top20[:20],
    "no_signal_count": NO_SIGNAL,
    "planted_ranks": {p["name"]: {"rank": order.get(p["name"], None),
                                  "score": by_name.get(p["name"], {}).get("score", 0),
                                  "kind": p["kind"]} for p in PLANTED},
    "token_cost": 0,
}
print(json.dumps(result, indent=2))
