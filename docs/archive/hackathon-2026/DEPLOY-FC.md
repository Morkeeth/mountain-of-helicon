# Deploy — Alibaba Cloud Function Compute (the deployment proof)

The read-only Mount Helicon dashboard + API runs as an **FC 3.0 custom-container web function**. This is the Alibaba Cloud deployment the hackathon requires. Backend dependency on Alibaba services is real and load-bearing:

- **Compute:** the function itself runs on **Function Compute**.
- **Inference:** Qwen judging (contradiction/identity/synthesis) calls **Model Studio / MaaS** (`token-plan.ap-southeast-1.maas.aliyuncs.com`).
- **Embeddings:** retrieval calls **DashScope** `text-embedding-v4` (`dashscope-intl.aliyuncs.com`).

Kill either key and the intelligence layer goes dark — the container still serves the seeded store, but the judged loop stops. That is the honest "backend uses Alibaba Cloud" claim: FC + Model Studio + DashScope, three Alibaba services.

ECS was dropped on KYC (Jul 3). FC needs no long-lived server and no inbound firewall rule — it fits the constraint.

---

## What's already prepped (done)

Everything in `fc/` is built and the **runtime path is verified locally** (lean image deps boot `helicon.api.app`, the FC-style keyless config renders, the seeded demo store serves, `/api/health` → `{"status":"ok"}`, SPA + `/api/findings` return real data):

- `fc/Dockerfile` — lean custom-container image (no torch/sentence-transformers → <300MB, seconds cold start). Bakes the helicon package, the prebuilt `web/dist` dashboard, and the seeded read-only `data/helicon.db`.
- `fc/entrypoint.sh` — copies the DB to writable `/tmp`, renders `/tmp/config.json` from the two env-var keys (image stays keyless), serves on port 9000.
- `fc/config.fc.json` — keyless config template (Model Studio + DashScope endpoints baked, keys injected at runtime).

> **What this publishes.** The FC http trigger is `authType: anonymous` and the URL is
> submitted publicly, so anything baked into the image is published to the open
> internet — and an image layer is the leak even behind an app password, because
> anyone who pulls it has the file. Only `data/helicon-demo.db` (the synthetic
> seed from `scripts/demo_seed.py`) is baked in. **Never `data/helicon.db`**: the
> real store holds journal, finance, wallet, health and passport memories that do
> not leave the machine. `deploy-fc.sh` refuses to build if the store it is about
> to publish has more than 500 memories or any personal marker. "Zero fake data" is
> earned by the LOCAL run in the demo video and by ROT.md; the deploy is a
> deployment proof, not a data proof.
- `fc/requirements.txt` — lean serve deps only.
- `fc/s.yaml` — Serverless Devs `fc3` web function: custom-container, port 9000, anonymous HTTP trigger, keys via `environmentVariables`.
- `fc/deploy-fc.sh` — build → push to ACR → `s deploy`, one command.

## Your part (~15 min, first time)

Prereqs: an Alibaba Cloud account (already KYC'd for FC), Docker running locally, and the two keys.

```bash
# 0. from repo root, make sure the dashboard bundle + store are present
cd web && npx vite build && cd ..        # only if web/dist is stale
python3 scripts/demo_seed.py              # (re)build data/helicon-demo.db — the ONLY store baked in

# 1. install the two CLIs (once)
npm i -g @serverless-devs/s               # Serverless Devs v3
brew install aliyun-cli                   # or: curl the aliyun CLI

# 2. add your Alibaba credentials to a Serverless Devs profile named "default"
s config add                              # paste AccessKey ID + Secret, region ap-southeast-1
#   (get an AK/SK from RAM console; give it AliyunFCFullAccess + AliyunContainerRegistryFullAccess)

# 3. create an ACR namespace called "helicon" (once)
#   console: Container Registry → Namespaces → Create → name "helicon" (Personal Edition is fine)
#   then log Docker into the ACR registry:
docker login registry.ap-southeast-1.aliyuncs.com   # username = your Aliyun account, password = ACR access password

# 4. export the two keys and deploy
export QWEN_API_KEY=<Model Studio key>       # inference
export DASHSCOPE_API_KEY=<DashScope key>     # embeddings   (both are in your local .env)
./fc/deploy-fc.sh

# 5. the script prints the function's public HTTP URL. Verify:
curl <url>/api/health          # -> {"status":"ok","memories":11}   (the seeded demo store;
                               #    "cubes" is still emitted as a deprecated alias)
open <url>/                    # the dashboard, live on Function Compute
```

That URL is the deployment proof for the submission and the demo.

### Overrides (optional)

`deploy-fc.sh` reads: `HELICON_FC_REGION` (default `ap-southeast-1`), `HELICON_ACR_NAMESPACE` (default `helicon`), `HELICON_S_ACCESS` (default `default`). Change the namespace/region here and in `fc/s.yaml`'s `vars` if you use different names.

### Redeploy

Re-run `./fc/deploy-fc.sh` — it rebuilds, pushes `:latest`, and `s deploy` updates the function in place.

## Notes

- **Keyless image:** the two keys are never baked into a layer; they live only as function env vars, injected at container start. Safe to push the image to a private ACR namespace.
- **Read-only:** the deployed function serves the seeded store; it does not scan your machine (connectors are empty in `config.fc.json`). Rulings/writes happen locally on the CLI, not on FC.
- **Cost:** FC bills per-request + GB-s; an idle dashboard costs ~nothing. Covered by the $3K Alibaba Cloud credits in the prize.
- **Platform:** the image is built `--platform linux/amd64` (FC runs x86); fine to build from Apple Silicon via buildx/Rosetta emulation.
