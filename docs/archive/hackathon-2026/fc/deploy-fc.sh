#!/usr/bin/env bash
# One-command deploy of Mount Helicon's read-only dashboard to Alibaba Cloud
# Function Compute. Builds the lean custom-container image at repo root, pushes
# it to Alibaba Container Registry (ACR), then registers the FC web function via
# Serverless Devs. Idempotent — re-run to ship a new build.
#
# Prereqs (see DEPLOY-FC.md for the ~15-min first-time setup):
#   - docker, aliyun CLI, and `s` (Serverless Devs v3) installed
#   - `s config add` profile created (default: "default")
#   - ACR namespace created and `docker login` done to the ACR registry
#   - QWEN_API_KEY and DASHSCOPE_API_KEY exported in this shell
#   - web/dist built (cd web && npx vite build) and data/helicon.db present
set -euo pipefail

# ---- config (override via env) ----
REGION="${HELICON_FC_REGION:-ap-southeast-1}"
NAMESPACE="${HELICON_ACR_NAMESPACE:-helicon}"
ACCESS="${HELICON_S_ACCESS:-default}"
IMAGE="registry.${REGION}.aliyuncs.com/${NAMESPACE}/helicon-fc:latest"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Preflight"
[ -f web/dist/index.html ] || { echo "web/dist missing — run: (cd web && npx vite build)"; exit 1; }
[ -f data/helicon-demo.db ] || { echo "==> seeding demo store"; python3 scripts/demo_seed.py >/dev/null || { echo "demo seed failed"; exit 1; }; }

# The store about to be published. authType is anonymous and the URL goes on
# Devpost, so this is a one-way door: an image pushed to ACR with a private life
# in layer 8 cannot be un-published. The Dockerfile once baked data/helicon.db
# (6,880 real cubes: journal, finance, wallet, passport, private keys) while
# entrypoint.sh's comments claimed it served a seeded store. Nothing caught it,
# because the safety note in DEPLOY-FC.md reasoned about the API keys instead.
# Assert on the artifact, not the intent.
echo "==> Preflight: the store being published"
python3 - <<'PY' || exit 1
import sqlite3, sys
db = "data/helicon-demo.db"
conn = sqlite3.connect(db)
n = conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
hits = {}
for term in ("private key", "seed phrase", "passport", "salary", "recruiter",
             "journal", "wallet", "0x"):
    c = conn.execute("SELECT COUNT(*) FROM helicon_cubes "
                     "WHERE lower(content) LIKE ?", (f"%{term}%",)).fetchone()[0]
    if c:
        hits[term] = c
if n > 500:
    sys.exit(f"    REFUSED: {db} has {n} cubes — that is not the demo seed. "
             f"Rebuild it: python3 scripts/demo_seed.py")
if hits:
    sys.exit(f"    REFUSED: personal markers in the store to be published: {hits}")
print(f"    ok: {n} seeded cubes, no personal markers -> safe to publish")
PY
# Keys are OPTIONAL now: the hosted instance serves the keyless demo (deterministic
# exam + governance loop). Set them only if you want live Qwen judging on the host.
[ -n "${QWEN_API_KEY:-}" ] || echo "  note: no QWEN_API_KEY — hosting the keyless demo (dashboard + deterministic exam)"
command -v s >/dev/null || { echo "Serverless Devs 's' not installed — npm i -g @serverless-devs/s"; exit 1; }

echo "==> Building image: $IMAGE  (context: repo root, lean/keyless)"
DOCKER_BUILDKIT=1 docker build --platform linux/amd64 -f fc/Dockerfile -t "$IMAGE" .

echo "==> Pushing to ACR (run 'docker login registry.${REGION}.aliyuncs.com' first if this fails)"
docker push "$IMAGE"

echo "==> Deploying FC web function via Serverless Devs"
s deploy -t fc/s.yaml --access "$ACCESS" \
  --var "region=${REGION}" --var "namespace=${NAMESPACE}" --var "access=${ACCESS}"

echo
echo "==> Done. The public HTTP trigger URL is printed above (…fcapp.run / …functioncompute…)."
echo "    Verify:  curl <url>/api/health   ->  {\"status\":\"ok\",\"cubes\":<n>}"
echo "    Dashboard: open <url>/ in a browser."
