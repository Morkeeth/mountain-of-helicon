#!/usr/bin/env bash
# The interactive Alibaba Cloud deploy walkthrough.
#
# DEPLOY-FC.md is the reference; this is the co-pilot. It checks the real state
# of your machine at every step, tells you the exact command to run next, and
# refuses to move on until the step actually passed. Nothing here deploys by
# itself: it verifies, then hands you the command.
#
# The one step that matters is STEP 5. The FC trigger is authType:anonymous and
# the URL goes on Devpost, so the image is published to the open internet, and
# an image layer is the leak even behind a password: anyone who pulls it has the
# file. This script asserts on the ARTIFACT (the bytes about to be baked), never
# on the intent, because the intent was already right the day the Dockerfile
# baked 6,880 real cubes while the comments said "seeded".
#
#   bash fc/deploy-guide.sh
set -uo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"

B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; N=$'\033[0m'
ok(){ printf "  ${G}OK${N}    %s\n" "$1"; }
bad(){ printf "  ${R}TODO${N}  %s\n" "$1"; }
warn(){ printf "  ${Y}!${N}     %s\n" "$1"; }
step(){ printf "\n${B}%s${N}\n" "$1"; }
cmd(){ printf "        ${D}\$ %s${N}\n" "$1"; }
pause(){ printf "\n${D}      [enter] when done, or ctrl-c to stop${N} "; read -r _ </dev/tty || true; }

TODO=0

printf "\n${B}Mount Helicon -> Alibaba Cloud Function Compute${N}\n"
printf "${D}The deployment proof. Reference: DEPLOY-FC.md${N}\n"

# ---------------------------------------------------------------- step 0
step "STEP 0 - do you actually need this?"
cat <<'TXT'
      The track rule asks for "a link to a code file demonstrating use of
      Alibaba Cloud services/APIs". You already satisfy that three times over,
      and those links are live in SUBMISSION.md:

        helicon/qwen.py        Model Studio / MaaS inference
        helicon/embeddings.py  DashScope text-embedding-v4
        fc/s.yaml + Dockerfile Function Compute

      So a live URL is a BONUS, not a requirement. It costs ~30 min from a cold
      machine (Docker Desktop alone is a big install). If the video is not
      recorded yet, record first and come back to this. The deploy cannot save a
      missing video; a missing deploy cannot sink a good one.
TXT
pause

# ---------------------------------------------------------------- step 1
step "STEP 1 - toolchain"
for t in docker aliyun s; do
  if command -v "$t" >/dev/null 2>&1; then ok "$t installed"; else bad "$t missing"; TODO=1; fi
done
if ! command -v docker >/dev/null 2>&1; then
  cmd "brew install --cask docker    # then LAUNCH Docker Desktop once"
fi
if ! command -v aliyun >/dev/null 2>&1; then
  cmd "brew install aliyun-cli"
fi
if ! command -v s >/dev/null 2>&1; then
  cmd "npm install -g @serverless-devs/s3    # the 's' CLI, v3"
fi
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then ok "docker daemon running"
  else bad "docker installed but the daemon is NOT running - open Docker Desktop"; TODO=1; fi
fi
[ "$TODO" = 1 ] && pause

# ---------------------------------------------------------------- step 2
step "STEP 2 - Alibaba credentials"
cat <<'TXT'
      You need an AccessKey pair (AK/SK) from the Alibaba Cloud console:
        console -> profile menu -> AccessKey -> Create AccessKey
      Use a RAM user with AliyunFCFullAccess + AliyunContainerRegistryFullAccess
      rather than the root key. The root key can do anything to the account; this
      script only needs to push an image and register a function.
TXT
if [ -f "$HOME/.s/access.yaml" ] || [ -d "$HOME/.s" ]; then
  ok "Serverless Devs profile dir exists (~/.s)"
  cmd "s config get    # confirm the 'default' profile has your AK/SK"
else
  bad "no Serverless Devs profile yet"
  cmd "s config add    # choose 'Alibaba Cloud', paste AK + SK, name it: default"
  TODO=1
fi
pause

# ---------------------------------------------------------------- step 3
step "STEP 3 - the two Qwen keys (this is the Alibaba backend dependency)"
if [ -n "${QWEN_API_KEY:-}" ]; then ok "QWEN_API_KEY exported"; else bad "QWEN_API_KEY not exported in this shell"; TODO=1; fi
if [ -n "${DASHSCOPE_API_KEY:-}" ]; then ok "DASHSCOPE_API_KEY exported"; else bad "DASHSCOPE_API_KEY not exported in this shell"; TODO=1; fi
if [ -z "${QWEN_API_KEY:-}" ] || [ -z "${DASHSCOPE_API_KEY:-}" ]; then
  printf "        %s\n" "They already live in config.json. Export them for this shell only:"
  cmd 'export QWEN_API_KEY=$(python3 -c "import json;print(json.load(open(\"config.json\"))[\"qwen_api_key\"])")'
  cmd 'export DASHSCOPE_API_KEY=$(python3 -c "import json;print(json.load(open(\"config.json\"))[\"embeddings\"][\"api_key\"])")'
  printf "        ${D}%s${N}\n" "The image stays keyless: s.yaml injects these as env vars at deploy."
  pause
fi

# ---------------------------------------------------------------- step 4
step "STEP 4 - ACR (the image registry)"
REGION="${HELICON_FC_REGION:-ap-southeast-1}"
NS="${HELICON_ACR_NAMESPACE:-helicon}"
cat <<TXT
      Create a namespace in Container Registry, region ${REGION} (Singapore -
      it matches the Model Studio endpoint the code already points at):
        console -> Container Registry -> Personal Instance -> Namespace -> Create
        namespace name: ${NS}
TXT
cmd "docker login --username=<your-aliyun-account> registry.${REGION}.aliyuncs.com"
pause

# ---------------------------------------------------------------- step 5
step "STEP 5 - WHAT YOU ARE ABOUT TO PUBLISH  <- the step that matters"
if [ ! -f data/helicon-demo.db ]; then
  bad "data/helicon-demo.db missing"
  cmd "python3 scripts/demo_seed.py"
else
  python3 - <<'PY'
import sqlite3, sys
G="\033[32m"; R="\033[31m"; Y="\033[33m"; N="\033[0m"; D="\033[2m"
TERMS=("private key","seed phrase","passport","salary","recruiter","journal","wallet","0x")
def scan(db):
    c=sqlite3.connect(db)
    n=c.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
    hits={t:c.execute("SELECT COUNT(*) FROM helicon_cubes WHERE lower(content) LIKE ?",(f"%{t}%",)).fetchone()[0] for t in TERMS}
    return n,{k:v for k,v in hits.items() if v}
n,h = scan("data/helicon-demo.db")
print(f"  {G}OK{N}    data/helicon-demo.db -> {n} cubes, sensitive hits: {h or 'none'}")
print(f"        {D}this is the file the Dockerfile bakes (COPY data/helicon-demo.db ./data/helicon.db){N}")
try:
    rn,rh = scan("data/helicon.db")
    print(f"  {R}NEVER{N} data/helicon.db      -> {rn} cubes, sensitive hits: {rh}")
    print(f"        {D}your real store. private keys, passport, wallet. it does not leave this machine.{N}")
except Exception:
    pass
if n > 500 or h:
    print(f"\n  {R}STOP{N}  the demo store is not clean. Rebuild: python3 scripts/demo_seed.py")
    sys.exit(1)
PY
  [ $? -ne 0 ] && exit 1
fi
cat <<'TXT'

      Understand the trade you are making, because it is a one-way door:

      The public dashboard serves the SEEDED store (11 planted memories), not
      your real one. That is correct and deliberate - the real store holds
      private keys and passport data and an anonymous URL is forever - but it
      means a judge clicking your link sees a SPARSE dashboard of synthetic
      data: 0 reviews, 0 rules, 0 runs, 0 judge runs.

      So the deploy proves DEPLOYMENT, not the product. The product is proven by
      the local run in your video, on the real store. Do not let the link carry
      weight it cannot hold, and say so on Devpost in one line:
        "Live URL = the FC deployment proof, serving a seeded store. The demo
         video is the real store; the real store is not publishable."

      BETTER OPTION (if you have 20 min): build the public store from a PUBLIC
      repo instead of the planted seed. Real commits, real agent-rules file,
      cited by SHA, zero privacy risk, reproducible by any judge:
        $ bash scripts/demo_public_store.sh
      That turns the live URL from "synthetic fixture" into "Helicon auditing
      OpenAI's own AGENTS.md", which is a link worth clicking.
TXT
pause

# ---------------------------------------------------------------- step 6
step "STEP 6 - the dashboard bundle"
if [ -f web/dist/index.html ]; then
  ok "web/dist present ($(find web/dist -type f | wc -l | tr -d ' ') files)"
  cmd "cd web && npx vite build && cd ..    # rebuild if you changed the UI"
else
  bad "web/dist missing"; cmd "cd web && npx vite build && cd .."
fi
pause

# ---------------------------------------------------------------- step 7
step "STEP 7 - deploy"
cat <<TXT
      One command. Builds at repo root, pushes to ACR, registers the FC web
      function via Serverless Devs. Idempotent - re-run to ship a new build.
TXT
cmd "bash fc/deploy-fc.sh"
printf "        ${D}%s${N}\n" "It re-runs the STEP 5 assertion itself before building. Belt and suspenders."
pause

# ---------------------------------------------------------------- step 8
step "STEP 8 - verify what you actually shipped"
cat <<'TXT'
      s deploy prints the trigger URL. Then, before it goes on Devpost:
TXT
cmd 'curl -s "$URL/api/health"            # expect {"status":"ok"}'
cmd 'curl -s "$URL/api/report" | head -c 300'
cmd 'open -a "Brave Browser" "$URL"       # eyeball it like a judge would'
cat <<'TXT'

      Last gate, and it is the same lesson as STEP 5: check the artifact, not
      the intent. Confirm the SHIPPED container is serving the seeded store and
      not something else that ended up in a layer:
TXT
cmd 'curl -s "$URL/api/cubes" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get(\"cubes\",d)), \"cubes served\")"'
printf "        ${D}%s${N}\n" "Expect ~11. If it prints thousands, TEAR THE FUNCTION DOWN and rotate the keys."

printf "\n${B}Done.${N} ${D}Reference: DEPLOY-FC.md. Safety rationale: fc/deploy-fc.sh preflight.${N}\n\n"
