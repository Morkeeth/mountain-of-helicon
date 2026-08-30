"""R16 version/framework claim vs manifest — deterministic, no execution."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helicon.versions import check_versions, CONTRADICTED, UPHELD, UNVERIFIABLE


def _repo(files: dict) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        if os.path.dirname(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


def _v(res, verdict):
    return [r for r in res["receipts"] if r["verdict"] == verdict]


def test_react_major_mismatch_is_contradicted():
    d = _repo({
        "package.json": json.dumps({"dependencies": {"react": "^19.0.0"}}),
        "CLAUDE.md": "We use React 18 on the frontend.\n",
    })
    res = check_versions(d)
    assert res["verdict"] == "ROT FOUND", res
    con = _v(res, CONTRADICTED)
    assert len(con) == 1 and "19" in con[0]["receipt"], res


def test_react_major_match_is_upheld():
    d = _repo({
        "package.json": json.dumps({"dependencies": {"react": "^18.2.0"}}),
        "CLAUDE.md": "We use React 18.\n",
    })
    res = check_versions(d)
    assert res["verdict"] == "CLEAN" and _v(res, UPHELD), res


def test_python_version_mismatch_via_python_version_file():
    d = _repo({".python-version": "3.11.6\n",
               "CLAUDE.md": "Runs on Python 3.12.\n"})
    res = check_versions(d)
    assert res["verdict"] == "ROT FOUND", res
    assert "3.11" in _v(res, CONTRADICTED)[0]["receipt"]


def test_python_requires_range_match_is_upheld():
    d = _repo({"pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
               "CLAUDE.md": "Python 3.11 required.\n"})
    res = check_versions(d)
    assert _v(res, UPHELD), res


def test_node_nvmrc_mismatch():
    d = _repo({".nvmrc": "20\n", "AGENTS.md": "Node 18 in CI.\n"})
    res = check_versions(d)
    assert res["verdict"] == "ROT FOUND" and "20" in _v(res, CONTRADICTED)[0]["receipt"], res


def test_no_manifest_is_unverifiable_not_a_false_alarm():
    d = _repo({"CLAUDE.md": "We use React 18 and Python 3.11.\n"})
    res = check_versions(d)
    assert res["verdict"] == "UNMEASURED", res     # nothing to grade against
    assert len(_v(res, UNVERIFIABLE)) == 2


def test_negated_version_claim_is_skipped():
    d = _repo({
        "package.json": json.dumps({"dependencies": {"react": "^18.0.0"}}),
        "CLAUDE.md": "We no longer use React 17.\n",
    })
    res = check_versions(d)
    assert res["checked"] == 0, res                # negated mention not graded


if __name__ == "__main__":
    fns = [x for k, x in sorted(globals().items()) if k.startswith("test_") and callable(x)]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
