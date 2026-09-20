# Mountain of Helicon 0.2.1 — release candidate

This candidate makes the deterministic repository review the default install.
It is prepared for review and has not been published.

## What changes

- `pip install mountain-of-helicon==0.2.1` installs Mountain of Helicon without
  third-party runtime packages.
- `helicon review`, `helicon-review`, `helicon truth`, and `helicon ci` keep
  their keyless standard-library path.
- Web, model, retrieval, embeddings, and test dependencies are explicit extras.
- A command that needs an extra names the exact install command and exits without
  a traceback.

## Candidate boundary

PyPI 0.2.0 still contains the earlier full dependency set. These notes describe
the 0.2.1 candidate bytes only. Publishing, tagging, merging, and creating a
GitHub release are separate actions.
