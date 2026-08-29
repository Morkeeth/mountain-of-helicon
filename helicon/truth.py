"""helicon truth — point it at ANY agent's memory/notes store, get a ranked,
evidence-cited staleness+rot report in one command. No key, no LLM, no DB.

Where `helicon inventory` (inventory.py) ranks *Helicon's own* memory by JOINing
the cube DB, `truth` is the stranger-facing product: it works COLD on any
directory of markdown and/or jsonl files — a Claude Code / Cursor / Cline memory
dir, a shared AGENTS.md pile, an Obsidian vault dashboard — with zero Helicon
state. Everything it needs it reads off the disk.

The staleness fix (see DIAGNOSIS.md): Helicon's shipped decay score measures
days-since-INGEST, not staleness, because `last_reinforced` is only written on a
human review. `truth` never touches that signal. It measures real staleness from
the file system and the document's own self-declared freshness:

  1. stamp-stale        — a frontmatter as_of/date/updated stamp OLDER than the
                          file's own mtime: the page was edited but its freshness
                          stamp was not, so the stamp lies. (The SLASK failure.)
  2. freshness-rule     — the page states its own rule ("stale if not touched
                          today", "refresh daily") and mtime is past that window.
  3. claims-live-stale  — status: live/active, but the stamp/mtime is weeks old.
  4. retired-but-live   — status/first-line says RETIRED/SUPERSEDED/KILLED/PARKED/
                          DEPRECATED, yet the file is still on disk (still loaded).
  5. expired-date       — a deadline/freeze date in the body now in the past.
  6. superseded-term    — a term a NEWER file in the store bans or renames, still
                          used by an OLDER file ("never call it X"; "renamed X→Y").
  7. stale-on-disk      — mtime far below the store's active band (weak context).

Deterministic and cheap: hundreds of files rank in <1s and every row cites the
exact line it fired on. Redaction is ON by default for any file that looks
personal or is mode-600, so a report written to a repo never leaks a body.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, date, timedelta
from glob import glob

# --- self-declared freshness stamps in frontmatter -------------------------
# Real vault formats seen: "2026-08-25 evening", "2026-08-12 ~19:35",
# "2026-08-10T14:54:00+02:00", "2026-07-06". Extract the leading ISO date and
# ignore whatever trails it.
_STAMP_KEYS = ("as_of", "as of", "date", "updated", "last_updated", "last-updated",
               "refreshed", "last_reviewed", "last-reviewed")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# self-declared freshness windows, e.g. SLASK "Stale if not touched today"
_FRESH_RULE = re.compile(
    r"stale if not touched (?P<today>today)"
    r"|(?:refresh(?:ed)?|update[d]?|touch(?:ed)?)\s+(?:it\s+)?(?P<daily>daily|every day|each day)"
    r"|(?:refresh(?:ed)?|update[d]?)\s+(?:it\s+)?(?P<weekly>weekly|every week)",
    re.I,
)

_LIVE = re.compile(r"^\s*(live|active|current|canonical)\b", re.I)
_RETIRED = re.compile(
    r"\b(RETIRED|SUPERSEDED|SUPERCEDED|DEPRECATED|KILLED|ABANDONED|PARKED|OBSOLETE|ARCHIVED|DO NOT UPDATE)\b"
)

# --- expired dated claims in the body (deadlines / freezes) ----------------
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DATED = re.compile(
    r"(?P<phrase>(?:till|until|by|before|closes?|deadline|due|frozen till|"
    r"expires?|ends?|submit(?:ted)? by)\b[^.\n]{0,40}?"
    r"(?:(?P<m1>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s\-]+(?P<d1>\d{1,2})"
    r"|(?P<d2>\d{1,2})[\s\-]+(?P<m2>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)))",
    re.I,
)

# --- supersession: a newer file bans a term an older file still uses ---------
# HIGH-PRECISION ONLY. In this corpus "→" is prose flow ("comment → prompt"),
# not a rename, so a bare-arrow pattern is pure noise (it produced 'work→route',
# 'file→the'). We only accept a naming PROHIBITION whose term is QUOTED — that is
# how a real ruling is written: never call anything a "ledger"; don't use the
# word "ledger". The quote requirement is what keeps this from crying wolf.
_BAN = re.compile(
    r"(?:never (?:call|name)[^\"'\n]{0,24}|"
    r"(?:don'?t|do not|never|avoid|stop) (?:use|using|say|writ)[^\"'\n]{0,20}|"
    r"banned[^\"'\n]{0,10}|forbidden[^\"'\n]{0,10})"
    r"[\"'`“‘](?P<term>[A-Za-z][\w -]{1,24})[\"'`”’]",
    re.I,
)
# terms too generic to ever flag even if quoted
_STOPTERMS = {"it", "the", "a", "an", "this", "that", "them", "one", "on", "in",
              "to", "is", "word", "term", "name", "generic"}

# curated dead names (a rename everyone in the store should have adopted). An
# OLDER file using the dead name without the live name present = drift.
_DEAD_NAMES = {"RELAY": "FAVOUR"}

# --- personal-data redaction (body never leaves the machine) ---------------
_PERSONAL = re.compile(
    r"finance|wallet|portfolio|hl_dashboard|receipt|journal|salary|"
    r"yieldbound|rekt|okx_oracle|earned_supply|bank|passport|ssn|seed phrase",
    re.I,
)
# labels whose evidence is pure filesystem metadata → always safe to print
_SAFE_LABELS = ("retired-but-live", "stamp-stale", "claims-live", "freshness-rule",
                "stale-on-disk", "superseded-term", "never ingested")


def _parse_frontmatter(text: str) -> tuple[dict, str, int]:
    """Return (frontmatter dict, body, body_start_line). No yaml dependency."""
    if not text.startswith("---"):
        return {}, text, 0
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text, 0
    head = text[3:end]
    body = text[end + 4:]
    fm: dict = {}
    for line in head.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, _, v = line.partition(":")
            fm[k.strip().lower()] = v.strip()
    body_start = head.count("\n") + 2
    return fm, body, body_start


def _stamp_date(fm: dict) -> tuple[date | None, str, str]:
    """The document's self-declared freshness date: (date, key, raw value)."""
    for k in _STAMP_KEYS:
        if k in fm:
            m = _ISO_DATE.search(fm[k])
            if m:
                try:
                    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), k, fm[k][:60]
                except ValueError:
                    continue
    return None, "", ""


def _first_lines(body: str, n: int = 6) -> str:
    out = []
    for line in body.splitlines():
        s = line.strip()
        if s:
            out.append(s)
        if len(out) >= n:
            break
    return "\n".join(out)


def _first_line(body: str) -> str:
    for line in body.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:100]
    return ""


def _dated_claims(body: str, today: date) -> list[dict]:
    out = []
    for m in _DATED.finditer(body):
        mon = (m.group("m1") or m.group("m2") or "").lower()
        day = m.group("d1") or m.group("d2")
        if not mon or not day:
            continue
        month = _MONTHS.get(mon[:4]) or _MONTHS.get(mon[:3])
        if not month:
            continue
        try:
            claim = date(today.year, month, int(day))
        except ValueError:
            continue
        # same-year past only; guessing "last year" for a far-future month+day is
        # a coin flip that mis-reports. Under-report over mis-report.
        if claim < today:
            phrase = re.sub(r"\s+", " ", m.group("phrase")).strip()
            out.append({"date": claim.isoformat(), "days_past": (today - claim).days,
                        "quote": phrase[:90]})
    seen, uniq = set(), []
    for c in out:
        if c["quote"] not in seen:
            seen.add(c["quote"])
            uniq.append(c)
    return uniq


def _is_personal(fp: str, fm: dict) -> bool:
    if _PERSONAL.search(os.path.basename(fp)):
        return True
    try:
        mode = os.stat(fp).st_mode
        # owner-only file (0600 / 0700) → treat as personal
        if not (mode & (stat.S_IRGRP | stat.S_IROTH)):
            return True
    except OSError:
        pass
    return False


# ---------------------------------------------------------------------------
# supersession map: scan the whole store once for terms a file bans / renames.
# Each ruling is tagged with the declaring file's mtime so we only flag OLDER
# files that still use the term.
# ---------------------------------------------------------------------------
def _build_supersession(records: list[dict]) -> dict:
    """term(lower) -> {'replacement': str|None, 'src': filename, 'mtime': datetime}.

    A file that states a quoted naming ban ('never call it "ledger"') supersedes
    any OLDER file still using that term. Frontmatter description + first ~800
    chars only, where rulings live."""
    bans: dict = {}
    for rec in records:
        head = " ".join(rec["fm"].values()) + "\n" + rec["body"][:800]
        for m in _BAN.finditer(head):
            term = m.group("term").strip().lower().strip(".,:;\"'` -")
            if not term or term in _STOPTERMS or len(term) < 3 or " " in term:
                continue
            cur = bans.get(term)
            if not cur or rec["mtime"] > cur["mtime"]:
                bans[term] = {"replacement": None, "src": rec["file"], "mtime": rec["mtime"]}
    return bans


def _read_markdown(fp: str) -> dict | None:
    try:
        text = open(fp, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    fm, body, _ = _parse_frontmatter(text)
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(fp))
    except OSError:
        mtime = datetime.now()
    return {"file": os.path.basename(fp), "path": fp, "fm": fm, "body": body,
            "mtime": mtime, "kind": "md"}


def _read_jsonl(fp: str) -> list[dict]:
    """A jsonl memory store (Cursor/Cline style): one record per line. Each record
    is treated as a mini-document with a text field and, if present, a timestamp."""
    out = []
    try:
        lines = open(fp, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return out
    file_mtime = datetime.fromtimestamp(os.path.getmtime(fp)) if os.path.exists(fp) else datetime.now()
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        # find a text-ish field and a timestamp-ish field, format-agnostic
        text = ""
        for tk in ("text", "content", "body", "memory", "message", "value", "note", "summary"):
            if isinstance(obj.get(tk), str):
                text = obj[tk]
                break
        stamp = None
        for sk in ("date", "timestamp", "ts", "created_at", "updated_at", "as_of", "time"):
            v = obj.get(sk)
            if isinstance(v, str):
                m = _ISO_DATE.search(v)
                if m:
                    try:
                        stamp = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    except ValueError:
                        pass
                    break
        out.append({"file": f"{os.path.basename(fp)}#L{i}", "path": fp, "fm": {},
                    "body": text, "mtime": file_mtime, "kind": "jsonl",
                    "record_stamp": stamp})
    return out


def scan_store(path: str, today: date | None = None, include_archive: bool = False,
               recursive: bool = False) -> dict:
    """Rank every file in an agent memory/notes store by real staleness+rot.

    path: a directory of *.md / *.jsonl files, or a single such file. No Helicon
          DB, config, or key required — this reads only the disk.
    """
    today = today or date.today()
    path = os.path.expanduser(path)

    if os.path.isfile(path):
        md_files = [path] if path.endswith((".md", ".markdown")) else []
        jsonl_files = [path] if path.endswith((".jsonl", ".ndjson")) else []
        base = os.path.dirname(path)
    elif os.path.isdir(path):
        pat = "**/*" if recursive else "*"
        md_files = sorted(glob(os.path.join(path, f"{pat}.md"), recursive=recursive))
        jsonl_files = sorted(glob(os.path.join(path, f"{pat}.jsonl"), recursive=recursive))
        jsonl_files += sorted(glob(os.path.join(path, f"{pat}.ndjson"), recursive=recursive))
        base = path
    else:
        return {"error": f"not a file or directory: {path!r}", "items": []}

    if not include_archive:
        md_files = [f for f in md_files if os.sep + "archive" + os.sep not in f]

    # index file (MEMORY.md / README / AGENTS.md) for orphan context, if present
    index_text = ""
    for idx_name in ("MEMORY.md", "AGENTS.md", "index.md", "README.md"):
        idxp = os.path.join(base, idx_name)
        if os.path.isfile(idxp):
            try:
                index_text += "\n" + open(idxp, encoding="utf-8", errors="replace").read()
            except OSError:
                pass

    # -- load records --
    records: list[dict] = []
    for fp in md_files:
        if os.path.basename(fp) in ("MEMORY.md", "AGENTS.md"):
            continue
        rec = _read_markdown(fp)
        if rec:
            records.append(rec)
    jsonl_records: list[dict] = []
    for fp in jsonl_files:
        jsonl_records.extend(_read_jsonl(fp))

    # store's active band: the freshest file's age is the reference point
    all_mtimes = [r["mtime"] for r in records] or [datetime.now()]
    newest = max(all_mtimes)

    supersession = _build_supersession(records)

    items = []
    for rec in records:
        items.append(_score_md(rec, today, newest, index_text, supersession))
    # jsonl records: score the past-dated / stale ones
    for rec in jsonl_records:
        it = _score_jsonl(rec, today)
        if it:
            items.append(it)

    items.sort(key=lambda it: (-it["score"], -it["age_days"]))
    for i, it in enumerate(items, 1):
        it["rank"] = i

    return {
        "path": path,
        "total": len(items),
        "flagged": sum(1 for it in items if it["score"] > 0),
        "clean": sum(1 for it in items if it["score"] == 0),
        "items": items,
        "today": today.isoformat(),
        "newest_mtime": newest.date().isoformat(),
    }


def _score_md(rec: dict, today: date, newest: datetime, index_text: str,
              supersession: dict) -> dict:
    fp, fm, body = rec["path"], rec["fm"], rec["body"]
    fn = rec["file"]
    mtime = rec["mtime"]
    age_days = (datetime.now() - mtime).days
    reasons: list[tuple] = []
    personal = _is_personal(fp, fm)

    stamp, stamp_key, stamp_raw = _stamp_date(fm)
    mtime_d = mtime.date()

    # 1. stamp-stale: the self-declared freshness date is OLDER than the file's
    #    own mtime. The page was edited; its freshness stamp was not. The stamp lies.
    if stamp and stamp < mtime_d:
        gap = (mtime_d - stamp).days
        if gap >= 3:  # a day or two of lag is noise
            reasons.append((min(45, 8 + gap),
                            f"stamp-stale ({stamp_key} says {stamp.isoformat()}, file edited {mtime_d.isoformat()} — {gap}d newer)",
                            f"{stamp_key}: {stamp_raw}"))

    # how stale is the declared/actual freshness against TODAY
    ref_date = stamp or mtime_d
    days_since_fresh = (today - ref_date).days

    # 2. self-declared freshness rule violated
    fr = _FRESH_RULE.search(body[:400]) or _FRESH_RULE.search(" ".join(fm.values()))
    if fr:
        window = 1 if fr.group("today") or fr.group("daily") else 7
        if days_since_fresh > window:
            reasons.append((min(40, 10 + days_since_fresh),
                            f"freshness-rule violated (page's own rule: refresh "
                            f"{'daily' if window == 1 else 'weekly'}; {days_since_fresh}d since fresh)",
                            (fr.group(0) or "")[:80]))

    # 3. claims live but the stamp/mtime is weeks old
    status = fm.get("status", "")
    if _LIVE.match(status) or _LIVE.search(_first_line(body)):
        if days_since_fresh > 21:
            reasons.append((min(30, 6 + days_since_fresh // 3),
                            f"claims-live but stale ({days_since_fresh}d since {'stamp' if stamp else 'edit'})",
                            f"status/first-line asserts live; freshness ref {ref_date.isoformat()}"))

    # 4. retired-but-live: status/first-lines mark it dead, file still on disk
    head = (status + "\n" + _first_lines(body, 4))
    rmatch = _RETIRED.search(head)
    if rmatch:
        reasons.append((38, f"retired-but-live ({rmatch.group(1).upper()} marker, file still on disk)",
                        _first_line(status if _RETIRED.search(status) else body)))

    # 5. expired dated claims in the body
    for c in _dated_claims(body, today):
        reasons.append((min(30, 12 + c["days_past"] // 10),
                        f"expired dated claim ({c['days_past']}d past, {c['date']})",
                        c["quote"]))

    # 6. superseded term: uses a term a NEWER file bans
    low_head = body[:800].lower()
    for term, ban in supersession.items():
        if ban["src"] == fn:
            continue  # the declaring file itself
        if mtime >= ban["mtime"]:
            continue  # only OLDER files are contradicted by the newer ruling
        if re.search(r"\b" + re.escape(term) + r"\b", low_head):
            reasons.append((15, f"superseded-term ('{term}' banned by newer {ban['src']})",
                            f"still uses '{term}'; {ban['src']} (newer) bans that word"))

    # curated dead-name rename (e.g. RELAY→FAVOUR): old name used, new name absent
    for dead, live_name in _DEAD_NAMES.items():
        if re.search(r"\b" + re.escape(dead) + r"\b", body) and live_name.lower() not in body.lower():
            reasons.append((15, f"dead-name reference ({dead}→{live_name})",
                            f"uses '{dead}', never '{live_name}'"))

    # 7. stale-on-disk relative to the store's freshest file (weak context)
    store_gap = (newest.date() - mtime_d).days
    is_hard = bool(re.search(r"\bHARD\b|eternal|always|never lift|canonical", body[:400]))
    if store_gap > 30 and not reasons:
        pts = 5 if is_hard else 8
        reasons.append((pts, f"stale-on-disk ({store_gap}d behind the store's freshest file)"
                        + (" [HARD/eternal — down-weighted]" if is_hard else ""),
                        f"mtime {mtime_d.isoformat()} vs newest {newest.date().isoformat()}"))

    score = sum(p for p, _, _ in reasons)
    # eternal HARD rules: shave the pure-age contribution so they don't dominate
    if is_hard:
        score = int(score * 0.7)

    return {
        "file": fn, "path": fp, "kind": "md", "score": score,
        "age_days": age_days, "mtime": mtime_d.isoformat(),
        "stamp": stamp.isoformat() if stamp else None,
        "reasons": sorted(reasons, key=lambda r: -r[0]),
        "personal": personal, "title": _first_line(body),
    }


def _score_jsonl(rec: dict, today: date) -> dict | None:
    body = rec["body"]
    stamp = rec.get("record_stamp")
    reasons = []
    if stamp:
        days = (today - stamp).days
        for c in _dated_claims(body, today):
            reasons.append((min(30, 12 + c["days_past"] // 10),
                            f"expired dated claim in record ({c['days_past']}d past)",
                            c["quote"]))
    for c in _dated_claims(body, today):
        if not any("expired dated claim in record" in r[1] for r in reasons):
            reasons.append((min(30, 12 + c["days_past"] // 10),
                            f"expired dated claim in record ({c['days_past']}d past)",
                            c["quote"]))
    rmatch = _RETIRED.search(body[:200])
    if rmatch:
        reasons.append((25, f"retired marker in record ({rmatch.group(1).upper()})",
                        _first_line(body)))
    if not reasons:
        return None
    mtime_d = rec["mtime"].date()
    return {
        "file": rec["file"], "path": rec["path"], "kind": "jsonl",
        "score": sum(p for p, _, _ in reasons),
        "age_days": (datetime.now() - rec["mtime"]).days, "mtime": mtime_d.isoformat(),
        "stamp": stamp.isoformat() if stamp else None,
        "reasons": sorted(reasons, key=lambda r: -r[0]),
        "personal": _PERSONAL.search(rec["path"] or "") is not None,
        "title": _first_line(body),
    }


def _redact_ev(personal: bool, label: str, ev: str) -> str:
    if label.startswith(_SAFE_LABELS):
        return ev
    if personal:
        return "[redacted: personal/owner-only file — evidence visible in live terminal only]"
    return ev


def format_report(res: dict, top: int | None = None, min_score: int = 1,
                  redact: bool = True) -> str:
    if res.get("error"):
        return f"truth: {res['error']}"
    items = [it for it in res["items"] if it["score"] >= min_score]
    shown = items[:top] if top else items
    L = []
    L.append(f"STALENESS + ROT REPORT — {res['path']}")
    L.append(f"{res['total']} files scanned · {res['flagged']} carry a staleness/rot signal · "
             f"{res.get('clean', 0)} clean · as of {res['today']}")
    L.append(f"Freshest file in store: {res.get('newest_mtime', '?')}. "
             f"Signals read from disk only — no DB, no key, no LLM.")
    L.append("Signals: stamp-stale · freshness-rule · claims-live-but-stale · "
             "retired-but-live · expired-date · superseded-term.")
    if redact:
        L.append("Redaction ON: owner-only/personal file bodies shown as metadata only.")
    L.append("")
    L.append(f"{'#':>3}  {'SCORE':>5}  {'AGE':>5}  FILE")
    L.append("  " + "-" * 76)
    for it in shown:
        L.append(f"{it['rank']:>3}  {it['score']:>5}  {it['age_days']:>4}d  {it['file']}")
        for pts, label, ev in it["reasons"][:4]:
            L.append(f"          +{pts:<3} {label}")
            if ev:
                shown_ev = _redact_ev(it.get("personal", False), label, ev) if redact else ev
                shown_ev = re.sub(r"\s+", " ", shown_ev).strip()
                L.append(f"                └ {shown_ev}")
    if top and len(items) > top:
        L.append("")
        L.append(f"… {len(items) - top} more flagged below (rerun without --top for the full report).")
    if not shown:
        L.append("  (nothing above the score threshold — store looks fresh.)")
    return "\n".join(L)
