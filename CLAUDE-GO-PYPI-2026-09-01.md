# GO · Helicon 0.2.0 PyPI — paste to Claude

You have the PyPI token. Oscar does not in Cursor. Run in `~/CODE/mountain-of-helicon`.

## Pre-flight (must pass)

```bash
cd ~/CODE/mountain-of-helicon
git pull --ff-only origin main
python3 scripts/launch_check.py   # expect: READY
python3 -m twine check dist/mountain_of_helicon-0.2.0-py3-none-any.whl   # expect: PASSED
```

## Publish

```bash
cd ~/CODE/mountain-of-helicon
export TWINE_USERNAME=__token__
export TWINE_PASSWORD='<your PyPI token>'
python3 -m twine upload dist/mountain_of_helicon-0.2.0-py3-none-any.whl
```

If wheel is stale, rebuild first:

```bash
python3 -m build --wheel
python3 -m twine check dist/mountain_of_helicon-0.2.0-py3-none-any.whl
# then upload
```

## Done-when (paste output back)

```bash
curl -s https://pypi.org/pypi/mountain-of-helicon/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
# expect: 0.2.0

python3 -m venv /tmp/hstranger && /tmp/hstranger/bin/pip install -q mountain-of-helicon==0.2.0
/tmp/hstranger/bin/helicon truth ~/.claude --top 3
# expect: EXIT=0, ranked report
```

## Do NOT

- touch `MorkeethHQ/mount-helicon`
- bump version
- deploy anything else

## Receipt

One line in chat: PyPI version + cold-install EXIT code.

---

**Transcripto:** PyPI already **0.1.3** — skip publish. X post only if Oscar asks: `~/CODE/fleet-ops/gtm/transcripto-launch-post.md` Option A.
