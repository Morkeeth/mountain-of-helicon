# Mountain of Helicon launch roadmap

## Launch contract

The first public release is the executable preflight for agent context:

> Mountain of Helicon checks whether an agent's loaded instructions still match
> repository reality, shows the command and stdout behind every contradiction,
> and warns before work continues.

The broader control-plane vision remains the roadmap. The launch does not claim
that every memory is verified, that warning mode blocks runs, or that routing and
cross-agent learning are mature.

## Gate 0 — Truthful and reproducible

- [x] One canonical product name: Mountain of Helicon.
- [x] One canonical repository: `Morkeeth/mountain-of-helicon`.
- [x] Warning semantics in README, demo copy, and runtime.
- [x] Public-corpus claim uses the hand-verified 1.74% repo rate.
- [ ] Clean-clone terminal demo succeeds.
- [ ] Clean-clone visual demo builds assets, seeds a writable isolated store,
      serves the SPA, and exposes at least one ruling.
- [ ] Full Python suite and frontend lint/build pass without concurrent agents.

## Gate 1 — Public repository release

- [ ] Make the GitHub repository public.
- [ ] Confirm clone, README links, images, report links, and Action install URL
      work without authentication.
- [ ] Enable branch protection requiring the release-gate workflow.
- [ ] Add a tagged `v0.1.0` GitHub release with wheel and source distribution.
- [ ] Publish only claims represented by automated acceptance checks.

## Gate 2 — Launch proof

- [ ] Record a 45–60 second terminal demo:
      measured finding → executable receipt → doorway warning → recorded reason.
- [ ] Capture a current Mountain-branded screenshot; retire the stale dashboard
      image and stale ECS title.
- [ ] Publish a short launch post linking the repository and the August report.
- [ ] Run one blind external review of README, demo, and launch copy.

## Gate 3 — Package distribution

- [ ] Decide whether to keep the distribution name `mount-helicon` or publish
      under `mountain-of-helicon` before the first PyPI release.
- [ ] Ensure demo state is always under a user-writable directory.
- [ ] Verify `pipx install <distribution>`, `helicon --help`, and the terminal
      demo from the built wheel.
- [ ] Add trusted publishing from GitHub Actions; never store a PyPI token.

## Gate 4 — Hosted product

- [ ] Replace the stale HTTP ECS demo or remove it from launch surfaces.
- [ ] Terminate TLS and require authentication for every mutation API.
- [ ] Replace wildcard credentialed CORS with configured origins.
- [ ] Add session login, CSRF protection, rate limits, logout, and backup/restore.
- [ ] Keep personal stores private; public demos use labelled planted data only.

## Gate 5 — Cross-agent loop

- [ ] Automate Cursor Cloud export ingestion into a persistent store.
- [ ] Register authenticated remote MCP for each agent.
- [ ] Prove: agent A surfaces context → human corrects it → agent B retrieves the
      correction on a later run.
- [ ] Record receipt, latency, failure mode, and rollback for that loop.

## Founder-only decisions

1. Make the repository public.
2. Choose the PyPI distribution name before publishing.
3. Choose whether the current Alibaba deployment is replaced or omitted.
4. Approve the final tweet/video after the blind review.

## Launch acceptance command

```bash
bash scripts/judge-check.sh --full
```

It must clone only committed files, install from scratch, build the dashboard,
run `helicon demo`, verify populated health/findings endpoints, and resolve the
referenced JavaScript asset.
