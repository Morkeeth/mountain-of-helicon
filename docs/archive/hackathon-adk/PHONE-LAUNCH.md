# Paste into https://cursor.com/agents — then shut down

**Repo:** `Morkeeth/mountain-of-helicon`  
**Branch:** `hackathon/adk-cloud`  
**Worker:** Cloud (not Local / My Machines)

---

## Agent 1 — GCP deploy (priority)

```
Read docs/archive/hackathon-adk/spin-up.md and docs/archive/hackathon-adk/deploy/deploy.sh.

Slice 2 files already exist on this branch. Your job: make deploy actually work
(or document the exact blocker).

1. If GOOGLE_CLOUD_PROJECT is unset, write docs/archive/hackathon-adk/CLOUD-LOG.md with the
   exact gcloud commands Oscar runs once — do not fake a URL.
2. If GCP creds exist in the environment, run bash docs/archive/hackathon-adk/deploy/deploy.sh
   and append Agent URL + Brief URL to CLOUD-LOG.md.
3. Do NOT reimplement helicon probes. Subprocess only:
   python3 -m helicon measurement-bench --json --db docs/archive/hackathon-adk/demo/helicon.db
4. Demo store only. Never ~/.helicon.
5. Commit + push on this branch (workOnCurrentBranch).

Done when CLOUD-LOG has either live URLs or honest one-shot commands.
```

---

## Agent 2 — Present-ready README (optional, second launch)

```
On branch hackathon/adk-cloud, update README.md with a "Hackathon demo" section
that points to: helicon measurement-bench, docs/archive/hackathon-adk/PRESENT-2026-08-21.md,
and docs/archive/hackathon-adk/spin-up.md. Keep it short. Do not rewrite the product pitch.
Commit to this branch.
```
