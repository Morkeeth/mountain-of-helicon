#!/usr/bin/env python3
"""Executable receipt for Mountain of Helicon's public-launch claims."""

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


CANONICAL_REPO = "Morkeeth/mountain-of-helicon"
FROZEN_REPO = "MorkeethHQ/mount-helicon"


@dataclass
class Check:
    key: str
    label: str
    ok: bool | None
    detail: str
    owner: str = "code"
    required: bool = True


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _public_url_status(url: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "mountain-of-helicon-launch-check"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
        return status == 200, f"HTTP {status} · {url}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} · {url}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, f"unreachable · {url} · {exc}"


def _pypi_status() -> tuple[bool, str]:
    url = "https://pypi.org/pypi/mount-helicon/json"
    request = urllib.request.Request(
        url, headers={"User-Agent": "mountain-of-helicon-launch-check"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} · {url}"
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return False, f"unreachable/invalid · {url} · {exc}"
    info = payload.get("info") or {}
    links = list((info.get("project_urls") or {}).values())
    links.append(info.get("home_page") or "")
    canonical = "github.com/Morkeeth/mountain-of-helicon"
    owned = any(canonical in str(link) for link in links)
    return (
        owned,
        f"published and linked to {CANONICAL_REPO}"
        if owned else "published, but metadata does not link to the canonical repository",
    )


def static_checks(root: Path) -> list[Check]:
    readme = _read(root, "README.md")
    demo = _read(root, "DEMO.md")
    action = _read(root, "action.yml")
    workflow = _read(root, ".github/workflows/memory-ci.yml")
    pyproject = _read(root, "pyproject.toml")
    roadmap = _read(root, "LAUNCH_ROADMAP.md")
    cli = _read(root, "helicon/cli.py")
    report = _read(root, "docs/agent-context-report-2026-08.md")

    launch_surfaces = {
        "README.md": readme,
        "DEMO.md": demo,
        "action.yml": action,
        "CLAUDE.md": _read(root, "CLAUDE.md"),
        "ARCHITECTURE.md": _read(root, "ARCHITECTURE.md"),
        "ROT.md": _read(root, "ROT.md"),
        "web/public/welcome.html": _read(root, "web/public/welcome.html"),
        "web/src/components/Landing.tsx": _read(root, "web/src/components/Landing.tsx"),
    }
    stale_brand = [
        path for path, text in launch_surfaces.items()
        if "Mount Helicon" in text or FROZEN_REPO in text
    ]

    release_commands = (
        "python -m pytest -q",
        "npm run lint",
        "npm run build",
        "python -m build",
        "python -m twine check",
    )
    missing_release_commands = [command for command in release_commands if command not in workflow]

    return [
        Check(
            "identity",
            "Canonical Mountain identity on launch surfaces",
            not stale_brand,
            "clean" if not stale_brand else "stale: " + ", ".join(stale_brand),
        ),
        Check(
            "repository",
            "Consumer links target product repo; Action installs its checked-out revision",
            (
                CANONICAL_REPO in readme
                and FROZEN_REPO not in readme + action
                and "$GITHUB_ACTION_PATH" in action
            ),
            f"{CANONICAL_REPO} · $GITHUB_ACTION_PATH",
        ),
        Check(
            "warning-semantics",
            "Launch copy matches warning-by-default behavior",
            (
                "warns by default" in readme
                and "warning in the terminal" in demo
                and '"warn"' in cli
                and "refuses to let a run start" not in readme
                and "refused in the terminal" not in demo
            ),
            "warn default · block explicit opt-in",
        ),
        Check(
            "measured-claim",
            "Public headline uses the hand-verified denominator",
            (
                "6 repositories (1.04%)" in readme
                and "Finding-level precision was 9/30" in readme
                and re.search(
                    r"\*\*Verified repo prevalence:\*\* 6 / 577 = \*\*1\.04%\*\*",
                    report,
                ) is not None
            ),
            "6 / 577 repos · 1.04% · 9 / 30 findings",
        ),
        Check(
            "terminal-demo",
            "README leads with the deterministic terminal demo",
            (
                "bash scripts/demo.sh" in readme
                and readme.index("bash scripts/demo.sh") < readme.index("helicon demo")
            ),
            "bash scripts/demo.sh",
        ),
        Check(
            "visual-demo",
            "Visual demo targets the planted Rulings queue",
            "#findings" in readme and "#findings" in cli,
            "19 planted memories · localhost · #findings",
        ),
        Check(
            "release-ci",
            "Release workflow covers backend, frontend, and package",
            not missing_release_commands,
            "complete" if not missing_release_commands else "missing: " + ", ".join(missing_release_commands),
        ),
        Check(
            "package-metadata",
            "Package metadata names Mountain and current source URLs",
            (
                "Mountain of Helicon" in pyproject
                and "https://github.com/Morkeeth/mountain-of-helicon" in pyproject
            ),
            "distribution name remains a founder decision",
        ),
        Check(
            "roadmap",
            "Founder-only gates remain explicit",
            all(
                phrase in roadmap
                for phrase in (
                    "Make the GitHub repository public",
                    "PyPI distribution name",
                    "Alibaba deployment",
                    "blind external review",
                )
            ),
            "public repo · package name · deployment · final review",
        ),
    ]


def online_checks() -> list[Check]:
    repo_ok, repo_detail = _public_url_status(
        "https://github.com/Morkeeth/mountain-of-helicon"
    )
    pypi_ok, pypi_detail = _pypi_status()
    return [
        Check(
            "public-repository",
            "Repository is publicly reachable",
            repo_ok,
            repo_detail,
            owner="founder",
        ),
        Check(
            "pypi",
            "Distribution is published on PyPI",
            pypi_ok,
            pypi_detail,
            owner="founder",
            required=False,
        ),
    ]


def run(root: Path, include_online: bool = False) -> list[Check]:
    checks = static_checks(root)
    if include_online:
        checks.extend(online_checks())
    else:
        checks.append(
            Check(
                "online",
                "Founder-controlled online gates",
                None,
                "skipped; rerun with --online",
                owner="founder",
                required=False,
            )
        )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Mountain of Helicon's launch contract against source."
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root",
    )
    parser.add_argument("--online", action="store_true", help="Check public repo and PyPI")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    args = parser.parse_args()

    root = Path(os.path.expanduser(args.root)).resolve()
    checks = run(root, include_online=args.online)
    blockers = [check for check in checks if check.required and check.ok is not True]

    if args.json:
        print(json.dumps({
            "ready": not blockers,
            "blockers": [check.key for check in blockers],
            "checks": [asdict(check) for check in checks],
        }, indent=2))
    else:
        print("Mountain of Helicon · launch contract")
        print()
        for check in checks:
            if check.ok is True:
                state = "PASS"
            elif check.ok is None:
                state = "SKIP"
            elif check.required:
                state = "BLOCK"
            else:
                state = "TODO"
            print(f"  [{state:5}] {check.label}")
            print(f"          {check.detail}")
        print()
        print(
            "READY: source-controlled gates pass."
            if not blockers
            else f"BLOCKED: {len(blockers)} required gate(s) failed."
        )

    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
