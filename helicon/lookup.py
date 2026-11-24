"""The right-page lookup: one prompt in, the one page section or ruling out.

Saving a rule does not mean an agent reads it. The prompt hook used to hand
every session the newest approved rulings, whatever the prompt was about. This
module answers a narrower question, fast and locally: of the pages and rulings
the operator named in config, which ONE matters for this prompt, if any?

Design, in the order the hook needs it:

- Corpus from config only (`lookup.pages`: globs; `lookup.rulings`: jsonl
  files). Nothing is hardcoded; with no config the lookup is off.
- Lexical, local, no network and no embeddings: SQLite FTS5 with the porter
  stemmer, in its own small database next to the store.
- The index rebuilds in a detached background process when a source file
  changes. A prompt never waits for a rebuild; it reads the last index.
- One hit or nothing. A hit needs two distinct prompt words in the same unit,
  at least one of them rare in the corpus. Below that the hook says nothing,
  because a wrong page handed over with authority is worse than none.
- Rulings marked private, superseded or retired never enter the index, and
  neither does any page or ruling whose path or text matches the privacy
  pattern. The newest ruling wins a tie.
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")

# Words that say what kind of request it is, not what it is about.
_STOP = set("""
the and for with that this from into onto your you our are was were will would
should could can cant not but all any some each every just also then than them
they their there here what when where which who whom why how its it's has have
had having been being does did doing done make made makes making get gets got
let lets use used using want wants need needs like please okay yes now new old
one two three more most less very really still even only over under again back
out off about after before while because same other another such way ways thing
things stuff work works working run runs running check checks look looks find
fix fixes build builds show shows tell give take put set see seen go going
start started stop keep kept try tried add added change changed today tomorrow
yesterday next last first time times day days week claude codex agent agents
session sessions prompt prompts file files page pages line lines repo repos
code code's project projects task tasks note notes doc docs
fail fails failing failed error errors bug bugs module modules function functions
method methods class classes test tests issue issues help write writing
""".split())

_MAX_UNIT_CHARS = 4000
_EXCERPT_CHARS = 420


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _private(text: str) -> bool:
    """For PATHS: the store-wide privacy pattern (journal, finance, wallet...)."""
    from helicon.cockpit import PRIVATE_RX
    return bool(PRIVATE_RX.search(text or ""))


# For TEXT the path pattern is the wrong tool: a rule page that says "finance
# files never go on the shelf" is about privacy, not private, and the path
# pattern dropped it. Text is refused only when it carries a secret's shape.
_SECRET_TEXT = re.compile(
    r"seed.?phrase|private.?key|password\s*[:=]|\b0x[0-9a-fA-F]{40}\b|"
    r"\bIBAN\b|\bsk-[A-Za-z0-9]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY", re.I)


_EXCLUDE: dict = {}


def _secret(text: str, exclude: str = "") -> bool:
    if _SECRET_TEXT.search(text or ""):
        return True
    if exclude:
        rx = _EXCLUDE.get(exclude)
        if rx is None:
            rx = _EXCLUDE[exclude] = re.compile(exclude, re.I)
        return bool(rx.search(text or ""))
    return False


_CHUNK = 700


def _chunks(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Long sections split into ~700-char pieces at a blank line or a list
    item, each keeping the line number it starts on, so a pointer lands on
    the rule and not on the top of a long page."""
    out, cur, start, size = [], [], None, 0
    for n, ln in lines:
        boundary = (not ln.strip()) or re.match(r"\s*(?:[-*]|\d+\.|\|)\s", ln)
        if cur and size >= _CHUNK and boundary:
            out.append((start, "\n".join(cur).strip()))
            cur, start, size = [], None, 0
        if not cur and not ln.strip():
            continue
        if start is None:
            start = n
        cur.append(ln)
        size += len(ln) + 1
    if cur:
        out.append((start, "\n".join(cur).strip()))
    return [c for c in out if c[1]]


def settings(config: dict | None) -> dict:
    """The lookup block of a config, normalised. Empty sources means off."""
    raw = dict((config or {}).get("lookup") or {})
    store = (config or {}).get("db_path") or "~/.helicon/helicon.db"
    default_db = os.path.join(os.path.dirname(os.path.expanduser(store)), "lookup.db")
    return {
        "enabled": bool(raw.get("enabled", True)),
        "db_path": os.path.expanduser(raw.get("db_path") or default_db),
        "pages": [os.path.expanduser(p) for p in raw.get("pages") or []],
        "rulings": [os.path.expanduser(p) for p in raw.get("rulings") or []],
        # Extra words that keep a unit out of the index, on top of secret
        # shapes. An operator's own career, money or diary topics belong here.
        "exclude_text": str(raw.get("exclude_text") or ""),
        # Rule pages that NAME those topics as rules ("finance files never go
        # on the shelf") and hold no such data. Exempt from exclude_text only;
        # the secret-shape check still applies.
        "trusted_pages": [os.path.expanduser(p) for p in raw.get("trusted_pages") or []],
        # Index a ruling only when it says private: false outright. A row
        # with no flag is unknown, and unknown is not public.
        "rulings_require_public_flag": bool(raw.get("rulings_require_public_flag", True)),
        "min_terms": int(raw.get("min_terms", 2)),
        "max_prompt_words": int(raw.get("max_prompt_words", 40)),
        "rare_df": float(raw.get("rare_df", 0.02)),
        # Share of the prompt's weight (sum of log N/df over its live words)
        # the unit must carry. Stops two rare-ish words from dragging in a
        # unit that misses what the prompt is mainly about.
        "min_cover": float(raw.get("min_cover", 0.45)),
        # Pages are the canonical map; a ruling is one fact. Equal evidence
        # goes to the page.
        "page_weight": float(raw.get("page_weight", 1.3)),
    }


def _source_files(cfg: dict) -> list[str]:
    out = []
    for pattern in cfg["pages"]:
        for path in sorted(glob.glob(pattern, recursive=True)):
            if os.path.isfile(path) and path.endswith(".md") and not _private(path):
                out.append(path)
    for path in cfg["rulings"]:
        if os.path.isfile(path) and not _private(path):
            out.append(path)
    return sorted(set(out))


def manifest(cfg: dict) -> str:
    """Size and mtime of every source. Any edit moves it; a stat is cheap."""
    parts = []
    for path in _source_files(cfg):
        try:
            st = os.stat(path)
            parts.append(f"{path}:{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            parts.append(f"{path}:missing")
    parts.append("pages=" + "|".join(cfg["pages"]))
    parts.append("rulings=" + "|".join(cfg["rulings"]))
    parts.append(f"exclude={cfg['exclude_text']}|flag={cfg['rulings_require_public_flag']}"
                 f"|trusted={'|'.join(cfg['trusted_pages'])}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:32]


# --------------------------------------------------------------------------
# building the index
# --------------------------------------------------------------------------

def _page_units(path: str, exclude: str = "") -> list[dict]:
    """A page split at its headings, and long sections split again into
    ~700-char pieces. The page title is the first # heading, else the file
    name. Frontmatter is skipped."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    title = os.path.splitext(os.path.basename(path))[0]
    units, heading, buf = [], "", []

    def flush():
        for start, body in _chunks(buf):
            if _secret(body, exclude) or _secret(heading, exclude):
                continue
            units.append({"kind": "page", "path": path, "line": start,
                          "title": title, "heading": heading,
                          "body": body[:_MAX_UNIT_CHARS], "ts": ""})

    in_front = bool(lines) and lines[0].strip() == "---"
    for n, line in enumerate(lines, 1):
        if in_front:
            if n > 1 and line.strip() == "---":
                in_front = False
            continue
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1 and not units and not any(l.strip() for _, l in buf):
            title = m.group(2)
            continue
        if m:
            flush()
            heading, buf = m.group(2), []
            continue
        buf.append((n, line))
    flush()
    return units


def _ruling_units(path: str, exclude: str = "",
                  require_public_flag: bool = True) -> list[dict]:
    units = []
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return units
    with fh:
        for n, raw in enumerate(fh, 1):
            try:
                r = json.loads(raw)
            except ValueError:
                continue
            text = str(r.get("text") or "").strip()
            if not text or r.get("private"):
                continue
            if require_public_flag and r.get("private") is not False:
                continue
            if str(r.get("value") or "").lower() in ("superseded", "retired", "void"):
                continue
            if _secret(text, exclude) or _secret(str(r.get("title") or ""), exclude):
                continue
            units.append({"kind": "ruling", "path": path, "line": n,
                          "title": str(r.get("title") or r.get("repo") or ""),
                          "heading": "", "body": text[:_MAX_UNIT_CHARS],
                          "ts": str(r.get("ts") or "")})
    return units


def build(cfg: dict) -> dict:
    """Rebuild the index from scratch into a temp file, then swap it in, so a
    reader never sees a half-built index."""
    os.makedirs(os.path.dirname(cfg["db_path"]) or ".", exist_ok=True)
    tmp = cfg["db_path"] + f".build-{os.getpid()}"
    if os.path.exists(tmp):
        os.unlink(tmp)
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE TABLE units (id INTEGER PRIMARY KEY, kind TEXT, path TEXT, "
                 "line INTEGER, title TEXT, heading TEXT, body TEXT, ts TEXT)")
    conn.execute("CREATE VIRTUAL TABLE units_fts USING fts5(title, heading, body, "
                 "content='units', content_rowid='id', tokenize='porter unicode61')")
    n = 0
    for path in _source_files(cfg):
        trusted = any(path in glob.glob(t, recursive=True) for t in cfg["trusted_pages"])
        units = (_ruling_units(path, cfg["exclude_text"], cfg["rulings_require_public_flag"])
                 if path.endswith(".jsonl")
                 else _page_units(path, "" if trusted else cfg["exclude_text"]))
        for u in units:
            cur = conn.execute(
                "INSERT INTO units (kind, path, line, title, heading, body, ts) "
                "VALUES (?,?,?,?,?,?,?)",
                (u["kind"], u["path"], u["line"], u["title"], u["heading"],
                 u["body"], u["ts"]))
            conn.execute("INSERT INTO units_fts (rowid, title, heading, body) "
                         "VALUES (?,?,?,?)",
                         (cur.lastrowid, u["title"], u["heading"], u["body"]))
            n += 1
    conn.executemany("INSERT INTO meta (k, v) VALUES (?,?)",
                     [("manifest", manifest(cfg)), ("built_at", _now_iso()),
                      ("units", str(n))])
    conn.commit()
    conn.close()
    os.replace(tmp, cfg["db_path"])
    return {"units": n, "db_path": cfg["db_path"]}


def _index_manifest(db_path: str) -> str | None:
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute("SELECT v FROM meta WHERE k='manifest'").fetchone()
        conn.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def refresh_in_background(cfg: dict, every_s: float = 60.0) -> str:
    """Keep the index fresh without ever costing the prompt.

    Walking the page globs costs about a second on a large vault, so the
    prompt does none of it. It looks at one stamp file; if the last check is
    older than `every_s` (or there is no index), it starts a detached process
    that compares the sources and rebuilds only if they moved.
    Returns "checked-recently", "started", "running" or "failed"."""
    stamp = cfg["db_path"] + ".checked"
    try:
        if (os.path.exists(cfg["db_path"])
                and time.time() - os.path.getmtime(stamp) < every_s):
            return "checked-recently"
    except OSError:
        pass
    lock = os.path.join(tempfile.gettempdir(), "helicon-lookup-"
                        + hashlib.sha256(cfg["db_path"].encode()).hexdigest()[:16]
                        + ".lock")
    try:
        if time.time() - os.path.getmtime(lock) < 300:
            return "running"
        os.unlink(lock)
    except OSError:
        pass
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return "running"
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONSAFEPATH="1")
    env["PYTHONPATH"] = pkg_root + (os.pathsep + env["PYTHONPATH"]
                                    if env.get("PYTHONPATH") else "")
    try:
        subprocess.Popen(
            [sys.executable, "-c",
             "import sys, json; from helicon.lookup import _build_main; "
             "_build_main(json.loads(sys.argv[1]), sys.argv[2])",
             json.dumps(cfg), lock],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
            env=env)
    except OSError:
        try:
            os.unlink(lock)
        except OSError:
            pass
        return "failed"
    return "started"


def is_fresh(cfg: dict) -> bool:
    """Slow (walks the globs). For the background process and for tests."""
    return _index_manifest(cfg["db_path"]) == manifest(cfg)


def _build_main(cfg: dict, lock: str) -> None:
    try:
        if not is_fresh(cfg):
            build(cfg)
        stamp = cfg["db_path"] + ".checked"
        with open(stamp, "w") as fh:
            fh.write(_now_iso())
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass


# --------------------------------------------------------------------------
# the lookup
# --------------------------------------------------------------------------

_PATHLIKE = re.compile(r"(?:https?://|~/|/)[^\s`'\"<>)]*|<[^>]{1,80}>|\S+\.(?:md|py|ts|json|jsonl|txt|sh)\b")


def content_count(prompt: str) -> int:
    """Distinct content words, uncapped. A long paste is a brief to read,
    not a question to answer, and matching it finds its boilerplate."""
    text = _PATHLIKE.sub(" ", prompt or "")
    return len({w.lower() for w in _WORD.findall(text) if w.lower() not in _STOP})


def prompt_terms(prompt: str) -> list[str]:
    """Content words of the prompt, lowercased, in order, without repeats.
    File paths, URLs and tags are cut first: their folder names are not what
    the prompt is about."""
    seen, out = set(), []
    for w in _WORD.findall(_PATHLIKE.sub(" ", prompt or "")):
        t = w.lower().strip("-_")
        if len(t) < 3 or t in _STOP or t.isdigit() or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:24]


def _age_factor(ts: str) -> float:
    """1.0 for a ruling up to 14 days old, falling to 0.6 at 90 days. Newer
    rulings replace older ones far more often than the reverse."""
    if not ts:
        return 0.6
    try:
        from datetime import datetime, timezone
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - when).total_seconds() / 86400
    except ValueError:
        return 0.6
    if days <= 14:
        return 1.0
    return max(0.6, 1.0 - 0.4 * (days - 14) / 76)


def _fts_quote(term: str) -> str:
    return '"' + term.replace('"', "") + '"'


def best(cfg: dict, prompt: str, exclude: set | None = None) -> dict | None:
    """The one unit that matters for this prompt, or None.

    Scoring is plain on purpose, so a reader can check it: each prompt word
    that appears in the unit adds its rarity (log N/df). A unit needs
    `min_terms` distinct prompt words and at least one word found in fewer
    than `rare_df` of all units. Ties go to the newest ruling, then the
    better FTS rank."""
    if content_count(prompt) > cfg["max_prompt_words"]:
        return None
    terms = prompt_terms(prompt)
    if len(terms) < cfg["min_terms"] or not os.path.exists(cfg["db_path"]):
        return None
    try:
        conn = sqlite3.connect(f"file:{cfg['db_path']}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    conn.row_factory = sqlite3.Row
    try:
        total = int(conn.execute("SELECT v FROM meta WHERE k='units'").fetchone()[0] or 0)
        if total <= 0:
            return None
        df = {}
        for t in terms:
            df[t] = conn.execute("SELECT count(*) FROM units_fts WHERE units_fts MATCH ?",
                                 (_fts_quote(t),)).fetchone()[0]
        live = [t for t in terms if df[t] > 0]
        if len(live) < cfg["min_terms"]:
            return None
        weight_all = sum(math.log(total / df[t]) for t in live)
        query = " OR ".join(_fts_quote(t) for t in live)
        rows = conn.execute(
            "SELECT u.id, u.kind, u.path, u.line, u.title, u.heading, u.body, u.ts, "
            "bm25(units_fts, 4.0, 3.0, 1.0) AS rank FROM units_fts "
            "JOIN units u ON u.id = units_fts.rowid WHERE units_fts MATCH ? "
            "ORDER BY rank LIMIT 60", (query,)).fetchall()
        exclude = exclude or set()
        scored = []
        for r in rows:
            key = f"{r['path']}:{r['line']}"
            if key in exclude:
                continue
            matched = []
            for t in live:
                hit = conn.execute(
                    "SELECT 1 FROM units_fts WHERE rowid = ? AND units_fts MATCH ?",
                    (r["id"], _fts_quote(t))).fetchone()
                if hit:
                    matched.append(t)
            if len(matched) < cfg["min_terms"]:
                continue
            if not any(df[t] <= max(1.0, cfg["rare_df"] * total) for t in matched):
                continue
            raw = sum(math.log(total / df[t]) for t in matched)
            if raw < cfg["min_cover"] * weight_all:
                continue
            score = raw * (cfg["page_weight"] if r["kind"] == "page"
                           else _age_factor(r["ts"]))
            scored.append((score, r["ts"] or "", -r["rank"], r, matched))
        if not scored:
            return None
        scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        score, _ts, _rank, r, matched = scored[0]
        return {"kind": r["kind"], "path": r["path"], "line": r["line"],
                "title": r["title"], "heading": r["heading"], "body": r["body"],
                "ts": r["ts"], "score": round(score, 2), "matched": matched,
                "key": f"{r['path']}:{r['line']}"}
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def excerpt(hit: dict, terms: list[str]) -> str:
    """The lines of the unit that carry the most prompt words, capped."""
    lines = [ln.strip() for ln in hit["body"].splitlines() if ln.strip()]
    if not lines:
        return ""
    low = [t.lower() for t in terms]

    def weight(ln: str) -> int:
        l = ln.lower()
        return sum(1 for t in low if t[:5] in l)

    top = max(range(len(lines)), key=lambda i: weight(lines[i]))
    out, size = [], 0
    for ln in lines[top:top + 4]:
        if size + len(ln) > _EXCERPT_CHARS and out:
            break
        out.append(ln[:_EXCERPT_CHARS])
        size += len(ln)
    return "\n".join(out)


def render(hit: dict, prompt: str) -> str:
    """The text injected into the session: a pointer plus the matching lines."""
    where = f"{hit['path']}:{hit['line']}"
    if hit["kind"] == "ruling":
        head = (f"## Helicon: the ruling for this prompt\n"
                f"Ruling ({hit['ts'][:10] or 'undated'}), {where}")
    else:
        sect = f" § {hit['heading']}" if hit["heading"] else ""
        head = (f"## Helicon: the page for this prompt\n"
                f"{hit['title']}{sect}, {where}")
    return (f"{head}\n{excerpt(hit, prompt_terms(prompt))}\n"
            f"(matched on: {', '.join(hit['matched'])}. Read the source before "
            f"you act on it; this is a pointer, not the whole page.)")
