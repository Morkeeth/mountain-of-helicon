"""Score both frozen sets against a read-only copy of the live store, embeddings present.

The live store is opened read only and copied into memory with the SQLite backup
call. Nothing is written to it or to disk. Set 2 is scored in three conditions:

    A  the copy as it is
    B  A plus the cubes of the setup-rules and learnings connectors, not embedded
    C  B plus embeddings for those new cubes

Each question text goes once to the configured embedding endpoint, as every live
`helicon ask` does. The vectors are cached across the conditions.

It prints ids, booleans and counts. It never prints a retrieved text or a ruling.

    python scripts/recall_score_live.py --db ~/.helicon/helicon.db --set1 Q1.json --set2 Q2.json \\
        --rulings LOG --claude-home ~/.claude --learnings FILE [--out FILE]
"""
import argparse
import json
import os
import sqlite3


def memory_copy(db_path):
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn = sqlite3.connect(":memory:")
    source.backup(conn)
    source.close()
    conn.row_factory = sqlite3.Row
    return conn


def ask(conn, question, limit=10):
    from helicon.mcp_server import handle_tool_call

    answer = json.loads(handle_tool_call("helicon_ask", {"question": question, "limit": limit}, conn))
    answer.pop("task", None)
    return answer


def score_set2(conn, questions):
    right = {}
    for q in questions:
        text = json.dumps(ask(conn, q["question"]), ensure_ascii=False).lower()
        right[q["id"]] = (all(t.lower() in text for t in q["gold_all"]) if q.get("gold_all")
                          else any(t.lower() in text for t in q.get("gold_any", [])))
    return right


def score_set1(conn, questions, rulings_file):
    rows = [json.loads(line) for line in open(rulings_file, encoding="utf-8") if line.strip()]
    rows = [r for r in rows if isinstance(r, dict) and r.get("text")]
    right = {}
    for q in questions:
        gold = rows[q["ruling_index"]]["text"]
        got = ask(conn, q["question"]).get("dated_rulings", [])
        right[q["id"]] = any(g["text"] == gold and g["standing"] == "current" for g in got)
    return right


def add_cubes(conn, claude_home, learnings):
    from helicon.connectors import learnings as learnings_connector
    from helicon.connectors import setup_rules
    from helicon.db import insert_cube
    from helicon.scanner import result_to_cube

    found = setup_rules.scan({"claude_home": claude_home}) + learnings_connector.scan({"files": [learnings]})
    ids = []
    for result in found:
        cube = result_to_cube(result)
        if insert_cube(conn, cube):
            ids.append(cube.id)
    conn.commit()
    return ids


def embed(conn, ids):
    from helicon.embeddings import embed_batch, store_embedding

    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    cubes = conn.execute(f"SELECT id, title, content FROM helicon_cubes WHERE id IN ({marks})", ids).fetchall()
    for start in range(0, len(cubes), 64):
        batch = cubes[start:start + 64]
        vectors = embed_batch([f"{c['title']} {(c['content'] or '')[:500]}" for c in batch])
        for cube, vector in zip(batch, vectors):
            store_embedding(conn, cube["id"], vector)
    conn.commit()
    return len(cubes)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--set1")
    parser.add_argument("--set2", action="append", default=[], help="a set scored by gold tokens; repeat for more")
    parser.add_argument("--rulings", required=True)
    parser.add_argument("--claude-home", default="~/.claude")
    parser.add_argument("--learnings", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    os.environ["HELICON_RULINGS_FILE"] = os.path.expanduser(args.rulings)

    from helicon import embeddings

    cache, calls, plain = {}, [0], embeddings.embed_text

    def cached(text):
        if text not in cache:
            calls[0] += 1
            cache[text] = plain(text)
        return cache[text]

    embeddings.embed_text = cached
    conn = memory_copy(os.path.expanduser(args.db))
    stats = embeddings.get_embedding_stats(conn)
    report = {"embedded_cubes": stats.get("embedded"), "cubes": conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]}
    print("store copy in memory:", report)
    sets = {os.path.basename(os.path.dirname(os.path.abspath(p))) + "/" + os.path.basename(p): json.load(open(os.path.expanduser(p))) for p in args.set2}

    def run(label):
        for name, questions in sets.items():
            right = score_set2(conn, questions)
            report[f"{label} {name}"] = right
            print(label, name, sum(right.values()), "of", len(right), "| wrong:", " ".join(k for k, v in right.items() if not v))

    if args.set1:
        right = score_set1(conn, json.load(open(os.path.expanduser(args.set1))), os.environ["HELICON_RULINGS_FILE"])
        report["set1"] = right
        print("set 1, gold ruling is current:", sum(right.values()), "of", len(right), "| wrong:", " ".join(k for k, v in right.items() if not v))
    run("A")
    ids = add_cubes(conn, os.path.expanduser(args.claude_home), os.path.expanduser(args.learnings))
    print("cubes added to the copy:", len(ids))
    run("B")
    print("new cubes embedded:", embed(conn, ids))
    run("C")
    report["query_embedding_calls"] = calls[0]
    print("query embedding calls:", calls[0])
    if args.out:
        with open(os.path.expanduser(args.out), "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)


if __name__ == "__main__":
    main()
