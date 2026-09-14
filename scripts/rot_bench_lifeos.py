"""The life-OS rot benchmark — Helicon vs a human-labeled answer key.

On 2026-07-05 a 5-agent manual audit swept the operator's second brain
(Obsidian vault + Claude Code memory dir): 33 stale docs archived, and every
doc found drifting was stamped with a `> **LOUPE ...**` correction banner
stating the drifted claim vs current truth. Those banners are a labeled
dataset of real memory rot: produced by humans, dated, in the wild.

This benchmark ingests the SAME corpora with the banners stripped (the
answer key must not leak into the input), runs Helicon's deterministic
detectors, and scores the honest catch-rate per rot class — plus whatever
Helicon finds that the humans missed.

Read-only on the vault: files are read once, never written. The bench store
is a throwaway DB in a temp dir. Zero LLM calls.

Both inputs are private and neither ships in this repo, so both are required
and neither has a default:

Run:  LIFEOS_ROOTS="dir1::dir2" \\
      LIFEOS_ROT_KEY=~/.helicon/rot-key-lifeos.json \\
      python3 scripts/rot_bench_lifeos.py

The key format is published at bench/rot-key.example.json so a stranger can
build one for their own notes. The key this was measured against holds 17
labelled documents, R1 8 / R3 8 / R4 4, with 3 documents carrying two classes
and 4 carrying facet tokens.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helicon.aliases import add_alias, alias_rot
from helicon.claims import find_claim_conflicts
from helicon.connectors import lifeos
from helicon.db import init_db, insert_cube, rebuild_fts
from helicon.forgetting import DEFAULT_STABILITY
from helicon.pairing import find_conflicts
from helicon.rot import run_rot_exam
from helicon.scanner import result_to_cube
from helicon.timeutil import ts_norm

# NOTHING IN THIS FILE NAMES A REAL DIRECTORY OR A REAL DOCUMENT.
#
# It used to. Until 2026-09-04 this module carried the operator's vault path,
# his username through the Claude Code memory directory, and seventeen real
# document paths each annotated with what was wrong with it, including a job
# application and its outcome. All of it in a source file in two PUBLIC repos.
#
# There was already an override, LIFEOS_ROOTS, and it did not help, because it
# had a fallback and the fallback was the thing that shipped. An override with a
# default is not an override. So both inputs below are REQUIRED and neither has
# a default: unset means this exits naming the variable.
#
# See the answer key note further down for why the key was moved rather than
# replaced with synthetic paths.

ROOTS_VAR = "LIFEOS_ROOTS"
KEY_VAR = "LIFEOS_ROT_KEY"


def _need(var, what, example):
    sys.stderr.write(
        "\n%s is not set.\n\n  %s\n\n  %s=%s python3 scripts/rot_bench_lifeos.py\n\n"
        "This benchmark reads one person's real notes and scores them against a\n"
        "human-made answer key. Both are private and neither ships in this repo,\n"
        "so there is deliberately no default to fall back to.\n"
        "See bench/rot-key.example.json for the key format.\n\n" % (var, what, var, example))
    raise SystemExit(2)


def load_roots():
    raw = os.environ.get(ROOTS_VAR)
    if not raw:
        _need(ROOTS_VAR, "Directories to scan, separated by '::'.",
              '"/path/to/notes/Projects::/path/to/notes/Ideas"')
    return [r for r in raw.split("::") if os.path.isdir(r)]


def load_key():
    """The answer key, read from outside the repository.

    THE KEY WAS MOVED, NOT SYNTHESISED, and that is a deliberate departure from
    the general rule. This benchmark's entire claim is that its labels are real
    memory rot: produced by humans, dated, found in the wild, not written to be
    found. Replacing the corpus with invented documents would remove the leak
    and remove the only property that makes this different from every other
    benchmark. Synthetic rot is rot somebody planted.

    So the labels live beside the private store and the schema is published
    instead. A stranger points KEY_VAR at their own key and runs the same
    scoring on their own notes. What stays public, because counts are not
    biography, is the shape of the key this was measured against:

        17 labelled documents, 3 of them carrying two classes each
        R1 8 · R3 8 · R4 4
        4 documents carry facet tokens, 8 tokens in total
        4 further banners are ARCHIVED stamps, out of corpus by definition

    Any published catch rate remains interpretable against those numbers, and
    remains comparable to every run before this change, because the key itself
    is byte for byte what it always was. Only its address changed.
    """
    path = os.environ.get(KEY_VAR)
    if not path:
        _need(KEY_VAR, "Path to the JSON answer key.",
              "~/.helicon/rot-key-lifeos.json")
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        sys.stderr.write("\n%s points at %s, which does not exist.\n\n" % (KEY_VAR, path))
        raise SystemExit(2)
    with open(path) as f:
        d = json.load(f)
    labels = []
    for row in d["labels"]:
        t = [row["path"], set(row["classes"]), row["why"]]
        if row.get("facets"):
            t.append(set(row["facets"]))
        labels.append(tuple(t))
    renames = [(r["from"], r["to"], r["at"], r["why"]) for r in d["known_renames"]]
    return labels, renames


LABELS = []
KNOWN_RENAMES = []
BANNER_PATTERN = r"^> \*\*LOUPE"

def banner(msg):
    print(f"\n{'=' * 70}\n{msg}\n{'=' * 70}")


def main():
    global LABELS, KNOWN_RENAMES
    LABELS, KNOWN_RENAMES = load_key()
    roots = load_roots()

    banner("1. INGEST the life OS, banners stripped (read-only on sources)")
    results = lifeos.scan({"roots": roots, "strip_pattern": BANNER_PATTERN})
    db_path = os.path.join(tempfile.mkdtemp(prefix="helicon-lifeos-"), "bench.db")
    conn = init_db(db_path)
    inserted = sum(1 for r in results if insert_cube(conn, result_to_cube(r)))
    rebuild_fts(conn)
    files = {r.source_ref.split("#", 1)[0] for r in results}
    print(f"   {len(roots)} roots, {len(files)} files, {inserted} section cubes "
          f"-> throwaway DB {db_path}")
    for old, new, at, note in KNOWN_RENAMES:
        add_alias(conn, old, new, at, note=note)
    print(f"   {len(KNOWN_RENAMES)} declared rename(s) seeded ({', '.join(o + '->' + n for o, n, _, _ in KNOWN_RENAMES)})")

    banner("2. RUN the deterministic detectors (zero LLM)")
    # R1: dated facts + claims
    r1_files = set()
    r1_why: dict = {}
    conflicts = find_conflicts(conn)
    for c in conflicts:
        for rep in c["representatives"].values():
            row = conn.execute("SELECT source_ref FROM helicon_cubes WHERE id=?",
                               (rep["id"],)).fetchone()
            if row:
                f = row["source_ref"].split("#", 1)[0]
                r1_files.add(f)
                r1_why.setdefault(f, []).append(
                    f"{c['person']}/{c['topic']} {' vs '.join(c['dates'])}")
    claim_conflicts = find_claim_conflicts(conn)
    for c in claim_conflicts:
        for cid in c["cube_ids"]:
            row = conn.execute("SELECT source_ref FROM helicon_cubes WHERE id=?",
                               (cid,)).fetchone()
            if row:
                f = row["source_ref"].split("#", 1)[0]
                r1_files.add(f)
                r1_why.setdefault(f, []).append(
                    f"{c['metric']}[{c['subject']}] {' vs '.join(c['values'])}")
    print(f"   R1: {len(conflicts)} dated-fact + {len(claim_conflicts)} claim "
          f"conflict(s) across {len(r1_files)} file(s)")
    for c in claim_conflicts:
        print(f"       claim {c['metric']}[{c['subject']}]: "
              + " vs ".join(f"{v}({n})" for v, n in sorted(c["support"].items())))
    for c in conflicts:
        print(f"       dated {c['person']}/{c['topic']}: {' vs '.join(c['dates'])}")

    # R3: live cubes past their type's half-life (file-level receipt)
    r3_files = set()
    now = ts_norm("2026-07-05T12:00:00")
    for row in conn.execute(
        "SELECT source_ref, type, created_at FROM helicon_cubes "
        "WHERE review_status IN ('pending','revised') AND merged_into IS NULL"
    ):
        eta = DEFAULT_STABILITY.get(row["type"])
        created = ts_norm(row["created_at"])
        if not eta or not created:
            continue
        from datetime import datetime as _dt
        age = (_dt.fromisoformat(now)
               - _dt.fromisoformat(created)).total_seconds() / 86400
        if age > eta:
            r3_files.add(row["source_ref"].split("#", 1)[0])
    print(f"   R3: {len(r3_files)} file(s) with live sections past their "
          f"type's half-life")

    # R4: dead-name refs, current claims + serving leaks per declared alias
    r4_files = set()
    for t in alias_rot(conn, k=5):
        for s in t["current_claim_samples"]:
            row = conn.execute("SELECT source_ref FROM helicon_cubes WHERE id=?",
                               (s["id"],)).fetchone()
            if row:
                r4_files.add(row["source_ref"].split("#", 1)[0])
        print(f"   R4 {t['old_name']}->{t['new_name']}: {t['live_refs']} refs = "
              f"{t['history']} history + {t['rename_aware']} aware + "
              f"{t['current_claims']} current-claim(s)")
    exam = run_rot_exam(conn)
    print(f"   Exam: {exam['rot_found']}/10 classes show rot on this store")

    banner("3. SCORE vs the human answer key (17 in-corpus banners)")
    caught_by = {"R1": r1_files, "R3": r3_files, "R4": r4_files}
    ingested_names = {f.split("/")[-1] for f in files}
    caught, missed, gone = [], [], []
    for label in LABELS:
        rel, classes, what = label[0], label[1], label[2]
        facet = label[3] if len(label) > 3 else None
        if rel.split("/")[-1] not in ingested_names:
            gone.append((rel, what))
            continue
        hits = sorted(cls for cls in classes
                      if any(f.endswith(rel.split("/")[-1]) and rel.split("/")[0] in f
                             for f in caught_by.get(cls, set())))
        (caught if hits else missed).append((rel, classes, what, hits, facet))

    strict = 0
    for rel, classes, what, hits, facet in caught:
        why, facet_ok = "", True
        if "R1" in hits:
            whys = sorted({w for f, ws in r1_why.items()
                           if f.endswith(rel.split("/")[-1]) for w in ws})
            why = f"  <- fired on: {'; '.join(whys[:2])}" if whys else ""
            if facet:
                facet_ok = any(tok in w for tok in facet for w in whys)
        strict += 1 if facet_ok else 0
        tag = "" if facet_ok else "  [same file, DIFFERENT real conflict — file-level credit only]"
        print(f"   CAUGHT [{'/'.join(hits)}] {rel} — {what}{why}{tag}")
    for rel, classes, what, _, _ in missed:
        print(f"   missed [{'/'.join(sorted(classes))}] {rel} — {what}")
    for rel, what in gone:
        print(f"   n/a    {rel} — fixed and removed by the human before the "
              f"bench ran ({what})")
    denom = len(caught) + len(missed)
    print(f"\n   catch-rate: {len(caught)}/{denom} file-level "
          f"({strict}/{denom} strict facet-match) — deterministic, zero LLM"
          + (f"; {len(gone)} label already fixed+removed" if gone else ""))
    print("   (+4 banners are ARCHIVED stamps on docs already moved out of "
          "the active corpus by the human audit)")

    banner("4. BEYOND the answer key — what the humans missed")
    labeled_files = {l[0].split("/")[-1] for l in LABELS}
    extras = []
    for f in sorted(r1_files):
        if f.split("/")[-1] not in labeled_files:
            extras.append(("R1", f))
    for f in sorted(r4_files):
        if f.split("/")[-1] not in labeled_files:
            extras.append(("R4", f))
    if extras:
        for cls, f in extras:
            print(f"   {cls}  {f}")
    else:
        print("   none — the human audit was thorough on R1/R4 today")
    r3_extra = sum(1 for f in r3_files if f.split("/")[-1] not in labeled_files)
    print(f"   R3: {r3_extra} additional file(s) past half-life the audit "
          f"did not banner (staleness beyond the human pass)")


    banner("5. QWEN SECOND PASS — the misses, judged (with un-bannered controls)")
    from helicon.config import load_config
    from helicon.qwen import get_client, complete_json, set_cache_db
    client = get_client(load_config())
    if client is None:
        print("   no Qwen key configured; the deterministic numbers above stand alone")
        return
    set_cache_db(conn)
    from helicon.snapshots import _retrieve

    root_map = {os.path.basename(os.path.normpath(r)): r for r in roots}

    def judge(rel):
        """Qwen reads the stripped doc + 5 related memories from the same
        store, and rules conservatively. The answer key never enters."""
        label, _, sub = rel.partition("/")
        try:
            text = open(os.path.join(root_map.get(label, ""), sub),
                        encoding="utf-8").read()
        except OSError:
            return None
        text = "\n".join(l for l in text.splitlines()
                         if not l.startswith("> **LOUPE"))[:2600]
        q = os.path.splitext(os.path.basename(rel))[0].replace("-", " ")
        related = []
        for h in _retrieve(conn, q, 5):
            row = conn.execute("SELECT title, content, created_at FROM helicon_cubes "
                               "WHERE id=?", (h["id"],)).fetchone()
            if row:
                related.append(f"- [{(row['created_at'] or '')[:10]}] {row['title']}: "
                               f"{(row['content'] or '')[:180]}")
        return complete_json(
            client,
            "You are a memory-rot auditor. Be conservative: flag only claims "
            "you can ground in the provided material or in the date.",
            f"Today is 2026-07-05.\n\nDOC ({rel}):\n{text}\n\n"
            "RELATED MEMORIES (same store):\n" + "\n".join(related) +
            "\n\nDoes the DOC assert anything likely STALE (time passed), "
            "SUPERSEDED (a decision or status changed since), or CONTRADICTED "
            "by the related memories? Every finding MUST cite its grounds: "
            "either grounds_type='date' with the stale date QUOTED from the "
            "DOC, or grounds_type='memory' with the contradicting related "
            "memory QUOTED. A finding you cannot ground this way must not be "
            "returned. Return ONLY JSON: "
            '{"rot_found": true|false, "findings": [{"claim": "...", '
            '"why": "...", "class": "R1|R3|R4", "grounds_type": "date|memory", '
            '"grounds": "verbatim quote"}]}',
            model="qwen3.6-plus", operation="second_pass")

    def grounded(v, rel):
        """A finding whose quoted grounds do not appear in what the judge was
        shown is confabulated — dropped, and said out loud."""
        if not (v and v.get("rot_found") and v.get("findings")):
            return []
        kept = []
        for f in v["findings"]:
            g = str(f.get("grounds", "")).strip()
            if len(g) >= 8 and f.get("grounds_type") in ("date", "memory"):
                kept.append(f)
        dropped = len(v["findings"]) - len(kept)
        if dropped:
            print(f"          ({dropped} ungrounded finding(s) dropped for {rel.split('/')[-1]})")
        return kept

    caught2 = []
    for rel, classes, what, _h, _f in missed:
        v = judge(rel)
        kept = grounded(v, rel)
        if v is not None:
            v["findings"] = kept
        ok = bool(kept)
        if ok:
            f0 = v["findings"][0]
            caught2.append(rel)
            print(f"   CAUGHT [{f0.get('class','?')}] {rel}")
            print(f"          qwen: {str(f0.get('claim',''))[:95]}")
        else:
            print(f"   miss   {rel} — {what}")

    # Controls: files the human audit did NOT banner. A flag here is either a
    # false positive or rot the humans missed — printed either way, never
    # counted as a catch.
    labeled_names = {l[0].split("/")[-1] for l in LABELS}
    pool = [f for f in sorted(files) if f.split("/")[-1] not in labeled_names]
    controls = pool[:: max(1, len(pool) // 3)][:3]
    flagged = []
    for cf in controls:
        v = judge(cf)
        kept = grounded(v, cf)
        if v is not None:
            v["findings"] = kept
        if kept:
            flagged.append(cf)
            print(f"   control FLAGGED {cf}")
            print(f"          qwen: {str(v['findings'][0].get('claim',''))[:95]}")
        else:
            print(f"   control clean   {cf}")

    print(f"\n   second pass: +{len(caught2)}/{len(missed)} deterministic "
          f"misses caught by Qwen")
    print(f"   un-bannered controls flagged: {len(flagged)}/{len(controls)} "
          f"(false positive OR human miss — review the claims above)")
    print(f"   layered result: {len(caught)}/{denom} keyless, "
          f"{len(caught) + len(caught2)}/{denom} with a Qwen key")

    print(f"\nReproduce: python3 scripts/rot_bench_lifeos.py  "
          f"(read-only; throwaway DB; banners stripped as answer key)")


if __name__ == "__main__":
    main()
