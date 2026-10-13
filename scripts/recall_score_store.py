"""Score a frozen question set against what `helicon_ask` gives an agent.

For each question it calls the MCP tool handler the way an agent does, drops the
echoed question, and looks for the gold tokens in the rest. `gold_any` needs one
token, `gold_all` needs every token. Retrieval level only: no answer model.

It records booleans per question. It never prints or stores a retrieved text.

    python scripts/recall_score_store.py QUESTIONS.json --db STORE.db [--out FILE]

Point --db at a copy of a store. A retrieve writes usage rows to the store it reads.
"""
import argparse
import datetime
import hashlib
import json
import os
import sqlite3


def score(questions_path, db_path, limit=10):
    from helicon.mcp_server import handle_tool_call

    blob = open(questions_path, "rb").read()
    questions = json.loads(blob)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    results = []
    for q in questions:
        answer = json.loads(handle_tool_call("helicon_ask", {"question": q["question"], "limit": limit}, conn))
        answer.pop("task", None)
        text = json.dumps(answer, ensure_ascii=False).lower()
        if q.get("gold_all"):
            right = all(t.lower() in text for t in q["gold_all"])
        else:
            right = any(t.lower() in text for t in q.get("gold_any", []))
        results.append({"id": q["id"], "split": q["split"], "category": q["category"], "right": right,
                        "memories": len(answer.get("safe_context", [])),
                        "rulings": len(answer.get("dated_rulings", []))})
    conn.close()
    return {
        "at": datetime.datetime.now().astimezone().isoformat(),
        "questions_sha256": hashlib.sha256(blob).hexdigest(),
        "scoring": "gold token in the helicon_ask JSON answer, echoed question removed; no answer model",
        "score": sum(r["right"] for r in results),
        "of": len(results),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("questions")
    parser.add_argument("--db", required=True, help="a COPY of a store; the retrieve writes usage rows")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--condition", default="")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    report = score(os.path.expanduser(args.questions), os.path.expanduser(args.db), args.limit)
    report["condition"] = args.condition
    for r in report["results"]:
        print(r["id"], r["split"], r["category"], "RIGHT" if r["right"] else "-")
    by = {}
    for r in report["results"]:
        by.setdefault(r["split"], []).append(r["right"])
    print(f"right: {report['score']} of {report['of']} | " + " | ".join(f"{k} {sum(v)} of {len(v)}" for k, v in sorted(by.items())))
    if args.out:
        with open(os.path.expanduser(args.out), "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)


if __name__ == "__main__":
    main()
