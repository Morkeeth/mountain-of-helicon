# Helicon launch receipt · 1 Sep 2026 (IDE night)

**Repo:** Morkeeth/mountain-of-helicon · `main`  
**Lane:** IDE (harness `mount-helicon` blocked — work on product repo)

## Gates

```text
$ python3 scripts/launch_check.py
READY: source-controlled gates pass.

$ python3 -m pytest tests/test_launch_contract.py tests/test_new_user_onboarding.py tests/test_python_version_gate.py -q
18 passed
```

## Shipped tonight

| Item | Path |
|------|------|
| DEMO.md restored | `DEMO.md` |
| CLAUDE.md launch-surface clean | `CLAUDE.md` |
| BYOK rerank doctor fix | `helicon/embeddings.py` |
| Release notes | `RELEASE-NOTES-0.2.0.md` |
| Subtraction ruling | `docs/SUBTRACTION-MEMO.md` |

## Oscar gate

```bash
cd ~/CODE/mountain-of-helicon && python3 -m twine upload dist/mountain_of_helicon-0.2.0-py3-none-any.whl
```

**Do not run until release notes read.**

## Verdict

✅ Launch-ready on disk · ⚠️ PyPI publish is Oscar-only
