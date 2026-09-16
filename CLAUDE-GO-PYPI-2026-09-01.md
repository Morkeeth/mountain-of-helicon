# GO · Helicon 0.2.0 PyPI — paste to Claude

Oscar owns the PyPI token and the upload action. Run in the product checkout.

## Pre-flight (must pass)

```bash
cd ~/CODE/mountain-of-helicon
git pull --ff-only origin main
python3 scripts/launch_check.py   # expect: READY
python3 -m twine check dist/helicon-0.2.0.tar.gz dist/helicon-0.2.0-py3-none-any.whl
```

## Publish

```bash
cd ~/CODE/mountain-of-helicon
export TWINE_USERNAME=__token__
export TWINE_PASSWORD='<your PyPI token>'
python3 -m twine upload dist/helicon-0.2.0.tar.gz dist/helicon-0.2.0-py3-none-any.whl
```

If wheel is stale, rebuild first:

```bash
bash scripts/build_release.sh
bash scripts/cold_install_check.sh
# then upload
```

## Done-when (paste output back)

```bash
curl -s https://pypi.org/pypi/helicon/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
# expect: 0.2.0

python3 -m venv /tmp/hstranger && /tmp/hstranger/bin/pip install -q helicon==0.2.0
/tmp/hstranger/bin/helicon review /path/to/repo
# expect: a report with exact file and line evidence
```

## Do NOT

- touch `MorkeethHQ/mount-helicon`
- bump version
- deploy anything else

## Receipt

One line in chat: PyPI version + cold-install EXIT code.

---

**Transcripto:** PyPI already **0.1.3** — skip publish. X post only if Oscar asks: `~/CODE/fleet-ops/gtm/transcripto-launch-post.md` Option A.
