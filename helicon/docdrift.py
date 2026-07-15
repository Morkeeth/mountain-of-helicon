"""Doc-drift check: doc claims vs source truth.

The dogfood lens pointed at our own docs. On Jul 4 a manual audit caught this
repo's README claiming 8 MCP tools while source had 11. This makes that check
reproducible: claims in the docs are parsed and compared against counts computed
from the package source. Wired into the test suite, so stale docs literally fail
the build. Run standalone: python3 -m helicon.docdrift

Three shapes of drift, because v1 only caught the first and the other two shipped
past it anyway (found by the Jul 15 audit):

  COUNT — a number in prose vs a count computed from source. v1 did this, for
          four claims, in README only. It passed while CLAUDE.md sat four
          numbers out of date, because nothing ever read CLAUDE.md.
  LIST  — a declared count vs the length of the list right beneath it. v1 read
          the headline and never the table, so "MCP Server (14 tools)" sat on
          top of a 12-row table and passed. A count and its own list are two
          separate claims and both are checked here. This is also how ROT.md's
          12-class catalogue was found rendering only 11 rows.
  EVAL  — a metric in prose vs data/eval-latest.json, read at check time. A
          hardcoded expected value would just be a second copy of the number,
          and a second copy is a second thing to drift. Docs may round: a claim
          is compared at the precision it states, so 0.69 accepts 0.692 and
          0.615 does not accept 0.603.

Deliberately NOT guarded: live cube counts. The store grows on every scan (6,880
to 6,986 during a single audit on Jul 15, with a watch cron every 6h), so an
exact cube count in a doc is stale within the hour and a check on it would fail
the build for no reason. Those claims carry an as-of date and the command that
recomputes them instead of a number this check would have to chase.
"""
import json
import os
import re

PKG_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.dirname(PKG_DIR)

# Number words the docs actually use for class counts ("the ten-class exam").
_WORD_NUMBERS = {
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14,
}
_NUM = r"\d+|" + "|".join(_WORD_NUMBERS)


def _to_int(token: str) -> int:
    return int(token) if token.isdigit() else _WORD_NUMBERS[token.lower()]


# --------------------------------------------------------------------------
# Source-truth counters. Each one answers a claim by counting the real thing.
# --------------------------------------------------------------------------

def count_mcp_tools() -> int:
    from helicon.mcp_server import TOOLS
    return len(TOOLS)


def count_cli_commands() -> int:
    src = open(os.path.join(PKG_DIR, "cli.py")).read()
    return len(set(re.findall(r'sub\.add_parser\(\s*"([a-z-]+)"', src)))


def count_tables() -> int:
    names = set()
    for root, _dirs, files in os.walk(PKG_DIR):
        if "__pycache__" in root:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            src = open(os.path.join(root, f)).read()
            names.update(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", src))
            # virtual FTS tables are an index, not a table a README would count
    return len(names)


def count_endpoints() -> int:
    n = 0
    api_dir = os.path.join(PKG_DIR, "api")
    for f in os.listdir(api_dir):
        if f.endswith(".py"):
            src = open(os.path.join(api_dir, f)).read()
            n += len(re.findall(r"@(?:router|app)\.(?:get|post|put|delete)\(", src))
    return n


def count_routers() -> int:
    n = 0
    api_dir = os.path.join(PKG_DIR, "api")
    for f in os.listdir(api_dir):
        if f.endswith(".py"):
            src = open(os.path.join(api_dir, f)).read()
            n += len(re.findall(r"=\s*APIRouter\(", src))
    return n


def count_rot_classes() -> int:
    """R-classes the exam actually runs (rot.py is the source, ROT.md the doc)."""
    src = open(os.path.join(PKG_DIR, "rot.py")).read()
    return len(set(re.findall(r'"(R\d+)"', src)))


def count_web_tabs() -> int:
    app = os.path.join(REPO_ROOT, "web", "src", "App.tsx")
    m = re.search(r"type Tab\s*=\s*([^;]+);", open(app).read())
    return len(set(re.findall(r"'([a-z-]+)'", m.group(1)))) if m else 0


# --------------------------------------------------------------------------
# List extractors. Given the doc text and the match that declared the count,
# return how many items are actually listed beneath it.
# --------------------------------------------------------------------------

def _table_rows(text: str, m: re.Match) -> int:
    """Body rows of the first markdown table after the declaring line."""
    rows, past_separator = 0, False
    for line in text[m.end():].split("\n"):
        s = line.strip()
        if not past_separator:
            if re.fullmatch(r"\|[\s:|-]+\|", s):
                past_separator = True
            continue
        if s.startswith("|") and s.endswith("|"):
            rows += 1
        else:
            break
    return rows


def _backticked_items(text: str, m: re.Match) -> int:
    """`init` `scan` ... items in the first paragraph after the declaring line."""
    rest = text[m.end():].lstrip("\n")
    paragraph = rest.split("\n\n")[0]
    return len(set(re.findall(r"`([a-z][a-z0-9_-]*)`", paragraph)))


def _comma_items(group: int):
    """Items in a comma-separated list captured by `group` of the count regex."""
    def extract(text: str, m: re.Match) -> int:
        return len({s.strip() for s in m.group(group).split(",") if s.strip()})
    return extract


def _line_rows(pattern: str):
    """Lines matching `pattern` anywhere in the doc (a table with no declared count)."""
    def extract(text: str, _m) -> int:
        return len(re.findall(pattern, text, re.M))
    return extract


# --------------------------------------------------------------------------
# The claims. Adding a number to a doc means adding it here.
# --------------------------------------------------------------------------

# (label, doc, regex with one count group, source-truth counter)
COUNT_CLAIMS = [
    ("MCP tools", "README.md", r"MCP Server \((\d+) tools\)", count_mcp_tools),
    ("CLI commands", "README.md", r"CLI \((\d+) commands\)", count_cli_commands),
    ("DB tables", "README.md", r"\((\d+) tables\)", count_tables),
    ("API endpoints", "README.md", r"\((\d+) endpoints\)", count_endpoints),
    ("MCP tools (prose)", "README.md", r"exposes (\d+) tools", count_mcp_tools),
    ("rot classes", "README.md", rf"\b({_NUM})-class (?:rot|deterministic) exam", count_rot_classes),
    ("rot classes", "README.md", rf"\b({_NUM}) documented failure classes", count_rot_classes),

    ("MCP tools", "CLAUDE.md", r"MCP Server \((\d+) tools", count_mcp_tools),
    ("API routers", "CLAUDE.md", r"(\d+) routers", count_routers),
    ("MCP tools (stats)", "CLAUDE.md", r"(\d+) MCP tools", count_mcp_tools),
    ("CLI commands (stats)", "CLAUDE.md", r"(\d+) CLI commands", count_cli_commands),

    ("rot classes", "ARCHITECTURE.md", rf"\b({_NUM}) (?:documented )?failure classes", count_rot_classes),
    ("MCP tools", "ARCHITECTURE.md", r"MCP server<br/>(\d+) tools", count_mcp_tools),
    ("web tabs", "ARCHITECTURE.md", r"Web UI · (\d+) tabs", count_web_tabs),
    ("DB tables", "ARCHITECTURE.md", r"SQLite · (\d+) tables", count_tables),
]

# (label, doc, regex declaring the count or None, list extractor, source counter)
LIST_CLAIMS = [
    # the "says 14, lists 12" bug: headline fixed, table left behind
    ("MCP tools table", "README.md", r"## MCP Server \((\d+) tools\)",
     _table_rows, count_mcp_tools),
    ("CLI commands list", "README.md", r"## CLI \((\d+) commands\)",
     _backticked_items, count_cli_commands),
    ("tables list", "CLAUDE.md", r"\((\d+) tables: ([^)]+)\)",
     _comma_items(2), count_tables),
    ("storage tables list", "ARCHITECTURE.md", r"## Storage \((\d+) core tables \+ FTS5\)",
     _backticked_items, count_tables),
    # no count declared in ROT.md: the source count is the expectation, and the
    # catalogue must render one row per class (it silently rendered 11 of 12)
    ("rot catalogue rows", "ROT.md", None,
     _line_rows(r"^\| R\d+ \|"), count_rot_classes),
]

# (label, doc, regex with one value group, dotted path into data/eval-latest.json)
EVAL_CLAIMS = [
    ("retrieval P@3", "README.md", r"P@3 (\d+\.\d+)",
     "sub_goals.efficient_storage_retrieval.precision_at_3"),
    ("retrieval MRR", "README.md", r"MRR (\d+\.\d+)",
     "sub_goals.efficient_storage_retrieval.mrr"),
    ("decay rank-AUC", "README.md", r"rank-AUC (\d+\.\d+)",
     "sub_goals.timely_forgetting.decay_predicts_human_kills_auc"),
    ("benchmark n", "README.md", r"\(n=(\d+)",
     "sub_goals.efficient_storage_retrieval.query_count"),

    ("retrieval P@3", "CLAUDE.md", r"P@3 (\d+\.\d+)",
     "sub_goals.efficient_storage_retrieval.precision_at_3"),
    ("retrieval MRR", "CLAUDE.md", r"MRR (\d+\.\d+)",
     "sub_goals.efficient_storage_retrieval.mrr"),
    ("decay rank-AUC", "CLAUDE.md", r"rank-AUC (\d+\.\d+)",
     "sub_goals.timely_forgetting.decay_predicts_human_kills_auc"),
    ("benchmark n", "CLAUDE.md", r"\(n=(\d+)",
     "sub_goals.efficient_storage_retrieval.query_count"),
]

EVAL_PATH = os.path.join("data", "eval-latest.json")


def _read_doc(repo_root: str, name: str) -> str:
    return open(os.path.join(repo_root, name)).read()


def _dig(blob: dict, path: str):
    node = blob
    for key in path.split("."):
        node = node[key]
    return node


def _agrees_at_stated_precision(literal: str, actual: float) -> bool:
    """A doc may round honestly: '0.69' accepts 0.692, '0.615' does not accept 0.603."""
    places = len(literal.split(".")[1]) if "." in literal else 0
    tolerance = 0.5 * 10 ** (-places)
    return abs(float(literal) - float(actual)) <= tolerance + 1e-12


def _result(claim, doc, kind, doc_value, source_value, ok, why):
    return {"claim": claim, "doc": doc, "kind": kind, "doc_value": doc_value,
            "source": source_value, "ok": ok, "why": why,
            # back-compat: rot.py R2 and older callers read r["readme"]
            "readme": doc_value}


def check_counts(repo_root: str = REPO_ROOT) -> list[dict]:
    """Every stated number vs the source of truth. All occurrences, not just the first."""
    results = []
    for label, doc, pattern, counter in COUNT_CLAIMS:
        text = _read_doc(repo_root, doc)
        actual = counter()
        found = [_to_int(m.group(1)) for m in re.finditer(pattern, text)]
        if not found:
            results.append(_result(label, doc, "count", None, actual, False,
                                   f"claim not found in {doc}"))
            continue
        wrong = sorted({v for v in found if v != actual})
        results.append(_result(
            label, doc, "count", found[0] if len(set(found)) == 1 else sorted(set(found)),
            actual, not wrong,
            "match" if not wrong
            else f"{doc} says {', '.join(str(v) for v in wrong)}, source has {actual}"))
    return results


def check_lists(repo_root: str = REPO_ROOT) -> list[dict]:
    """A declared count vs the length of the list beneath it, and both vs source."""
    results = []
    for label, doc, pattern, extract, counter in LIST_CLAIMS:
        text = _read_doc(repo_root, doc)
        actual = counter()
        match = None
        if pattern is not None:
            match = re.search(pattern, text)
            if not match:
                results.append(_result(label, doc, "list", None, actual, False,
                                       f"declaring line not found in {doc}"))
                continue
        declared = int(match.group(1)) if match else actual
        listed = extract(text, match)
        problems = []
        if declared != listed:
            problems.append(f"{doc} says {declared}, lists {listed}")
        if listed != actual:
            problems.append(f"list has {listed}, source has {actual}")
        results.append(_result(label, doc, "list", f"{declared} declared / {listed} listed",
                               actual, not problems, "; ".join(problems) or "match"))
    return results


def check_evals(repo_root: str = REPO_ROOT) -> list[dict]:
    """Metrics in prose vs data/eval-latest.json, read now, never a hardcoded copy."""
    results = []
    path = os.path.join(repo_root, EVAL_PATH)
    try:
        blob = json.load(open(path))
    except (OSError, ValueError) as e:
        return [_result("eval numbers", EVAL_PATH, "eval", None, None, False,
                        f"cannot read {EVAL_PATH}: {e}")]
    for label, doc, pattern, json_path in EVAL_CLAIMS:
        text = _read_doc(repo_root, doc)
        try:
            actual = _dig(blob, json_path)
        except KeyError:
            results.append(_result(label, doc, "eval", None, None, False,
                                   f"{json_path} missing from {EVAL_PATH}"))
            continue
        found = [m.group(1) for m in re.finditer(pattern, text)]
        if not found:
            results.append(_result(label, doc, "eval", None, actual, False,
                                   f"claim not found in {doc}"))
            continue
        wrong = [v for v in found if not _agrees_at_stated_precision(v, actual)]
        results.append(_result(
            label, doc, "eval", found[0] if len(set(found)) == 1 else sorted(set(found)),
            actual, not wrong,
            "match" if not wrong
            else f"{doc} says {', '.join(sorted(set(wrong)))}, {EVAL_PATH} has {actual}"))
    return results


def check_docs(repo_root: str = REPO_ROOT) -> list[dict]:
    """Every doc claim this repo knows how to verify."""
    return check_counts(repo_root) + check_lists(repo_root) + check_evals(repo_root)


# Kept for callers that predate CLAUDE.md/list/eval coverage (rot.py R2, tests).
# It now returns every doc claim, so R2 grades the whole docs surface.
def check_readme(repo_root: str = REPO_ROOT) -> list[dict]:
    return check_docs(repo_root)


def main():
    results = check_docs()
    drifted = [r for r in results if not r["ok"]]
    print("Doc-drift check: doc claims vs source truth\n")
    kinds = {"count": "COUNT — stated number vs source",
             "list": "LIST  — declared count vs the list beneath it",
             "eval": f"EVAL  — stated metric vs {EVAL_PATH}"}
    for kind, heading in kinds.items():
        rows = [r for r in results if r["kind"] == kind]
        if not rows:
            continue
        print(f"  {heading}")
        for r in rows:
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"    [{mark}] {r['doc']:<16} {r['claim']:<22} "
                  f"doc: {str(r['doc_value']):<24} source: {r['source']}  ({r['why']})")
        print()
    if drifted:
        print(f"{len(drifted)} claim(s) drifted. The docs are memory too — fix them.")
        raise SystemExit(1)
    print(f"{len(results)} claims checked across "
          f"{len({r['doc'] for r in results})} docs. All match source.")


if __name__ == "__main__":
    main()
