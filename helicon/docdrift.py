"""Doc-drift check: README claims vs source truth.

The dogfood lens pointed at our own docs. On Jul 4 a manual audit caught this
repo's README claiming 8 MCP tools while source had 11, plus a dead deploy
story and three stale counts. This makes that check reproducible: numeric
claims in README.md are parsed and compared against counts computed from the
package source. Wired into the test suite, so stale docs literally fail the
build. Run standalone: python3 -m helicon.docdrift
"""
import os
import re

PKG_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.dirname(PKG_DIR)


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


CLAIMS = [
    # (label, README regex with one capture group, source-truth counter)
    ("MCP tools", r"MCP Server \((\d+) tools\)", count_mcp_tools),
    ("CLI commands", r"CLI \((\d+) commands\)", count_cli_commands),
    ("DB tables", r"\((\d+) tables\)", count_tables),
    ("API endpoints", r"\((\d+) endpoints\)", count_endpoints),
]


def check_readme(repo_root: str = REPO_ROOT) -> list[dict]:
    readme = open(os.path.join(repo_root, "README.md")).read()
    results = []
    for label, pattern, counter in CLAIMS:
        m = re.search(pattern, readme)
        claimed = int(m.group(1)) if m else None
        actual = counter()
        results.append({
            "claim": label,
            "readme": claimed,
            "source": actual,
            "ok": claimed == actual,
            "why": ("claim not found in README" if claimed is None
                    else "match" if claimed == actual
                    else f"README says {claimed}, source has {actual}"),
        })
    return results


def main():
    results = check_readme()
    drifted = [r for r in results if not r["ok"]]
    print("Doc-drift check: README.md claims vs source truth\n")
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"  [{mark}] {r['claim']:<14} README: {r['readme']}  source: {r['source']}  ({r['why']})")
    if drifted:
        print(f"\n{len(drifted)} claim(s) drifted. The README is memory too — fix it.")
        raise SystemExit(1)
    print("\nREADME matches source.")


if __name__ == "__main__":
    main()
