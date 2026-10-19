"""Score a frozen ruling-recall question set against the dated rulings reader.

This is the 7 Oct 2026 scorer, kept as a file. A question holds `ruling_index`, the
position of its gold ruling among the rows of the log that carry a text. The gold row
is resolved from the raw log, private rows included, so the index stays exact. The
reader is then asked the question the way `helicon ask` asks it.

Per question it records booleans only. It never prints or stores a ruling text.

    python scripts/recall_score.py QUESTIONS.json [--rulings LOG] [--out FILE] [--include-private]
"""
import argparse
import datetime
import hashlib
import inspect
import json
import os

from helicon import dated_rulings


def score(questions_path, rulings_file=None, include_private=False):
    blob = open(questions_path, "rb").read()
    questions = json.loads(blob)
    path = rulings_file or dated_rulings.rulings_path()
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    rows = [r for r in rows if isinstance(r, dict) and r.get("text")]
    kwargs = {}
    if "include_private" in inspect.signature(dated_rulings.load_rulings).parameters:
        kwargs["include_private"] = include_private
    rulings = dated_rulings.load_rulings(path, **kwargs)
    # The private rows, weighed and never shown, as the agent path holds them.
    hidden = {}
    if not include_private and hasattr(dated_rulings, "load_hidden"):
        hidden = {"hidden": dated_rulings.load_hidden(path)}
    results = []
    for q in questions:
        gold_row = rows[q["ruling_index"]]
        gold = gold_row["text"]
        got = dated_rulings.match_rulings(q["question"], rulings=rulings, limit=3, **hidden)
        current = [g for g in got if g["standing"] == "current"]
        results.append({
            "id": q["id"],
            "split": q["split"],
            "gold_is_private": gold_row.get("private") is True,
            "returned": any(g["text"] == gold for g in got),
            "current": any(g["text"] == gold for g in current),
            "current_row_holds_answer_word": any(
                any(t in (g["text"] + g["quote"]).lower() for t in q["gold_any"]) for g in current),
            "other_current": sum(1 for g in current if g["text"] != gold),
            "possibly_superseded": sum(1 for g in got if g["standing"] == "possibly_superseded"),
        })
    return {
        "at": datetime.datetime.now().astimezone().isoformat(),
        "questions_sha256": hashlib.sha256(blob).hexdigest(),
        "rulings_sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
        "rulings_with_text": len(rows),
        "rulings_read": len(rulings),
        "include_private": include_private,
        "scoring": "gold = the ruling the question was written from is returned and marked current (limit 3)",
        "score": sum(r["current"] for r in results),
        "of": len(results),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("questions")
    parser.add_argument("--rulings", default=None, help="ruling log to read (default: HELICON_RULINGS_FILE or the fleet log)")
    parser.add_argument("--out", default=None, help="write the full result as JSON")
    parser.add_argument("--include-private", action="store_true", help="operator-only: score with private rows readable")
    args = parser.parse_args()
    report = score(os.path.expanduser(args.questions), args.rulings and os.path.expanduser(args.rulings), args.include_private)
    for r in report["results"]:
        print(r["id"], r["split"], "RET" if r["returned"] else "-  ", "CUR" if r["current"] else "-  ",
              "PRIVATE-GOLD" if r["gold_is_private"] else "",
              f"NEWER-HIDDEN x{r['possibly_superseded']}" if r["possibly_superseded"] else "")
    print(f"gold is current: {report['score']} of {report['of']} | returned {sum(r['returned'] for r in report['results'])}"
          f" | rulings read {report['rulings_read']} of {report['rulings_with_text']}")
    if args.out:
        with open(os.path.expanduser(args.out), "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)


if __name__ == "__main__":
    main()
