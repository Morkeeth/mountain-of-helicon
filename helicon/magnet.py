"""MAGNET — rank a flood of candidate skills by whether they fill a hole you have.

There are on the order of two thousand community agent skills and every directory
ranks them by stars. Stars measure how many people liked a thing; they say nothing
about whether it belongs in YOUR setup. So the noise is not a discovery problem —
the feed is already solved, several times over — it is a RANKING problem, and the
ranker has to be your own stack.

Not the same question as `helicon stack`, which lists what you have, and not the
same as the audit skills that compare your config against the official docs. Those
answer "are you using the documented features correctly". This answers "of the
flood, which three address something you are actually missing".

Deterministic on purpose. No model in the loop: a ranking that changes between
runs cannot be argued with, and the whole value here is an argument you can check.
The cost is that matching is lexical, so this reports CANDIDATES and says so. The
ruling is the human's.

Three outputs, and the middle one is the product:

  INVENTORY  what you have, by surface. Names only — never values, never secrets.
  GAPS       surfaces with no coverage, and named capabilities nothing you own
             mentions. A gap is stated as a fact about your machine, not a
             recommendation.
  RANKED     candidates scored by which of YOUR gaps they name, with the overlap
             against what you already own printed beside them, because a skill
             that duplicates one you have is the most common kind of noise.
"""
import json
import os
import re

# Surfaces a Claude Code stack can carry. Each is a place work can be automated;
# a surface at zero is the strongest gap signal there is, because it means a whole
# category of automation is unused rather than merely thin.
SURFACES = ("skills", "commands", "agents", "hooks", "mcp")

# Capabilities worth having an opinion about. Deliberately short and deliberately
# not a feature list: each is something whose ABSENCE is a fact about a stack, and
# each is stated as the words a candidate's own description would use.
CAPABILITIES = {
    "test-gate": ("test", "pytest", "jest", "suite", "green", "ci"),
    "review": ("review", "critique", "audit", "lint"),
    "security": ("secret", "credential", "vulnerab", "injection", "sandbox"),
    "docs": ("documentation", "docstring", "readme", "changelog"),
    "verification": ("verify", "probe", "receipt", "evidence", "reproduce"),
    "planning": ("plan", "decompose", "roadmap", "slice"),
    "research": ("research", "search", "literature", "source"),
    "design": ("design", "ui", "visual", "typography", "palette"),
    "writing": ("writing", "draft", "prose", "copy", "email"),
    "data": ("sql", "dataframe", "etl", "schema", "migration"),
    "debug": ("debug", "trace", "stack trace", "repro", "bisect"),
    "refactor": ("refactor", "rename", "extract", "simplify"),
}

_WORD = re.compile(r"[a-z][a-z0-9-]{2,}")
# Words too common in a skill description to carry any signal about what it does.
_STOP = {
    "the", "and", "for", "use", "when", "with", "this", "that", "his", "her",
    "you", "your", "not", "any", "all", "from", "into", "onto", "have", "has",
    "was", "are", "will", "can", "should", "must", "before", "after", "every",
    "one", "two", "three", "skill", "claude", "agent", "agents", "user", "code",
    "file", "files", "run", "runs", "running", "make", "makes", "get", "gets",
    "new", "old", "more", "most", "than", "then", "also", "just", "only",
}


def _words(text: str) -> set:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def _mentions(text: str, terms: tuple) -> bool:
    """Does this text actually NAME one of these terms?

    Word-boundary matching, not substring. A plain `term in text` scored "tune a
    guitar by ear" as a DESIGN skill, because "ui" sits inside "g-ui-tar" — and
    "build", "quick" and "require" carry it too. Short capability terms make
    substring matching a false-positive generator, and a false positive here is
    worse than a miss: it puts an unrelated skill in a shortlist whose entire
    value is that you can trust its five entries.

    Multi-word terms ("stack trace") are still matched as a phrase, since a
    phrase cannot collide the way a two-letter token can."""
    words = _words(text)
    low = (text or "").lower()
    for t in terms:
        if " " in t:
            if t in low:
                return True
        elif any(w == t or w.startswith(t) and len(t) >= 5 for w in words):
            return True
    return False


# --- inventory -------------------------------------------------------------

def inventory(claude_dir: str = "~/.claude") -> dict:
    """What this stack actually carries, by surface.

    NAMES AND DESCRIPTIONS ONLY. Never a value, never an environment variable's
    contents, never an MCP connection string. That rule is lifted from the
    prior-art audit skill and it is the right one: an inventory is something you
    might paste into a report, and a tool that quietly puts a token in it has
    done real damage for no benefit."""
    root = os.path.expanduser(claude_dir)
    inv = {s: [] for s in SURFACES}
    visible = set(SURFACES)
    if not os.path.isdir(root):
        return {"root": root, "present": False, "enumerable": [], **inv}

    skills_dir = os.path.join(root, "skills")
    if os.path.isdir(skills_dir):
        for name in sorted(os.listdir(skills_dir)):
            path = os.path.join(skills_dir, name, "SKILL.md")
            if os.path.isfile(path):
                inv["skills"].append({"name": name,
                                      "description": _frontmatter_desc(path)})

    cmd_dir = os.path.join(root, "commands")
    if os.path.isdir(cmd_dir):
        for fn in sorted(os.listdir(cmd_dir)):
            # A .bak file is not a live command. Counting it inflates coverage,
            # which is the direction an inventory must never err in.
            if not fn.endswith(".md") or ".bak" in fn:
                continue
            path = os.path.join(cmd_dir, fn)
            inv["commands"].append({"name": fn[:-3],
                                    "description": _frontmatter_desc(path)})

    agent_dir = os.path.join(root, "agents")
    if os.path.isdir(agent_dir):
        for fn in sorted(os.listdir(agent_dir)):
            if fn.endswith(".md") and ".bak" not in fn:
                inv["agents"].append({"name": fn[:-3],
                                      "description": _frontmatter_desc(
                                          os.path.join(agent_dir, fn))})

    settings = os.path.join(root, "settings.json")
    if os.path.isfile(settings):
        try:
            with open(settings) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
        for event, matchers in (data.get("hooks") or {}).items():
            for m in matchers:
                for h in m.get("hooks", []):
                    cmd = h.get("command", "")
                    inv["hooks"].append({
                        "name": os.path.basename(cmd.split()[0]) if cmd else h.get("type", "?"),
                        "description": f"{event} on {m.get('matcher') or '*'}",
                        "event": event})
        # MCP is the one surface this cannot enumerate. Servers arrive from
        # project .mcp.json, from `claude mcp add`, and from cloud connectors —
        # none of which live here. So an absent mcpServers key means NOT VISIBLE,
        # never zero. Reporting a surface you cannot see as empty invents a gap,
        # and a fabricated gap is worse than a missed one: it sends the ranker
        # hunting for candidates to fill a hole that is already filled.
        if "mcpServers" in data:
            for server in sorted((data.get("mcpServers") or {}).keys()):
                inv["mcp"].append({"name": server, "description": ""})
        else:
            visible.discard("mcp")
    return {"root": root, "present": True, "enumerable": sorted(visible), **inv}


def _frontmatter_desc(path: str) -> str:
    """The `description:` line from YAML frontmatter, if any."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(4000)
    except OSError:
        return ""
    m = re.search(r"^description:\s*(.+?)\s*$", head, re.M)
    return (m.group(1).strip().strip('"\'') if m else "")[:400]


# --- gaps ------------------------------------------------------------------

def gaps(inv: dict) -> dict:
    """Holes stated as facts about this machine, never as recommendations.

    Two kinds, and they are different in strength:

      EMPTY SURFACE   a whole category with nothing in it. This is the strongest
                      signal available without a model, because it needs no
                      judgement — either agents are defined or they are not.
      UNCOVERED CAP   a named capability that nothing in the inventory mentions.
                      Weaker: it is a keyword search over descriptions, so a
                      capability covered under a name this list does not know
                      reads as missing. Reported as such."""
    # Only a surface this stack can actually ENUMERATE may be called empty.
    enumerable = set(inv.get("enumerable") or SURFACES)
    empty = [s for s in SURFACES if s in enumerable and not inv.get(s)]
    unseen = [s for s in SURFACES if s not in enumerable]
    owned = set()
    for s in SURFACES:
        for item in inv.get(s) or []:
            owned |= _words(item.get("name", "")) | _words(item.get("description", ""))
    owned_blob = " ".join(sorted(owned))
    uncovered = sorted(cap for cap, terms in CAPABILITIES.items()
                       if not _mentions(owned_blob, terms))
    return {"empty_surfaces": empty, "uncovered": uncovered,
            "not_enumerable": unseen, "owned_terms": len(owned),
            "counts": {s: len(inv.get(s) or []) for s in SURFACES}}


# --- ranking ---------------------------------------------------------------

def load_candidates(path: str) -> list:
    """The feed's output. JSON list or JSONL, each row {name, description, ...}.

    MAGNET does NOT crawl. Several directories already index this corpus well and
    rebuilding one would be the coverage race they have already won. The feed is
    an input; ranking is the product."""
    path = os.path.expanduser(path or "")
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read().strip()
    if text.startswith("["):
        try:
            rows = json.loads(text)
        except json.JSONDecodeError:
            rows = []
    else:
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return [r for r in rows if isinstance(r, dict) and r.get("name")]


def rank(candidates: list, inv: dict, g: dict, top: int = 10) -> list:
    """Score each candidate by which of YOUR gaps it names.

    Scoring is stated rather than tuned, so the ranking can be argued with:

      +3  per uncovered capability the candidate's description names
      +2  if it targets an EMPTY surface (a skill when you have none, an agent
          when you have none)
      -4  if an item you already own shares most of its distinctive words

    That last one is the important term. A directory sorted by stars puts the
    popular duplicate at the top; the most common way a flood wastes your time is
    a good skill you already have under another name."""
    owned_sets = [(item.get("name", ""), _words(item.get("name", "")) |
                   _words(item.get("description", "")))
                  for s in SURFACES for item in (inv.get(s) or [])]
    out = []
    for c in candidates:
        text = f"{c.get('name','')} {c.get('description','')}"
        words = _words(text)
        low = text.lower()

        fills = [cap for cap in g["uncovered"]
                 if _mentions(text, CAPABILITIES[cap])]
        score = 3 * len(fills)

        surface = (c.get("surface") or "").lower()
        empty_hit = surface in g["empty_surfaces"]
        if empty_hit:
            score += 2

        dupes = []
        for owned_name, owned_words in owned_sets:
            if not words or not owned_words:
                continue
            overlap = len(words & owned_words) / len(words)
            if overlap >= 0.34:
                dupes.append({"name": owned_name, "overlap": round(overlap, 2)})
        dupes.sort(key=lambda d: -d["overlap"])
        if dupes:
            score -= 4

        out.append({"name": c.get("name"), "score": score, "fills": fills,
                    "empty_surface": surface if empty_hit else "",
                    "duplicates": dupes[:2],
                    "description": (c.get("description") or "")[:160],
                    "source": c.get("source", "")})
    # An item with no positive signal is UNRANKED, not last. Sorting ties by
    # name smuggles the alphabet into a ranking that claims to be about fit:
    # EXP-MAGNET-01 scored three synonym candidates at 0 — identical to all 990
    # noise items — and two of them still landed at rank 5 and 6, because
    # "code-surgeon" and "fault-localiser" sort before "noise-000". That read as
    # 87.5% recall. The real signal-based recall was 62.5%. A tie-break is not a
    # finding, and a ranking that cannot say "no evidence" will always invent one.
    scored = [r for r in out if r["score"] > 0]
    unranked = [r for r in out if r["score"] <= 0]
    scored.sort(key=lambda r: (-r["score"], r["name"]))
    demoted = sorted([r for r in unranked if r["score"] < 0],
                     key=lambda r: (r["score"], r["name"]))
    no_signal = [r for r in unranked if r["score"] == 0]
    for r in no_signal:
        r["no_signal"] = True
    return {"ranked": scored[:top], "demoted": demoted[:top],
            "no_signal": len(no_signal), "considered": len(out)}


def magnet_report(claude_dir: str = "~/.claude", candidates_path: str = "",
                  top: int = 10) -> dict:
    inv = inventory(claude_dir)
    g = gaps(inv)
    cands = load_candidates(candidates_path) if candidates_path else []
    return {"inventory": inv, "gaps": g,
            "candidates_read": len(cands),
            "candidates_path": candidates_path,
            **({"ranked": [], "demoted": [], "no_signal": 0, "considered": 0}
               if not cands else rank(cands, inv, g, top))}


def render_magnet(report: dict, read_at: str = "") -> str:
    inv, g = report["inventory"], report["gaps"]
    out = ["MAGNET — of the flood, what fills a hole you actually have", ""]
    if not inv.get("present"):
        return f"MAGNET — no stack found at {inv.get('root')}"

    unseen = set(g.get("not_enumerable") or [])
    counts = " · ".join(f"{'?' if s in unseen else g['counts'][s]} {s}"
                        for s in SURFACES)
    out += [f"  INVENTORY   {counts}", f"  {'':14}{inv['root']}", ""]

    if g["empty_surfaces"]:
        out.append(f"  EMPTY SURFACES   {', '.join(g['empty_surfaces'])}")
        out.append("  a whole category with nothing in it — the one gap that "
                   "needs no judgement")
    if unseen:
        out.append(f"  NOT VISIBLE HERE {', '.join(sorted(unseen))} — configured "
                   "outside this file (project .mcp.json,")
        out.append("  `claude mcp add`, cloud connectors). Not counted as a gap, "
                   "because absent is not zero.")
    if g["uncovered"]:
        out.append(f"  UNCOVERED        {', '.join(g['uncovered'])}")
        out.append("  nothing you own mentions these; a keyword search over "
                   "descriptions, so a capability")
        out.append("  you cover under another name will read as missing here")
    if not g["empty_surfaces"] and not g["uncovered"]:
        out.append("  NO GAPS FOUND    every surface is populated and every "
                   "named capability is mentioned")
    out.append("")

    if not report["candidates_path"]:
        out += ["  NO FEED CONFIGURED. MAGNET does not crawl — several "
                "directories already index",
                "  this corpus and rebuilding one is a race they have won. "
                "Point it at the feed's",
                "  output:  helicon magnet --candidates <file.jsonl>", ""]
    elif not report["candidates_read"]:
        out += [f"  FEED READ 0 ROWS from {report['candidates_path']}",
                "  an empty feed is not an empty result — nothing was ranked", ""]
    else:
        out.append(f"  RANKED   {report['candidates_read']} read · "
                   f"{len(report['ranked'])} showed positive signal · "
                   f"{report['no_signal']} showed NONE and are not ranked at all")
        if not report["ranked"]:
            out.append("     nothing in this feed names a gap you have")
        for r in report["ranked"]:
            out.append(f"     {r['score']:>3}  {r['name']}")
            if r["fills"]:
                out.append(f"          fills: {', '.join(r['fills'])}")
            if r["empty_surface"]:
                out.append(f"          targets an empty surface: {r['empty_surface']}")
            for d in r["duplicates"]:
                out.append(f"          OVERLAPS what you already have: "
                           f"{d['name']} ({int(d['overlap']*100)}% of its words)")
            if r["description"]:
                out.append(f"          {r['description']}")
        if report["demoted"]:
            out.append("")
            out.append("  DEMOTED — you already have something like these:")
            for r in report["demoted"][:5]:
                d = r["duplicates"][0] if r["duplicates"] else {"name": "?", "overlap": 0}
                out.append(f"     {r['score']:>3}  {r['name']}  ->  {d['name']} "
                           f"({int(d['overlap']*100)}%)")
        out += ["", "  These are CANDIDATES. Matching is lexical and has no model "
                "in it, which is why the",
                "  ranking is reproducible and why it cannot judge quality. "
                "The ruling is yours.", ""]

    out.append(f"read {read_at}  ·  helicon magnet")
    return "\n".join(out)
