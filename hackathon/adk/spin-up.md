# Spin-up — All Things Agentic cloud slice

## Prerequisites

- Google Cloud project + $150 hackathon credits
- `gcloud` CLI authenticated
- Python 3.10+
- Gemini API key (narrator) or Vertex AI enabled

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

## Local ADK runner (before Cloud Run)

```bash
python3 hackathon/adk/run_local.py              # stdout JSON
python3 hackathon/adk/run_local.py -o /tmp/run.json
python3 hackathon/adk/run_local.py --seed       # reseed + run
```

## Deploy (outline — fill in after Cloud agent lands)

```bash
export GOOGLE_CLOUD_PROJECT=your-project
gcloud services enable run.googleapis.com firestore.googleapis.com pubsub.googleapis.com

# Firestore native mode — create in console if needed

gcloud run deploy helicon-measurement-bench \
  --source hackathon/adk \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT

# Manual trigger
bash hackathon/adk/trigger.sh
```

## Verify for judges

1. Cloud Run logs show subprocess exit 0
2. Firestore `runs/{id}` contains `science.verdicts` with at least one UNMEASURABLE
3. Brief URL shows headline + reproduce command
4. Demo video: Console → trigger → brief (≤4 min)

## Reproduce verdicts without cloud

Every number in Firestore must match:

```bash
helicon measurement-bench --json --db hackathon/adk/demo/helicon.db
```

If they differ, the cloud layer is wrong — not the probes.
