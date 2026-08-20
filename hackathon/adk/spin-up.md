# Spin-up — All Things Agentic cloud slice

## Prerequisites

- Google Cloud project + hackathon credits
- `gcloud` CLI authenticated (`gcloud auth login` + `gcloud auth application-default login`)
- Python 3.10+
- IAM: deployer needs `roles/owner` or `roles/run.admin` + `roles/cloudbuild.builds.editor` + `roles/datastore.owner` for first-time Firestore create

## Local (no GCP)

```bash
cd mountain-of-helicon
python3 scripts/check_python.py
python3 -m pip install -e .

# Witness on your machine (optional — uses ~/.helicon by default)
helicon measurement-bench

# JSON witness (same payload Firestore stores)
helicon measurement-bench --json

# Demo store (after seeded DB exists)
helicon measurement-bench --json --db hackathon/adk/demo/helicon.db
```

## Build demo store

```bash
python3 hackathon/adk/seed_demo_db.py   # creates hackathon/adk/demo/helicon.db
# 15,001 cubes · 28 retrievals · UNMEASURABLE interactions wedge · 2 weeks measure
```

The demo DB is gitignored — **seed before Docker build** (deploy.sh does this automatically).

## Local ADK runner (before Cloud Run)

```bash
python3 hackathon/adk/run_local.py              # stdout JSON
python3 hackathon/adk/run_local.py -o /tmp/run.json
python3 hackathon/adk/run_local.py --seed       # reseed + run
```

## Local agent + brief (no Firestore)

```bash
python3 hackathon/adk/seed_demo_db.py
python3 hackathon/adk/agent/main.py             # agent on :8080

# another terminal
curl -s -X POST localhost:8080/run | python3 -m json.tool | head -20

python3 hackathon/adk/run_local.py -o /tmp/run.json
python3 hackathon/adk/brief/serve.py            # brief on :8080 — reads /tmp/run.json
# open http://localhost:8080
```

Without `GOOGLE_CLOUD_PROJECT`, the agent skips Firestore writes and returns witness JSON only.

## Deploy to Cloud Run (scale to zero)

```bash
export GOOGLE_CLOUD_PROJECT=your-gcp-project
export REGION=us-central1

# One-shot: APIs, Firestore native DB, both Cloud Run services, Pub/Sub topic, IAM
bash hackathon/adk/deploy/deploy.sh
```

What `deploy.sh` does:

1. Enables Run, Firestore, Pub/Sub, Cloud Build
2. Creates Firestore native database (if missing)
3. Seeds demo DB locally if absent
4. Builds + deploys **helicon-measurement-bench** (agent — subprocess witness + Firestore write)
5. Creates Pub/Sub topic **helicon-measurement-trigger**
6. Builds + deploys **helicon-brief** (static UI reading latest Firestore run)
7. Grants both service accounts **`roles/datastore.user`**

### Required IAM (Cloud Run runtime)

| Principal | Role | Why |
|---|---|---|
| Cloud Run agent SA | `roles/datastore.user` | Write `runs/{uuid}` after bench |
| Cloud Run brief SA | `roles/datastore.user` | Read latest run for `/api/run` |
| Deployer (you) | `roles/run.admin`, `roles/cloudbuild.builds.editor` | `deploy.sh` |

Set via deploy script automatically. For manual grant:

```bash
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/datastore.user"
```

### Trigger a cloud run

```bash
export GOOGLE_CLOUD_PROJECT=your-gcp-project
bash hackathon/adk/deploy/trigger.sh
# POST /run on helicon-measurement-bench, prints run_id + unmeasurable_count
```

Optional Pub/Sub audit message:

```bash
gcloud pubsub topics publish helicon-measurement-trigger \
  --project="$GOOGLE_CLOUD_PROJECT" \
  --message='scheduled tick'
```

(Pub/Sub push → Cloud Run wiring is v2; v1 uses direct POST for demo reliability.)

### URLs after deploy

```bash
gcloud run services describe helicon-measurement-bench \
  --region us-central1 --format='value(status.url)'
gcloud run services describe helicon-brief \
  --region us-central1 --format='value(status.url)'
```

Append both to `hackathon/adk/CLOUD-LOG.md`.

## Verify for judges

1. Cloud Run logs show subprocess exit 0
2. Firestore `runs/{id}` contains `science.verdicts` with at least one UNMEASURABLE
3. Brief URL shows UNMEASURABLE headline + reproduce command
4. Demo video: Console → trigger → brief (≤4 min)

## Reproduce verdicts without cloud

Every number in Firestore must match:

```bash
helicon measurement-bench --json --db hackathon/adk/demo/helicon.db
```

If they differ, the cloud layer is wrong — not the probes.
