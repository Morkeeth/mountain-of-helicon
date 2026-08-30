"""The consistency gate — the index must match its own directory.

The failure that bites hardest is the cheapest to catch. An index file (a
MEMORY.md, a registry, a table of contents) is loaded every session as trusted
background, so it gets the least scrutiny of anything in the system. A pointer
to a file that was deleted, or a file the index never lists, survives for
months because nobody re-reads the thing they see every day. Loaded is not
verified.

This gate is deterministic and free: parse the pointers the index makes, list
the directory it indexes, and diff. No model, no embeddings. The check that
would have caught the drift is twenty lines, not intelligence.

IT USED TO LIST ONE LEVEL AND CALL THAT THE DIRECTORY.
------------------------------------------------------
`os.listdir` is not a corpus. Measured 2026-08-27 on Oscar's own memory
directory: the gate read 273 of 352 files and printed `consistent: False` with
16 unlisted — a confident verdict over a population it never opened. The 79 it
could not see were all under `archive/`. This is the defect class the tool
exists to find, in the tool.

Recursion is DEFAULT-ON and not a flag. A scanner that silently skips a fifth of
its corpus is making exactly the claim this gate refuses, and that does not go
behind an opt-in.

AN ARCHIVE IS NOT ROT.
----------------------
Recursing naively would have been worse than the bug: every one of those 79
files is under a directory the index itself points at with "Older -> archive/",
so a naive walk turns a 16-item finding into a ~95-item wall, most of it
crying wolf against the operator's own stated convention. A directory that
declares itself archival is SCANNED AND COUNTED, and its files are not required
to be named by the index. They are reported separately so the number is visible
rather than silently dropped — the point is that nothing is invisible, not that
everything is a finding.
"""
import os
import re
import urllib.parse

_LINK = re.compile(r"\[[^\]]+\]\(([^)]+?\.md)\)")   # [title](path/to/file.md)
_WIKI = re.compile(r"\[\[([^\]]+?)\]\]")             # [[name]]
_WORD = re.compile(r"[A-Za-z0-9_\-]+")

# A directory that says it is archival, by name. Deliberately a small closed list
# and not a heuristic: mis-classifying a live directory as archival would hide
# real drift, which is the failure this whole module is about.
_ARCHIVAL = {"archive", "archives", "archived", "_archive", ".archive", "old"}


def _walk_md(root: str) -> list[str]:
    """Every .md under root, as paths relative to root. Dotdirs are skipped."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return out


def _is_archival(rel: str) -> bool:
    """True when any directory on the path declares itself archival."""
    parts = rel.split(os.sep)[:-1]
    return any(p.lower() in _ARCHIVAL for p in parts)


def _links(text: str) -> list[str]:
    return [m.group(1) for m in _LINK.finditer(text)]


def audit_index(index_path: str, memory_dir: str | None = None) -> dict:
    index_path = os.path.abspath(os.path.expanduser(index_path))
    if not os.path.isfile(index_path):
        return {"ok": False, "reason": f"no index file at {index_path}"}
    index_dir = os.path.dirname(index_path)
    memory_dir = (os.path.abspath(os.path.expanduser(memory_dir))
                  if memory_dir else index_dir)
    index_name = os.path.basename(index_path)
    text = open(index_path, encoding="utf-8").read()

    raw_links = _links(text)
    wiki = {m.group(1).strip() for m in _WIKI.finditer(text)}

    def resolve(link: str) -> str:
        return os.path.normpath(os.path.join(index_dir, urllib.parse.unquote(link)))

    def inside(path: str) -> bool:
        return path == memory_dir or path.startswith(memory_dir + os.sep)

    # This gate checks the index against the directory it indexes. Links that
    # point OUTSIDE that directory (a cross-vault ../ path) are a different
    # concern, so they are counted, not flagged: crying wolf on an out-of-scope
    # link is exactly the drift-fatigue the gate exists to avoid.
    every = [f for f in _walk_md(memory_dir) if f != index_name]
    by_stem = {}
    for rel in every:
        by_stem.setdefault(os.path.basename(rel)[:-3], rel)

    in_dir_links = [link for link in raw_links if inside(resolve(link))]
    external = sorted({link for link in raw_links if not inside(resolve(link))})
    dangling = sorted({link for link in in_dir_links if not os.path.isfile(resolve(link))})
    # A wikilink resolves anywhere in the tree, not only at the top level. Before
    # the walk existed, [[a-note]] that had been moved into archive/ was reported
    # DANGLING even though the file was right there — a false alarm produced by
    # the same one-level read that hid the files in the first place.
    dangling_wiki = sorted(w for w in wiki if w.strip() not in by_stem)

    # A file is "named" if the index (or a sub-index it links to, one hop) refers
    # to it by markdown link, wikilink, or bare stem. The grouped pattern names
    # files by stem without the shared prefix (feedback_index.md lists
    # 'no_fake_data' for feedback_no_fake_data.md), so match on stem too.
    direct = {os.path.basename(link) for link in raw_links} | {f"{w}.md" for w in wiki}
    corpus = text
    for link in raw_links:
        sub = resolve(link)
        if os.path.dirname(sub) == memory_dir and os.path.isfile(sub) and sub != index_path:
            try:
                corpus += "\n" + open(sub, encoding="utf-8").read()
            except OSError:
                pass
    words = set(_WORD.findall(corpus))

    def named(fname: str) -> bool:
        if fname in direct:
            return True
        stem = fname[:-3]
        if stem in words:
            return True
        return "_" in stem and stem.split("_", 1)[1] in words

    archived = sorted(f for f in every if _is_archival(f))
    live = [f for f in every if not _is_archival(f)]

    # `named` matches on basename, so a file keeps its identity wherever it sits.
    unlisted = sorted(f for f in live if not named(os.path.basename(f)))
    # Reported, never flagged: an archived file the index does not name is the
    # convention working, not drift.
    archived_unlisted = sorted(f for f in archived if not named(os.path.basename(f)))

    return {
        "ok": True,
        "index": index_path,
        "dir": memory_dir,
        "pointers": len(raw_links) + len(wiki),
        "scanned": len(every),
        "on_disk": len(live),
        "archived": len(archived),
        "archived_unlisted": archived_unlisted,
        "external": external,
        "dangling": dangling,
        "dangling_wikilinks": dangling_wiki,
        "unlisted": unlisted,
        "consistent": not (dangling or dangling_wiki or unlisted),
    }


def default_index(config: dict | None = None) -> str | None:
    """Where to look when no path is given: a configured index, else the
    Claude Code auto-memory MEMORY.md if one exists on this machine."""
    config = config or {}
    cfg = config.get("consistency", {}) or {}
    if cfg.get("index"):
        return os.path.expanduser(cfg["index"])
    base = os.path.expanduser("~/.claude/projects")
    if os.path.isdir(base):
        for proj in sorted(os.listdir(base)):
            cand = os.path.join(base, proj, "memory", "MEMORY.md")
            if os.path.isfile(cand):
                return cand
    return None
