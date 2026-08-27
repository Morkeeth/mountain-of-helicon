"""The checkouts gate — one repo, two working copies, drifting apart.

The registry gate asks whether every project has a row. It is blind to the case
where one project has TWO directories on disk, because both map to the same row.
That is how work gets done twice and lost once: you edit the stale copy, the
tests pass, and the commit lands in a tree nobody pushes.

WHY NOT A FILENAME CHECK
------------------------
The obvious version looks for the same filename in several places. Measured on
`magnet.py` 2026-08-27 it finds five files and four distinct hashes, of which:

  ONE  is real      -- two checkouts of one repo, 499 lines against 385
  ONE  is noise     -- build/lib/... byte-identical to its own source
  TWO  are false    -- unrelated 66- and 86-line files that share a name

A 25% hit rate is a wall, and a wall is a check nobody opens twice. The useful
question is not "same name" but SAME REPO, TWO CHECKOUTS, DIFFERENT HEAD, and it
is answerable with two git calls per directory and no hashing at all.

WHAT IS NOT A FINDING
---------------------
  - A repo with no remote is its own island. Grouping 22 unrelated local-only
    repos under a shared "(none)" key would be the single loudest false positive
    available here, and it is the first thing a naive implementation does.
  - A git WORKTREE is a second checkout on purpose. Worktrees share a common git
    dir, so they are detected and reported apart from clones. The fleet creates
    them deliberately; calling that drift would flag the intended workflow.
  - Build output. `build/`, `dist/` and friends are excluded BY PATH, because a
    tree that is byte-identical to its own source is not a second opinion.
  - Two checkouts sitting at the SAME commit are duplicated disk, not drift.
    Counted, not flagged.
"""
import os
import subprocess

_SKIP_PATH = ("/build/", "/dist/", "/node_modules/", "/.venv/", "/venv/",
              "/site-packages/", "/__pycache__/")


def _git(repo: str, *args) -> str:
    try:
        out = subprocess.run(("git", "-C", repo) + args,
                             capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _is_build_path(path: str) -> bool:
    p = path.replace(os.sep, "/") + "/"
    return any(seg in p for seg in _SKIP_PATH)


def scan_checkouts(code_root: str = "~/CODE") -> list[dict]:
    """Every git working copy directly under code_root, with what identifies it."""
    root = os.path.expanduser(code_root or "~/CODE")
    if not os.path.isdir(root):
        return []
    found = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if name.startswith(".") or not os.path.isdir(path):
            continue
        if not os.path.exists(os.path.join(path, ".git")):
            continue
        if _is_build_path(path):
            continue
        # git prints these relative to the repo when they are inside it, so they
        # are resolved against the repo rather than this process's cwd. On the
        # measured cases both forms agree -- this is correctness under a cwd that
        # differs, not a bug that was observed biting.
        common = _git(path, "rev-parse", "--git-common-dir")
        git_dir = _git(path, "rev-parse", "--git-dir")
        common = os.path.realpath(os.path.join(path, common)) if common else ""
        git_dir = os.path.realpath(os.path.join(path, git_dir)) if git_dir else ""
        found.append({
            "name": name,
            "path": path,
            "remote": _git(path, "remote", "get-url", "origin"),
            "head": _git(path, "rev-parse", "HEAD"),
            "branch": _git(path, "rev-parse", "--abbrev-ref", "HEAD"),
            # A worktree's git-dir sits inside another repo's git dir; a clone's
            # common dir is its own. This is the discriminator, not a heuristic
            # on the directory name.
            "is_worktree": bool(common and git_dir and common != git_dir),
            "dirty": bool(_git(path, "status", "--porcelain")),
        })
    return found


def audit_checkouts(code_root: str = "~/CODE") -> dict:
    checkouts = scan_checkouts(code_root)

    groups = {}
    no_remote, unreadable = [], []
    for c in checkouts:
        if not c["head"]:
            # An empty repo has no HEAD. It cannot be compared to anything, and
            # reporting it as a difference would be an unmeasured thing dressed
            # as a measured one.
            unreadable.append(c["name"])
            continue
        if not c["remote"]:
            no_remote.append(c["name"])
            continue
        groups.setdefault(c["remote"], []).append(c)

    diverged, in_sync, worktrees = [], [], []
    for remote, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        clones = [m for m in members if not m["is_worktree"]]
        trees = [m for m in members if m["is_worktree"]]
        if trees:
            worktrees.append({"remote": remote,
                              "names": sorted(m["name"] for m in trees)})
        if len(clones) < 2:
            continue
        heads = {m["head"] for m in clones}
        row = {
            "remote": remote,
            "checkouts": sorted(
                ({"name": m["name"], "head": m["head"][:8], "branch": m["branch"],
                  "dirty": m["dirty"]} for m in clones),
                key=lambda m: m["name"]),
        }
        (diverged if len(heads) > 1 else in_sync).append(row)

    diverged.sort(key=lambda g: -len(g["checkouts"]))
    return {
        "ok": True,
        "code_root": os.path.expanduser(code_root),
        "checkouts": len(checkouts),
        "remotes": len(groups),
        "no_remote": sorted(no_remote),
        "unreadable": sorted(unreadable),
        "diverged": diverged,
        "in_sync": in_sync,
        "worktree_groups": worktrees,
        "clean": not diverged,
    }
