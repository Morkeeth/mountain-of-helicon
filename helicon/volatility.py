"""The volatility gate — truth = fact + timestamp + decay.

Memory does not rot because it is stored wrong. It rots because facts are
stored without their volatility. A fact earns a place in long-term memory only
if it is durable; a fast fact (a %, a live count, a price, a ranking,
"currently / this week") goes wrong in days and belongs in the live layer
(a dashboard) or gets re-fetched, never in a memory file.

Three tiers:
  - static: never decays (heritage, birthdate, values, "3x founder").
  - slow:   decays over months, invalidated by a named event (job title,
            canonical numbers, stack choice). Earns a memory file IF it
            carries `as_of` + `stale_when`.
  - fast:   decays in days. Does not belong in memory at all.

Two stages, honest about cost:
  1. deterministic pre-filter (free) — flag cubes whose text carries a
     fast-fact SIGNAL. High recall, no judgment, no false confidence.
  2. Qwen classifier (paid, cached) — sentence each suspect: tier, a one-line
     reason, and the named event that would make it wrong (`stale_when`).

Only the suspects reach the model, so the scan stays cheap. Keyless degrade is
honest: with no Qwen key we surface the deterministic suspects and say plainly
that they are unsentenced, rather than faking a tier.
"""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

# Fast-fact signals: the vocabulary of facts that go wrong in days. High recall
# on purpose — the model does the sentencing, this just rounds up suspects.
_SIGNALS = [
    (re.compile(r"\b\d+(?:\.\d+)?\s?%"), "percentage"),
    (re.compile(r"[$€£]\s?\d"), "price"),
    (re.compile(r"\b\d[\d,]*\s?(?:SEK|USD|EUR|GBP|k|K|million|billion|M|B)\b"), "money/quantity"),
    (re.compile(r"\b(?:currently|right now|this week|today|as of now|these days|at the moment|so far)\b", re.I), "time-deictic"),
    (re.compile(r"(?:#\d+\b|\branked\s+\d+|\b\d+(?:st|nd|rd|th)\s+place|\bin the lead\b|\bwho'?s winning\b|\bcurrently winning\b)", re.I), "standing/rank"),
    (re.compile(r"\b\d[\d,]*\s?(?:completions?|users?|followers?|stakers?|signups?|downloads?|installs?|views?|listeners?)\b", re.I), "live count"),
    (re.compile(r"\b(?:price|cost|rate|balance|revenue|MRR|ARR|valuation|runway)\b", re.I), "financial"),
    (re.compile(r"\b\d+%?\s?(?:done|complete|rebranded|shipped|finished|migrated)\b", re.I), "progress"),
]

_SYS = (
    "You are the volatility gate for an AI agent's long-term memory. You decide "
    "whether a stored fact is durable enough to keep in memory, or whether it is "
    "a fast fact that belongs in a live dashboard instead.\n\n"
    "Tiers:\n"
    "- static: never goes wrong (heritage, birthdate, values, a lifetime count like '3x founder').\n"
    "- slow: goes wrong over months, only when a named event happens (job title, a stack choice, a canonical career number).\n"
    "- fast: goes wrong in days (a percentage, a live count, a price/balance, a ranking, 'currently', project %-done). Fast facts must NOT live in memory.\n\n"
    "A number alone does not make a fact fast: '3x founder' is static, '393K balance' is fast. Judge what makes it WRONG, not whether it has a digit.\n"
    "For each item return an object {i, tier, reason, stale_when} where i is the item's index, "
    "tier is static|slow|fast, reason is <=12 words, and stale_when names the event/date that invalidates it "
    "(\"\" for static)."
)


def _signal_scan(text: str) -> list[str]:
    hits = []
    for rx, label in _SIGNALS:
        if rx.search(text or ""):
            hits.append(label)
    return hits


def _excerpt(title: str, summary: str, content: str) -> str:
    body = (summary or "").strip() or (content or "").strip()
    body = re.sub(r"\s+", " ", body)[:260]
    return f"{title.strip()} — {body}" if body else title.strip()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def find_suspects(conn: sqlite3.Connection, cube_limit: int = 4000) -> list[dict]:
    """Stage 1, deterministic and free: cubes carrying a fast-fact signal."""
    rows = conn.execute(
        "SELECT id, source, source_ref, title, content, summary FROM helicon_cubes "
        "WHERE merged_into IS NULL AND review_status != 'killed' "
        "ORDER BY created_at DESC LIMIT ?",
        (cube_limit,),
    ).fetchall()
    # Sources where durable FACTS get stored (and so can rot) rank above git
    # commit history, which is activity, not a fact stored as memory.
    fact_first = {"memory": 0, "obsidian": 1, "chatgpt": 1, "notes": 1, "claude-code": 2, "cursor": 2}
    suspects = []
    for r in rows:
        text = f"{r['title']} {r['summary'] or ''} {r['content'] or ''}"
        sig = _signal_scan(text)
        if sig:
            suspects.append({
                "id": r["id"],
                "source": r["source"],
                "source_ref": r["source_ref"],
                "title": r["title"],
                "signals": sig,
                "excerpt": _excerpt(r["title"], r["summary"] or "", r["content"] or ""),
            })
    # Judge the highest-value suspects first: fact-bearing source, then signal
    # richness. The Qwen budget goes to real stored facts, not commit noise.
    suspects.sort(key=lambda s: (fact_first.get(s["source"], 5), -len(s["signals"])))
    return suspects


def _classify(client, suspects: list[dict], model: str) -> dict:
    """Stage 2: Qwen sentences each suspect. Returns {index: verdict}."""
    from helicon.qwen import complete_json
    verdicts: dict[int, dict] = {}
    batch = 12
    for start in range(0, len(suspects), batch):
        chunk = suspects[start:start + batch]
        items = [{"i": start + j, "fact": s["excerpt"]} for j, s in enumerate(chunk)]
        user = "Classify each fact's durability tier.\n" + json.dumps(items, ensure_ascii=False)
        res = complete_json(client, _SYS, user, model=model, operation="volatility")
        if isinstance(res, dict):
            res = res.get("items") or res.get("results") or res.get("verdicts") or []
        if not isinstance(res, list):
            continue
        for v in res:
            try:
                idx = int(v.get("i"))
            except (TypeError, ValueError):
                continue
            verdicts[idx] = {
                "tier": str(v.get("tier", "")).lower().strip(),
                "reason": str(v.get("reason", "")).strip(),
                "stale_when": str(v.get("stale_when", "")).strip(),
            }
    return verdicts


def scan_volatility(conn: sqlite3.Connection, config: dict | None = None,
                    client=None, judge_cap: int = 60, model: str | None = None) -> dict:
    """The full gate: deterministic suspects, then Qwen sentences the top ones.

    Returns fast facts (rot: belong in the live layer), slow facts missing decay
    metadata (fixable with as_of/stale_when), and honest counts.
    """
    config = config or {}
    suspects = find_suspects(conn)
    total_suspects = len(suspects)
    if not suspects:
        return {"suspects": 0, "judged": 0, "keyless": client is None,
                "fast": [], "slow_undated": [], "static": 0}

    if client is None:
        # Honest keyless degrade: we see the signal, we do not sentence it.
        return {
            "suspects": total_suspects, "judged": 0, "keyless": True,
            "fast": [], "slow_undated": [], "static": 0,
            "unsentenced": [
                {"id": s["id"], "title": s["title"], "source": s["source"],
                 "source_ref": s["source_ref"], "signals": s["signals"]}
                for s in suspects[:judge_cap]
            ],
        }

    to_judge = suspects[:judge_cap]
    model = model or (config.get("qwen_models", {}) or {}).get("flash", "qwen3.6-flash")
    verdicts = _classify(client, to_judge, model)

    fast, slow_undated, static_n = [], [], 0
    for i, s in enumerate(to_judge):
        v = verdicts.get(i)
        if not v:
            continue
        tier = v["tier"]
        rec = {**s, "tier": tier, "reason": v["reason"], "stale_when": v["stale_when"]}
        if tier == "fast":
            fast.append(rec)
        elif tier == "slow":
            slow_undated.append(rec)
        elif tier == "static":
            static_n += 1
    return {
        "suspects": total_suspects, "judged": len(verdicts), "keyless": False,
        "fast": fast, "slow_undated": slow_undated, "static": static_n,
    }


# --- one-click actions: Helicon edits the file --------------------------------

def _safe_md(path: str, config: dict) -> str | None:
    """A source_ref we are allowed to write: an existing .md under a known root
    (the vault, the operator-memory dir, or the repo). Anything else (a git
    object, a transcript, an absolute path outside these roots) is refused."""
    if not path or not path.endswith(".md"):
        return None
    p = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(p):
        return None
    roots = []
    for c in (config.get("connectors") or {}).values() if isinstance(config.get("connectors"), dict) else []:
        if isinstance(c, dict) and c.get("path"):
            roots.append(os.path.abspath(os.path.expanduser(c["path"])))
    for key in ("vault_path", "operator_memory_path", "memory_path"):
        if config.get(key):
            roots.append(os.path.abspath(os.path.expanduser(config[key])))
    roots.append(os.path.abspath(os.getcwd()))
    return p if any(p.startswith(r + os.sep) or p == r for r in roots) else None


def stamp_decay(source_ref: str, config: dict, stale_when: str) -> dict:
    """Add `as_of` + `stale_when` to a slow fact's file frontmatter."""
    p = _safe_md(source_ref, config)
    if not p:
        return {"ok": False, "reason": "not a writable markdown file"}
    text = open(p, encoding="utf-8").read()
    today = _now()
    add = f"as_of: {today}\nstale_when: {stale_when or 'a named event invalidates this'}\n"
    if text.startswith("---\n") and "\n---" in text[4:]:
        end = text.index("\n---", 4)
        head = text[4:end]
        head = re.sub(r"^as_of:.*\n", "", head, flags=re.M)
        head = re.sub(r"^stale_when:.*\n", "", head, flags=re.M)
        new = "---\n" + head.rstrip("\n") + "\n" + add + text[end + 1:]
    else:
        new = "---\n" + add + "---\n\n" + text
    open(p, "w", encoding="utf-8").write(new)
    return {"ok": True, "action": "stamped", "path": p, "as_of": today, "stale_when": stale_when}


def move_to_live_layer(source_ref: str, title: str, excerpt: str, config: dict) -> dict:
    """Move a fast fact out of memory: append it to the live-layer file and
    banner the source so the stale copy is not silently trusted. We append a
    copy and banner rather than blind-deleting lines from a doc we did not
    author — honest and reversible."""
    live = config.get("volatility", {}).get("live_layer_path") or os.path.join("data", "live-layer.md")
    live = os.path.abspath(os.path.expanduser(live))
    os.makedirs(os.path.dirname(live), exist_ok=True)
    today = _now()
    if not os.path.exists(live):
        open(live, "w", encoding="utf-8").write(
            "# Live layer — fast facts moved out of memory\n\n"
            "These decay in days. They live here, re-fetched, never in a memory file.\n")
    with open(live, "a", encoding="utf-8") as f:
        f.write(f"\n- **{title}** — {excerpt}  \n  _moved from `{os.path.basename(source_ref)}` on {today}_\n")

    bannered = False
    p = _safe_md(source_ref, config)
    if p:
        text = open(p, encoding="utf-8").read()
        banner = (f"> **HELICON {today}:** a fast fact here was moved to the live layer "
                  f"(`{os.path.basename(live)}`). Treat the copy below as point-in-time, re-fetch before trusting.\n\n")
        if "moved to the live layer" not in text:
            body = text
            if body.startswith("---\n") and "\n---" in body[4:]:
                end = body.index("\n---", 4) + 4
                text = body[:end] + "\n\n" + banner + body[end:].lstrip("\n")
            else:
                text = banner + body
            open(p, "w", encoding="utf-8").write(text)
            bannered = True
    return {"ok": True, "action": "moved", "live_layer": live, "source_bannered": bannered}
