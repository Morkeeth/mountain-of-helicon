# FC deploy — readiness (prepped 2026-07-18, Terminal 2)

**Status: NOT one-AK/SK-paste from live.** The build tooling is absent on this
machine, so the remaining gate is larger than credentials. Honest state below.

## Ready (verified)
- `web/dist/index.html` built ✓
- `data/helicon-demo.db` seeded (11 planted cubes) and **passes the publish
  preflight** (≤500 cubes, zero personal markers) ✓ — safe store to publish
- `config.json` proves the live Alibaba dependency (Model Studio + DashScope) ✓
- `QWEN_API_KEY` + `DASHSCOPE_API_KEY` present in local `.env` ✓
- Account KYC'd; repo default branch `main` is pushed ✓

## Missing on this machine (the real remaining work, ~15 min first-time)
- **Docker: not installed at all** (no binary, no Docker.app, no colima). The FC
  path is a local `docker build --platform linux/amd64` → ACR push, so this is
  the hard blocker, not AK/SK.
- **Serverless Devs `s`: not installed** → `npm i -g @serverless-devs/s`
- **aliyun CLI: not installed** → `brew install aliyun-cli`
- **ACR namespace `helicon`: unverifiable** without Alibaba credentials (needs
  console + `docker login registry.ap-southeast-1.aliyuncs.com`)

## Oscar — two routes to an Alibaba-served URL

**A. FC (durable anonymous URL, the submission's deployment proof):**
```bash
brew install aliyun-cli && npm i -g @serverless-devs/s   # install tooling
# install Docker Desktop, start it (docker info must succeed)
s config add                                             # paste AK/SK, region ap-southeast-1
# console: Container Registry → create namespace "helicon"
docker login registry.ap-southeast-1.aliyuncs.com
set -a && source .env && set +a                          # QWEN_API_KEY + DASHSCOPE_API_KEY
./fc/deploy-fc.sh                                         # prints the live /api/health URL
```

**B. Cloud Shell (no local Docker; faster for the video, temporary Web Preview URL):**
Alibaba Cloud Shell ships docker/s/aliyun preinstalled. `git clone`, upload
`data/helicon-demo.db`, `export QWEN_API_KEY`, `bash scripts/cloudshell-run.sh`,
then Web Preview port 8420. This is the path CLAUDE.md already decided for the
Alibaba-cloud proof (ECS dead on KYC). Recommend for the demo unless you want the
durable FC URL on the Devpost entry.

Both irreducibly need YOUR Alibaba credentials; nothing here can be done for you.
