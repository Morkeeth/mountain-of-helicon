# Changelog

Each release has full notes in a `RELEASE-NOTES-<version>.md` file at the repository root.
This file is the short index. The newest release is first.

## 0.3.0 (not yet on PyPI)

Changes since 0.2.4. Full notes: [RELEASE-NOTES-0.3.0.md](RELEASE-NOTES-0.3.0.md).

- New: `helicon start`, one first-run card for the whole agent setup.
- New: `helicon ask` reads dated rulings, newest first, and marks the current one.
- New: `helicon followed` lists instruction paths an agent followed and failed to open.
- Changed: the model layer works with any OpenAI-compatible endpoint. There is no default vendor.
- Fixed: `helicon review` gives fewer false alarms on other people's repositories.
- Fixed: `helicon start` runs on a fresh machine with no config file.
- Repository: internal planning files and the August 2026 hackathon build moved from the
  root to `docs/archive/`. Public files no longer contain the author's home path.
  `helicon review .` on a fresh clone of this repository grades A.

The git history was rewritten on 11 Oct 2026. Tags v0.2.2 to v0.2.4 are not on the current
history. v0.3.0 is the first tag on it.

## 0.2.4

[RELEASE-NOTES-0.2.4.md](RELEASE-NOTES-0.2.4.md)

## 0.2.3

[RELEASE-NOTES-0.2.3.md](RELEASE-NOTES-0.2.3.md)

## 0.2.2

[RELEASE-NOTES-0.2.2.md](RELEASE-NOTES-0.2.2.md)

## 0.2.1

[RELEASE-NOTES-0.2.1.md](RELEASE-NOTES-0.2.1.md)

## 0.2.0

[RELEASE-NOTES-0.2.0.md](RELEASE-NOTES-0.2.0.md)
