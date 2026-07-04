"""Demo: audit a real Agent-Skills library for dead weight.

Nobody regression-tests a skills library. Helicon does: each SKILL.md becomes a
cube, and deterministic checks surface what's wrong on REAL skills:

  - trigger collision : two skills whose triggers (name+description) overlap so
    much they will fight to fire (redundancy / ambiguous routing)
  - thin trigger      : a skill with no/too-short description — the model can't
    reliably decide when to load it
  - stub body         : a skill that is all trigger, no payload

Runs on your actual skills. No fixture, no ground truth.

Run:  python3 scripts/demo_skills_audit.py
      SKILL_ROOTS="~/.claude/skills,~/CODE" python3 scripts/demo_skills_audit.py
"""
import os
import re
import sys
import tempfile
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helicon.connectors import skills
from helicon.scanner import result_to_cube
from helicon.db import init_db, insert_cube, rebuild_fts

DEFAULT_ROOTS = [
    "~/.claude/skills",
    "~/.claude/plugins/marketplaces/claude-plugins-official",
    "~/CODE",
]
_WORD = re.compile(r"[A-Za-z0-9]+")
STOP = set("the a an and or to of for with when use used using this that your you "
           "on in at is are be it as if from into via can will not no do does".split())


def terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")
            if len(w) > 2 and w.lower() not in STOP}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def banner(msg):
    print(f"\n{'='*70}\n{msg}\n{'='*70}")


def main():
    roots = os.environ.get("SKILL_ROOTS")
    roots = [r.strip() for r in roots.split(",")] if roots else DEFAULT_ROOTS

    banner("1. SCAN the skills library")
    results = skills.scan({"skill_roots": roots})
    print(f"   ingested {len(results)} skills from {len(roots)} root(s)")
    if not results:
        print("   (no skills found — set SKILL_ROOTS)")
        return

    db_path = os.path.join(tempfile.mkdtemp(prefix="helicon-skills-"), "s.db")
    conn = init_db(db_path)
    for r in results:
        insert_cube(conn, result_to_cube(r))
    rebuild_fts(conn)

    # trigger = name + description; body length from content beyond description
    skmeta = []
    for r in results:
        name = r.metadata["skill_name"]
        desc = r.metadata["description"]
        skmeta.append({
            "name": name,
            "desc": desc,
            "trigger_terms": terms(f"{name} {desc}"),
            "desc_len": r.metadata["desc_len"],
            "body_len": max(0, len(r.content) - len(desc)),
            "path": r.metadata["path"],
        })

    banner("2a. EXACT DUPLICATES — the same skill installed in multiple places")
    by_name = {}
    for s in skmeta:
        by_name.setdefault(s["name"].lower(), []).append(s)
    dup_groups = {n: g for n, g in by_name.items() if len(g) > 1}
    print(f"   {len(dup_groups)} skill names are installed more than once "
          f"({sum(len(g) for g in dup_groups.values())} cubes collapse to {len(dup_groups)}):")
    for n, g in sorted(dup_groups.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"     - '{g[0]['name']}' x{len(g)}  e.g. {g[0]['path']}")

    banner("2b. TRIGGER COLLISIONS — DIFFERENT skills that will fight to fire (>0.5)")
    # one representative per unique name so pairs aren't repeated by duplicates
    uniq = list({s["name"].lower(): s for s in skmeta}.values())
    print(f"   ({len(uniq)} unique skills after collapsing duplicates)")
    collisions = []
    for a, b in combinations(uniq, 2):
        j = jaccard(a["trigger_terms"], b["trigger_terms"])
        if j > 0.5:
            collisions.append((j, a, b))
    collisions.sort(reverse=True, key=lambda x: x[0])
    if not collisions:
        print("   none above threshold")
    for j, a, b in collisions[:12]:
        print(f"   {j:.0%}  '{a['name']}'  ⟷  '{b['name']}'")

    banner("3. THIN TRIGGERS — description too short to route reliably (<40 chars)")
    thin = [s for s in uniq if s["desc_len"] < 40]
    print(f"   {len(thin)}/{len(uniq)} unique skills have a thin/absent description:")
    for s in thin[:14]:
        why = "no description" if s["desc_len"] == 0 else f"{s['desc_len']} chars"
        print(f"     - {s['name']}  ({why})")

    banner("4. STUB BODIES — trigger present, little/no payload (<120 chars)")
    stubs = [s for s in uniq if s["body_len"] < 120]
    print(f"   {len(stubs)}/{len(uniq)} unique skills are mostly trigger, little body:")
    for s in stubs[:10]:
        print(f"     - {s['name']}  (body ~{s['body_len']} chars)")

    banner("HONEST READ")
    print(f"   {len(skmeta)} skill files -> {len(uniq)} unique. {len(dup_groups)} duplicated, "
          f"{len(collisions)} trigger collisions, {len(thin)} thin triggers, {len(stubs)} stubs.")
    print("   Real dead weight to merge/sharpen/retire — computed on your own library,\n"
          "   no ground truth. Same battery that grades retrieved memory, aimed at skills.\n")


if __name__ == "__main__":
    main()
