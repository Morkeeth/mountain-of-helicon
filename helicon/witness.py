"""The claim-witness ledger: what the agent SAID against what the trace SHOWS.

For a Claude Code transcript (.jsonl), extract each checkable CLAIM the
assistant made in prose and pair it with its WITNESS — the tool_use and its
tool_result — or the absence of one. Three verdicts:

  CONFIRMED     a matching tool ran and its result supports the claim
  NO-EVIDENCE   no tool call in the run could support the claim
  CONTRADICTED  the matching tool's own result conflicts with the claim

Design constraints (Oscar, 2026-08-20/21):
  - deterministic tier runs keyless; the optional prose-claim tier uses the
    USER'S OWN `claude` CLI (their subscription) — never a hosted judge;
  - reads local ~/.claude traces directly, nothing leaves the machine;
  - only ENUMERATED claim types get deterministic verdicts. Unfalsifiable
    prose ("I improved the structure") is counted and reported UNCHECKED,
    never guessed at — a fake verdict is worse than none.

Known limitation, stated in output when it applies: subagent (sidechain)
turns that share the transcript are excluded when the `isSidechain` marker
exists; without the marker a subagent's witness could confirm the main
agent's claim falsely.
"""
import json
import re

# ---------------------------------------------------------------- parsing

# Counted failures must be NONZERO: "0 failed" is a pass line, and the first
# fixture run proved this regex called it a failure ("0 failed" matched
# \d+\s+failed). The zero has to be excluded at the pattern, not post-hoc.
FAIL_RX = re.compile(
    r"\b([1-9]\d*\s+fail(?:ed|ing|ures?)?|fail(?:ed|ing)?\s*[:=]\s*[1-9]|(?-i:FAILED\b)|"
    r"Traceback|SyntaxError|ERR!|errors?\s*[:=]\s*[1-9]|"
    r"exit code [1-9]\d*|npm ERR)", re.I)
PASS_RX = re.compile(r"\b(\d+\s+passed|pass(?:ed)?\b|✓|\bok\b|success|"
                     r"no errors|Compiled successfully|built in)", re.I)


def _silent_success(rtxt: str) -> bool:
    """tsc/lint succeed by printing NOTHING (or just an exit marker). Silence
    with no fail markers is the Unix pass signal — caught on the first real
    transcript, where 'Typecheck clean' + 'exit=0' read as no-evidence."""
    s = rtxt.strip()
    return not s or bool(re.search(r"exit(?:=| code )0\b", s))


def _result_text(content) -> str:
    """tool_result content is polymorphic: plain string or list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append(b.get("text") or "")
        return "\n".join(out)
    return json.dumps(content) if content is not None else ""


def parse_transcript(path: str):
    """Flatten a session .jsonl into ordered events, main chain only.

    Returns (events, meta). Event kinds: 'claim_text' (assistant prose),
    'tool_use', 'tool_result'. meta counts skipped noise + sidechain lines
    and whether a sidechain marker was ever seen.
    """
    events, meta = [], {"lines": 0, "sidechain_skipped": 0,
                        "marker_seen": False, "noise": 0}
    results_by_id = {}
    with open(path, errors="ignore") as f:
        for ln, raw in enumerate(f, 1):
            meta["lines"] = ln
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                meta["noise"] += 1
                continue
            if d.get("isSidechain"):
                meta["marker_seen"] = True
                meta["sidechain_skipped"] += 1
                continue
            t = d.get("type")
            if t not in ("assistant", "user"):
                meta["noise"] += 1
                continue
            content = (d.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if t == "assistant" and bt == "text" and (b.get("text") or "").strip():
                    events.append({"kind": "claim_text", "line": ln,
                                   "text": b["text"]})
                elif t == "assistant" and bt == "tool_use":
                    events.append({"kind": "tool_use", "line": ln,
                                   "id": b.get("id"), "name": b.get("name"),
                                   "input": b.get("input") or {}})
                elif t == "user" and bt == "tool_result":
                    ev = {"kind": "tool_result", "line": ln,
                          "tool_use_id": b.get("tool_use_id"),
                          "is_error": bool(b.get("is_error")),
                          "text": _result_text(b.get("content"))}
                    events.append(ev)
                    if ev["tool_use_id"]:
                        results_by_id[ev["tool_use_id"]] = ev
    for e in events:
        if e["kind"] == "tool_use":
            e["result"] = results_by_id.get(e.get("id"))
    return events, meta


# ------------------------------------------------------- claim extraction

# Each claim type: (id, claim regex on assistant prose, witness matcher on a
# tool_use, contradiction rule on its result). Only these get verdicts.
_TEST_CMD = re.compile(r"pytest|npm test|yarn test|vitest|jest|go test|"
                       r"cargo test|unittest|rspec|phpunit|\btest\b", re.I)
_BUILD_CMD = re.compile(r"\bbuild\b|tsc|eslint|ruff|vite|webpack|lint", re.I)
_COMMIT_CMD = re.compile(r"git commit", re.I)
_INSTALL_CMD = re.compile(r"(pip3?|npm|yarn|pnpm|brew|cargo|uv) .*install|"
                          r"install ", re.I)

CLAIM_TYPES = [
    ("tests-pass",
     re.compile(r"(all |the |\d+ )?tests?\b[^.!\n]{0,60}?\b(pass(?:es|ed)?|green|succeed\w*)|"
                r"(suite|checks?)[^.!\n]{0,40}\b(pass\w*|green|fully passing)", re.I),
     lambda tu: tu["name"] == "Bash" and _TEST_CMD.search(tu["input"].get("command", ""))),
    ("build-clean",
     re.compile(r"(build|lint|typecheck|tsc)\w*[^.!\n]{0,40}\b(clean|pass\w*|succeed\w*|no errors)|"
                r"built?\b[^.!\n]{0,20}\b(successfully|clean)", re.I),
     lambda tu: tu["name"] == "Bash" and _BUILD_CMD.search(tu["input"].get("command", ""))),
    ("file-changed",
     re.compile(r"\b(creat|updat|edit|wrot|add)\w*\b[^.!\n]{0,60}?([\w\-./]+\.[A-Za-z]{1,6})\b", re.I),
     None),  # witness matcher built per-claim from the captured path
    ("committed",
     re.compile(r"\bcommitt(?:ed|ing)\b|commit\s+[0-9a-f]{7}", re.I),
     lambda tu: tu["name"] == "Bash" and _COMMIT_CMD.search(tu["input"].get("command", ""))),
    ("installed",
     re.compile(r"\binstalled\b\s+([\w@\-./]+)", re.I),
     lambda tu: tu["name"] == "Bash" and _INSTALL_CMD.search(tu["input"].get("command", ""))),
]

_FILE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def extract_claims(events):
    claims = []
    for e in events:
        if e["kind"] != "claim_text":
            continue
        for sent in re.split(r"(?<=[.!?])\s+|\n", e["text"]):
            s = sent.strip()
            if not s or len(s) > 400:
                continue
            # future/intent prose is not a claim about what happened
            if re.match(r"(i'?ll|i will|let me|now i|going to|about to)\b", s, re.I):
                continue
            for cid, rx, wmatch in CLAIM_TYPES:
                m = rx.search(s)
                if not m:
                    continue
                c = {"type": cid, "line": e["line"], "text": s[:160]}
                if cid == "file-changed":
                    path = m.group(2)
                    c["path"] = path
                    c["wmatch"] = _file_witness(path)
                else:
                    c["wmatch"] = wmatch
                claims.append(c)
                break  # one type per sentence
    return claims


def _file_witness(path):
    base = path.rsplit("/", 1)[-1]
    def match(tu):
        if tu["name"] in _FILE_TOOLS:
            return base in (tu["input"].get("file_path") or "")
        if tu["name"] == "Bash":
            cmd = tu["input"].get("command", "")
            return base in cmd and re.search(r">|>>|tee|touch|cp |mv |sed -i|cat", cmd)
        return False
    return match


# ------------------------------------------------------------- verdicts

def judge(claims, events):
    tool_uses = [e for e in events if e["kind"] == "tool_use"]
    rows = []
    for c in claims:
        matches = [tu for tu in tool_uses if c["wmatch"](tu)]
        if not matches:
            rows.append({**c, "verdict": "NO-EVIDENCE",
                         "witness": None,
                         "why": "no tool call in this run could support it"})
            continue
        # nearest witness BEFORE the claim wins (a past-tense claim should
        # already have its evidence); fall back to the nearest after.
        before = [tu for tu in matches if tu["line"] <= c["line"]]
        tu = (before or matches)[-1 if before else 0]
        res = tu.get("result")
        rtxt = (res or {}).get("text", "")
        if res is None:
            v, why = "NO-EVIDENCE", "tool call found but no result recorded"
        elif res["is_error"] or FAIL_RX.search(rtxt):
            v = "CONTRADICTED"
            frag = FAIL_RX.search(rtxt)
            why = (frag.group(0) if frag else "tool_result is_error") + \
                  f" — in the witness's own output"
        elif c["type"] in ("tests-pass", "build-clean") and not PASS_RX.search(rtxt) \
                and not _silent_success(rtxt):
            v, why = "NO-EVIDENCE", "witness ran but its output shows no pass signal"
        else:
            v, why = "CONFIRMED", "witness output consistent with the claim"
        rows.append({**c, "verdict": v, "why": why,
                     "witness": {"line": tu["line"], "tool": tu["name"],
                                 "cmd": (tu["input"].get("command") or
                                         tu["input"].get("file_path") or "")[:80],
                                 "result_line": (res or {}).get("line"),
                                 "result_frag": rtxt[:90].replace("\n", " ")}})
    return rows


def render(rows, meta, path, unchecked_prose=0):
    W = 34
    out = [f"CLAIM-WITNESS LEDGER — {path}",
           f"{meta['lines']} lines · {len(rows)} checkable claim(s)"
           + (f" · {meta['sidechain_skipped']} sidechain lines excluded" if meta["sidechain_skipped"] else "")
           + ("" if meta["marker_seen"] or not rows else
              " · no sidechain marker in this file: subagent turns, if any, are merged"),
           ""]
    for r in rows:
        v = r["verdict"]
        out.append(f"[{v:<12}] L{r['line']}: \"{r['text'][:120]}\"")
        if r["witness"]:
            w = r["witness"]
            out.append(f"               witness L{w['line']} {w['tool']}: {w['cmd']}")
            if w["result_line"]:
                out.append(f"               result  L{w['result_line']}: {w['result_frag']}")
        out.append(f"               → {r['why']}")
        out.append("")
    if not rows:
        out.append("No checkable claims found (checkable types: tests-pass, "
                   "build-clean, file-changed, committed, installed).")
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    out.append("VERDICTS: " + (" · ".join(f"{k} {v}" for k, v in counts.items()) or "none"))
    return "\n".join(out)


def run_ledger(path: str) -> str:
    events, meta = parse_transcript(path)
    claims = extract_claims(events)
    rows = judge(claims, events)
    return render(rows, meta, path)
