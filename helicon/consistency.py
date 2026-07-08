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
"""
import os
import re
import urllib.parse

_LINK = re.compile(r"\[[^\]]+\]\(([^)]+?\.md)\)")   # [title](path/to/file.md)
_WIKI = re.compile(r"\[\[([^\]]+?)\]\]")             # [[name]]
_WORD = re.compile(r"[A-Za-z0-9_\-]+")


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
    in_dir_links = [link for link in raw_links if inside(resolve(link))]
    external = sorted({link for link in raw_links if not inside(resolve(link))})
    dangling = sorted({link for link in in_dir_links if not os.path.isfile(resolve(link))})
    dangling_wiki = sorted(
        w for w in wiki if not os.path.isfile(os.path.join(memory_dir, f"{w}.md")))

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

    on_disk = {f for f in os.listdir(memory_dir)
               if f.endswith(".md") and f != index_name}
    unlisted = sorted(f for f in on_disk if not named(f))

    return {
        "ok": True,
        "index": index_path,
        "dir": memory_dir,
        "pointers": len(raw_links) + len(wiki),
        "on_disk": len(on_disk),
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
