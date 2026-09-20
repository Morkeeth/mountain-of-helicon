#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wheel="${1:-"$root/dist/mountain_of_helicon-0.2.1-py3-none-any.whl"}"
python_bin="${PYTHON:-python3}"

if [[ ! -f "$wheel" ]]; then
    echo "Wheel not found: $wheel" >&2
    exit 2
fi
wheel="$(cd "$(dirname "$wheel")" && pwd)/$(basename "$wheel")"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
venv="$work/venv"
fixture="$work/erik-repo"
home="$work/empty-home"
mkdir -p "$fixture/docs" "$fixture/scripts" "$home"

cat > "$fixture/AGENTS.md" <<'EOF'
# Agent instructions

Read [the setup guide](docs/setup.md).
Read [the deployment guide](docs/deployment.md).
Run `python scripts/check.py` before each change.
EOF
printf '%s\n' '# Setup' > "$fixture/docs/setup.md"
printf '%s\n' 'print("fixture check passed")' > "$fixture/scripts/check.py"

"$python_bin" -m venv "$venv"
echo "INSTALL: $venv/bin/python -m pip install $wheel"
HOME="$home" "$venv/bin/python" -m pip \
    --disable-pip-version-check --quiet install "$wheel"

# The default install is the review and nothing else. `pip list` is where a stranger
# sees what the install cost, so this is the check that can go red on a heavy default.
HOME="$home" "$venv/bin/python" -m pip list --format=json > "$work/pip-list.json"
"$venv/bin/python" - "$work/pip-list.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    installed = {item["name"].lower() for item in json.load(handle)}
heavy = installed & {"openai", "fastapi", "uvicorn", "numpy", "starlette", "pydantic",
                     "sentence-transformers", "torch", "requests"}
if heavy:
    raise SystemExit(f"Default install pulled optional packages: {sorted(heavy)}")
print(f"DEFAULT INSTALL: {sorted(installed - {'pip', 'setuptools', 'wheel'})}")
PY

set +e
HOME="$home" \
NO_COLOR=1 \
QWEN_API_KEY= \
DASHSCOPE_API_KEY= \
OPENAI_API_KEY= \
"$venv/bin/helicon" review "$fixture" --json > "$work/result.json" 2> "$work/review.err"
review_status=$?
set -e

if [[ "$review_status" -ne 1 ]]; then
    echo "Expected exit 1 for one true finding, got $review_status." >&2
    cat "$work/review.err" >&2
    [[ -f "$work/result.json" ]] && cat "$work/result.json" >&2
    exit 1
fi

# A command that needs an extra names it in one line and exits 3, not a traceback.
set +e
HOME="$home" "$venv/bin/helicon" serve > "$work/serve.out" 2> "$work/serve.err"
serve_status=$?
set -e
if [[ "$serve_status" -ne 3 ]] \
    || ! grep -qF 'pip install "mountain-of-helicon[web]"' "$work/serve.err" \
    || grep -q Traceback "$work/serve.err"; then
    echo "Expected 'helicon serve' to exit 3 naming the web extra, got $serve_status." >&2
    cat "$work/serve.err" >&2
    exit 1
fi

"$venv/bin/python" - "$work/result.json" <<'PY'
import importlib.metadata
import json
import sys

distribution = importlib.metadata.distribution("mountain-of-helicon")
if distribution.version != "0.2.1":
    raise SystemExit(f"Expected installed version 0.2.1, got {distribution.version}")
scripts = {
    entry.name: entry.value
    for entry in distribution.entry_points
    if entry.group == "console_scripts"
}
if scripts.get("helicon") != "helicon.cli:main":
    raise SystemExit(f"Wrong helicon entry point: {scripts.get('helicon')!r}")

with open(sys.argv[1], encoding="utf-8") as handle:
    result = json.load(handle)

expected = {
    "tier": "pointer",
    "where": "AGENTS.md:4",
    "raw": "docs/deployment.md",
}
findings = result["findings"]
if result["broken"] != 1 or len(findings) != 1:
    raise SystemExit(
        f"Expected exactly one finding, got broken={result['broken']} findings={findings!r}"
    )
for key, value in expected.items():
    if findings[0].get(key) != value:
        raise SystemExit(
            f"Expected {key}={value!r}, got {findings[0].get(key)!r}"
        )
if result["instruction_files"] != ["AGENTS.md"]:
    raise SystemExit(
        f"Expected only AGENTS.md, got {result['instruction_files']!r}"
    )

print(
    "COLD INSTALL PASS: mountain-of-helicon 0.2.1 reported the planted missing file "
    "and did not report the valid file or command."
)
print(
    f"EVIDENCE: {findings[0]['where']} {findings[0]['raw']} "
    f"with broken={result['broken']}."
)
PY
