"""What changed my mind? Dated memory content, resolved against later corrections.

Reads memory CONTENT, not file presence or git history: markdown memory files
split into paragraphs, plus a dated rulings JSONL. Every passage is dated from
its own text first. Frontmatter `modified:` is only a labelled fallback, because
a file edited on 9 September can still say 20 August in its header.

Lexical score picks the chain; it never picks the winner. Inside a chain the
latest dated Oscar ruling at or before `as_of` is the current recommendation and
every earlier matching passage is listed as superseded with its date. A query
with no dated passage in the window returns an explicit gap and no lesson.

Personal history stays local. Journal, finance and wallet shaped passages are
redacted before they reach any response; the response says how many and why.
Nothing here writes, sends or calls a model.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "helicon.mind-changes/1"
WINDOWS = (7, 30)

# Digit lookarounds, not \b: "2026-08-25T15:32Z" has no word boundary before "T".
_ISO = re.compile(r"(?<!\d)(20\d\d)-(\d\d)-(\d\d)(?!\d)")
_LINK = re.compile(r"\[\[([^\]|#]+)")
_PATH = re.compile(r"(~/[^\s`'\")\]]+|/Users/[^\s`'\")\]]+)")
_WORD = re.compile(r"[a-z0-9]+")
_QUOTE = re.compile(r"Oscar[^:\n]{0,40}:\s*[*_]*[\"“]|[\"“][^\"”]{12,}[\"”]")
_CORRECTION = re.compile(
    r"\b(not ok|overrides?|overturn\w*|supersed\w*|void|current ruling|read-only|"
    r"no longer|was wrong|rejected|killed|lifted|reverse\w*|stop recording|never "
    r"submitted|do not|don't|instead)\b", re.I)
# Journal, finance and wallet shaped material. Matched per passage; a hit is
# redacted on screen and counted, never quoted. Slang such as "rekt" alone is not
# matched; only trading terms are.
_PRIVATE = {
    "wallet": re.compile(r"\b(wallet|seed phrase|mnemonic|private key|0x[0-9a-f]{40})\b", re.I),
    "finance": re.compile(r"\b(hyperliquid|pnl|p&l|portfolio|iban|salary|"
                          r"invoice|tax return|bank account|leverage|liquidat\w*|"
                          r"funding rate|trade entry|position size)\b", re.I),
    "journal": re.compile(r"\b(journal entry|diary|therapy|my feelings|"
                          r"girlfriend|boyfriend|family)\b", re.I),
}
def _extra_private_names():
    """Personal file-name patterns from HELICON_MIND_PRIVATE_FILES (comma list)
    and ~/.helicon/private-file-patterns (one per line), so a user's own project
    names never live in this module. A launchd job reads the file; it has no env."""
    names = [x.strip() for x in os.environ.get("HELICON_MIND_PRIVATE_FILES", "").split(",")]
    path = Path(os.environ.get("HELICON_HOME", "~/.helicon")).expanduser() / "private-file-patterns"
    if path.is_file():
        names += [line.strip() for line in path.read_text().splitlines()]
    return [re.escape(n) for n in names if n and not n.startswith("#")]


_PRIVATE_FILES = re.compile("|".join(["journal", "finance", "wallet", "trading", "diary"] +
                                     _extra_private_names()), re.I)
_STOP = set("a an and are as at be by can do does for from has have how i in is it its me my "
            "of on or our so that the this to was we what when where which who why will with "
            "you your should did change changed mind decide decided decision learn learned "
            "lesson rule ruling think week month past last about".split())


def _stem(t):
    for suffix in ("ing", "ed", "es", "s", "e"):
        if len(t) > 4 and t.endswith(suffix) and not t.endswith("ss"):
            return t[: -len(suffix)]
    return t


def _tokens(text):
    return [_stem(t) for t in _WORD.findall(text.lower()) if t not in _STOP and len(t) > 1]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _as_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _first_iso(text):
    for m in _ISO.finditer(text):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            continue
    return None


def _private_hit(text, name=""):
    for kind, pattern in _PRIVATE.items():
        if pattern.search(text):
            return kind
    if name and _PRIVATE_FILES.search(name):
        return "personal-file"
    return None


def _frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, text[end + 4:]


def memory_passages(memory_dir):
    """Split every memory file into dated paragraphs with byte-exact source refs."""
    out = []
    for path in sorted(Path(memory_dir).expanduser().glob("*.md")):
        if path.name in ("MEMORY.md",) or path.name.startswith("status_"):
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", "replace")
        meta, body = _frontmatter(text)
        fallback = _first_iso(meta.get("modified", ""))
        name = meta.get("name") or path.stem
        links = {l.strip().replace("-", "_") for l in _LINK.findall(text)}
        heading, heading_date = "", None
        line_no = text[: len(text) - len(body)].count("\n") + 1
        para, start = [], line_no

        def flush():
            chunk = "\n".join(para).strip()
            if len(chunk) < 20:
                return
            own = _first_iso(chunk)
            when, source = ((own, "text") if own else (heading_date, "heading") if heading_date
                            else (fallback, "frontmatter") if fallback else (None, "none"))
            out.append({
                "id": _sha(f"{path}:{start}".encode())[:16], "origin": "memory",
                "file": path.name, "chain_key": path.stem.replace("-", "_"),
                "name": name, "desc": meta.get("description", ""), "path": str(path),
                "line": start, "heading": heading,
                "text": chunk, "date": when.isoformat() if when else None, "date_source": source,
                "links": sorted(links), "tasks": [], "file_sha256": _sha(raw),
                "oscar_quote": bool(_QUOTE.search(chunk)),
                "correction": bool(_CORRECTION.search(chunk) or _CORRECTION.search(heading)),
            })

        # A passage is a heading section. Inside an undated section, a paragraph
        # that carries its own date starts a new passage; undated paragraphs stay
        # with the dated passage above them.
        blank = True
        for i, line in enumerate(body.splitlines(), start=line_no):
            if line.startswith("#"):
                flush()
                para, heading = [], line.lstrip("#").strip()
                heading_date, start = _first_iso(heading), i + 1
                continue
            if blank and line.strip() and not heading_date and _first_iso(line) and \
                    any(_first_iso(x) for x in para):
                flush()
                para, start = [], i
            if not para and line.strip():
                start = i
            if para or line.strip():
                para.append(line)
            blank = not line.strip()
        flush()
    return out


def ruling_passages(rulings_path):
    path = Path(rulings_path).expanduser()
    if not path.exists():
        return []
    raw = path.read_bytes()
    out = []
    for n, line in enumerate(raw.decode("utf-8", "replace").splitlines(), start=1):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        text = " ".join(x for x in (row.get("title"), row.get("text"), row.get("quote") and
                                    f"Oscar: \"{row['quote']}\"") if x)
        tasks = row.get("tasks") or []
        out.append({
            "id": _sha(f"{path}:{n}".encode())[:16], "origin": "ruling", "file": path.name,
            "chain_key": "tasks:" + ",".join(sorted(tasks)) if tasks else f"ruling:{n}",
            "name": row.get("title") or "untitled ruling", "desc": row.get("title") or "",
            "path": str(path), "line": n,
            "heading": row.get("source", ""), "text": text, "date": str(row.get("ts", ""))[:10] or None,
            "date_source": "ts", "links": [], "tasks": tasks, "file_sha256": _sha(raw),
            "oscar_quote": bool(row.get("quote")), "correction": bool(_CORRECTION.search(text)),
            "private_flag": bool(row.get("private")),
        })
    return out


_WORK_ROOTS = (Path.home() / ".local/state", Path.home() / "CODE")
_SECRET = re.compile(r"(credential|secret|token|\.env|\.ssh|keychain|password|\.pem|\.key)", re.I)


def _returned_work(passage):
    """Resolve returned-work paths the passage itself cites. Missing is a gap.

    Only paths under the returned-work roots are opened; anything else is
    reported as not opened, and secret-shaped names are never read."""
    rows = []
    for raw in dict.fromkeys(_PATH.findall(passage["text"])):
        raw = raw.rstrip(".,;:")
        p = Path(raw).expanduser()
        if _private_hit(raw) or _SECRET.search(raw):
            rows.append({"path": "[redacted path]", "state": "redacted"})
            continue
        if not any(p == r or r in p.parents for r in _WORK_ROOTS):
            rows.append({"path": raw, "state": "not_opened_outside_work_roots"})
            continue
        if p.is_file():
            data = p.read_bytes()[:200_000]
            excerpt = data.decode("utf-8", "replace").strip()[:400]
            if _private_hit(excerpt):
                excerpt = "[excerpt redacted: personal material]"
            rows.append({"path": raw, "state": "file", "sha256": _sha(data), "excerpt": excerpt})
        elif p.is_dir():
            names = sorted(x.name for x in p.iterdir())[:12]
            rows.append({"path": raw, "state": "directory", "entries": names})
        else:
            rows.append({"path": raw, "state": "unavailable"})
    return rows


def _score(qtok, passage):
    words = set(_tokens(passage["text"] + " " + passage["heading"] + " " + passage["name"]))
    return sum(1 for t in qtok if t in words)


def _public(p, score=None):
    row = {k: p[k] for k in ("id", "origin", "file", "path", "line", "heading", "date",
                             "date_source", "oscar_quote", "correction", "tasks")}
    row["text"] = p["text"]
    if score is not None:
        row["score"] = score
    return row


def _chain_members(seed, passages):
    keys = {seed["chain_key"], *seed["links"]}
    if seed["tasks"]:
        tasks = set(seed["tasks"])
        return [p for p in passages if p["origin"] == "ruling" and tasks & set(p["tasks"])]
    linked = {p["chain_key"] for p in passages if seed["chain_key"] in p["links"]}
    keys |= linked
    return [p for p in passages if p["chain_key"] in keys]


def _lesson(current):
    text = re.sub(r"\s+", " ", current["text"]).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:3])[:500]


def next_prompt(item):
    """Editable prompt carrying one lesson, its date and its source line."""
    cur = item["current"][0]
    lines = [f"Before you propose an action, apply this lesson from Oscar's memory.",
             f"Lesson ({cur['date']}, {cur['file']}:{cur['line']}): {item['lesson']}"]
    for old in item["superseded"][-2:]:
        flat = re.sub(r"\s+", " ", old["text"])[:200]
        lines.append(f"Superseded, do not follow ({old['date']}, {old['file']}:{old['line']}): {flat}")
    lines.append("Task: <describe the task here>. State your proposed action and which lesson changed it.")
    return "\n".join(lines)


def _redact(passages):
    """Redact personal paragraphs on screen and count them by kind.

    A private ruling or a personal-shaped file is dropped whole. Otherwise only
    the paragraph that matched is replaced, so a rule that merely names the
    word "wallet" does not hide the ruling around it."""
    kept, counts = [], {}
    for p in passages:
        whole = ("private-ruling" if p.get("private_flag") else
                 _private_hit("", p["file"]) if p["origin"] == "memory" else None)
        if whole:
            counts[whole] = counts.get(whole, 0) + 1
            continue
        paras, hit = [], False
        for para in re.split(r"\n\s*\n", p["text"]):
            kind = _private_hit(para)
            if kind:
                counts[kind] = counts.get(kind, 0) + 1
                paras.append(f"[redacted on screen: {kind}-shaped paragraph]")
                hit = True
            else:
                paras.append(para)
        if hit:
            if all(x.startswith("[redacted on screen") for x in paras):
                continue
            p = {**p, "text": "\n\n".join(paras), "redacted": True}
        kept.append(p)
    return kept, counts


def answer(question, *, window=7, as_of=None, memory_dir=None, rulings_path=None, limit=5):
    """Return dated, sourced items for a question inside an explicit window."""
    if window not in WINDOWS:
        raise ValueError(f"window must be one of {WINDOWS}")
    as_of = _as_date(as_of or datetime.now(timezone.utc))
    since = as_of - timedelta(days=window)
    passages = []
    if memory_dir:
        passages += memory_passages(memory_dir)
    if rulings_path:
        passages += ruling_passages(rulings_path)
    passages = [p for p in passages if p["date"] and _as_date(p["date"]) <= as_of]
    passages, redactions = _redact(passages)
    qtok = list(dict.fromkeys(_tokens(question or "")))
    base = {"schema": SCHEMA, "question": question, "window_days": window,
            "since": since.isoformat(), "as_of": as_of.isoformat(),
            "redactions": redactions, "sources": {
                "memory_dir": str(memory_dir) if memory_dir else None,
                "rulings": str(rulings_path) if rulings_path else None,
                "passages_read": len(passages)}}

    if qtok:
        scored = sorted(((_score(qtok, p), p) for p in passages), key=lambda x: -x[0])
        need = max(2, -(-len(qtok) // 3)) if len(qtok) > 2 else len(qtok)
        seeds = [p for s, p in scored if s >= need]
    else:
        # "What changed my mind?": every in-window Oscar correction is a seed.
        seeds = [p for p in passages if p["correction"] and p["oscar_quote"]
                 and _as_date(p["date"]) > since]
        seeds.sort(key=lambda p: p["date"], reverse=True)

    items, seen = [], set()
    for seed in seeds:
        if seed["chain_key"] in seen or len(items) >= limit:
            continue
        members = _chain_members(seed, passages)
        is_ruling = lambda m: m["oscar_quote"] or m["origin"] == "ruling"
        if qtok:
            topic = qtok
            relevant = [m for m in members if _score(topic, m) >= need or m is seed]
        else:
            topic = list(dict.fromkeys(_tokens(seed["name"].replace("_", " ") + " " + seed["desc"])))
            relevant = [m for m in members if m is seed or _score(topic, m) >= 3]
        rulings = [m for m in relevant if is_ruling(m)]
        if not rulings:
            continue
        latest = max(r["date"] for r in rulings)
        if _as_date(latest) <= since:
            continue  # the chain's newest ruling predates the window: no change in window
        seen |= {m["chain_key"] for m in members}
        current = [r for r in rulings if r["date"] == latest]
        # Earlier rulings, plus any earlier passage that lexically outranks the
        # current ruling: that is the attractive decoy, and it must be shown losing.
        top_now = max(_score(topic, r) for r in current)
        superseded = sorted((m for m in relevant if m["date"] < latest and
                             (is_ruling(m) or _score(topic, m) >= top_now)),
                            key=lambda r: (r["date"], r["line"]))
        corrected = [r for r in current if r["correction"]]
        instruction = next((r for r in reversed(superseded) if is_ruling(r)), None)
        span_from = instruction["date"] if instruction else latest
        cited = sorted((m for m in members if span_from <= m["date"] <= latest),
                       key=lambda r: (r["date"], r["line"]))
        work, seen_paths = [], set()
        for m in cited:
            for w in _returned_work(m):
                if w["path"] not in seen_paths:
                    seen_paths.add(w["path"])
                    work.append({**w, "cited_by": f"{m['file']}:{m['line']}", "cited_date": m["date"]})
        item = {
            "topic": seed["name"], "chain": sorted({m["file"] for m in members}),
            "instruction": _public(instruction) if instruction else None,
            "current": [_public(r, _score(topic, r)) for r in current],
            "superseded": [_public(r, _score(topic, r)) for r in superseded],
            "changed_in_window": bool(instruction) and bool(corrected),
            "returned_work": work,
            "decoys": [{"id": p["id"], "file": p["file"], "line": p["line"], "date": p["date"],
                        "score": _score(topic, p), "current_score": top_now,
                        "superseded_by": latest}
                       for p in superseded if _score(topic, p) >= top_now],
            "lesson": _lesson(corrected[0] if corrected else current[0]),
        }
        item["next_prompt"] = next_prompt(item)
        key = tuple(sorted(c["id"] for c in item["current"]))
        if any(tuple(sorted(c["id"] for c in it["current"])) == key for it in items):
            continue
        item["relevance"] = max(_score(topic, m) for m in relevant)
        items.append(item)
    if qtok and items:
        # A weak neighbour is a matching row, not an answer.
        best = max(it["relevance"] for it in items)
        items = [it for it in items if it["relevance"] >= 0.6 * best]
    if qtok:
        items.sort(key=lambda it: (it["relevance"], it["current"][0]["date"]), reverse=True)
    else:
        items.sort(key=lambda it: (it["changed_in_window"], it["current"][0]["date"]), reverse=True)

    gap = None
    if not items:
        gap = {"reason": ("No dated Oscar ruling or correction in memory content matches this "
                          f"question between {since} and {as_of}." if qtok else
                          f"No dated Oscar correction in memory content between {since} and {as_of}."),
               "lesson": None}
    return {**base, "items": items, "gap": gap}


def served_by(repo_root=None):
    """Identify the build and source this process is serving from."""
    root = Path(repo_root or Path(__file__).resolve().parents[1])
    def git(*args):
        try:
            return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                  text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    started = _PROCESS_STARTED
    return {"repo": str(root), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "head": git("rev-parse", "--short=12", "HEAD"),
            "dirty": bool(git("status", "--porcelain", "--", "helicon", "web/src", "mac/Sources")),
            "module": str(Path(__file__).resolve()),
            "module_sha256": _sha(Path(__file__).read_bytes())[:16],
            "pid": os.getpid(), "cwd": os.getcwd(),
            "process_started": datetime.fromtimestamp(started, timezone.utc).isoformat()}


_PROCESS_STARTED = time.time()


def default_sources():
    home = Path.home()
    # Claude Code names a project folder after its path with "/" replaced by "-".
    slug = "-" + str(home).strip("/").replace("/", "-")
    return {"memory_dir": os.environ.get("HELICON_MIND_MEMORY",
                                         str(home / ".claude/projects" / slug / "memory")),
            "rulings_path": os.environ.get("HELICON_MIND_RULINGS",
                                           str(home / ".local/state/fleet/rulings.jsonl"))}


def save_lesson(item_lesson, prompt_text, sources, outdir):
    """Write one packet-shaped lesson file for a receiving assistant. Local only."""
    payload = {"schema": "helicon.lesson-packet/1", "created_at": datetime.now(timezone.utc).isoformat(),
               "lesson": item_lesson, "prompt": prompt_text, "sources": sources}
    if _private_hit(prompt_text) or _private_hit(item_lesson):
        raise ValueError("Refusing to save a lesson that carries personal material.")
    data = json.dumps(payload, indent=2, sort_keys=True).encode()
    digest = _sha(data)
    out = Path(outdir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{digest[:16]}.json"
    path.write_bytes(data)
    return {"path": str(path), "sha256": digest, "payload": payload}
