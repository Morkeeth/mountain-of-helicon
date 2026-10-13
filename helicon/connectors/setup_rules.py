"""Setup rules and hooks connector: which rule is enforced, and by what.

A rule file under `rules/` is a sentence an agent may or may not read. A hook under
`hooks/` is a program the harness runs whether the agent read anything or not. The
store counted both and held neither, so `helicon ask` could not say which rule a
hook enforces.

This connector reads one agent home (for example `~/.claude`) and gives:

  - one cube per rule file: its name, what it says in one line, the hook that
    enforces it (if any), whether that hook is wired in settings.json, and its path;
  - one cube per hook file: its name, the events it runs on, the rule it enforces
    (if a rule names it), what it does in one line, and its path;
  - one index cube that lists the rules a hook enforces and the rules with no hook.

How enforcement is decided: a rule is enforced by a hook when the rule text names the
hook file and settings.json wires that file to an event. A rule that names a hook
which is absent or not wired is reported as that, because it is a claim that no
longer holds.

Everything is read as data. A hook is never run. Opt-in: nothing is read unless the
connector config holds `claude_home`.
"""
import json
import os
import re
from datetime import datetime

from helicon.models import ConnectorResult

_SCRIPT_SUFFIXES = (".sh", ".py", ".js", ".mjs", ".ts", ".rb", ".zsh", ".bash")
_SKIP_MARKERS = (".bak", "~", ".orig", ".disabled")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _mdate(path: str) -> str:
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%dT00:00:00")
    except OSError:
        return ""


def _plain(text: str, cap: int = 220) -> str:
    text = re.sub(r"[*_`>#]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:cap].rstrip()


def _frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fields = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip().strip("\"'")
    return fields, text[end + 4:]


def _rule_says(fields: dict, body: str) -> str:
    """One line for the rule: its own description, else its first line of substance."""
    if fields.get("description"):
        return _plain(fields["description"])
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return _plain(stripped)
    return ""


def _hook_does(text: str) -> str:
    """One line for the hook: its header comment or docstring, never its code."""
    lines = text.splitlines()
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    picked = []
    in_doc = False
    for line in lines[:14]:
        stripped = line.strip()
        if stripped.startswith(('"""', "'''")):
            rest = stripped[3:]
            if rest.endswith(('"""', "'''")):
                picked.append(rest[:-3])
                break
            in_doc = not in_doc
            if rest:
                picked.append(rest)
            if not in_doc:
                break
            continue
        if in_doc:
            if not stripped:
                break
            picked.append(stripped)
            continue
        if stripped.startswith("#"):
            comment = stripped.lstrip("#").strip()
            if comment:
                picked.append(comment)
            elif picked:
                break
            continue
        if picked or stripped:
            break
    return _plain(" ".join(picked))


def _wiring(settings_path: str) -> list[dict]:
    """Every command hook in settings.json: event, matcher and command text."""
    try:
        settings = json.loads(_read(settings_path) or "{}")
    except ValueError:
        return []
    out = []
    groups = settings.get("hooks", {}) if isinstance(settings, dict) else {}
    if not isinstance(groups, dict):
        return []
    for event, entries in groups.items():
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks", []) or []:
                if isinstance(hook, dict) and hook.get("command"):
                    out.append({"event": str(event), "matcher": str(entry.get("matcher") or ""),
                                "command": str(hook["command"])})
    return out


def _runs_on(name: str, wiring: list[dict]) -> list[str]:
    seen = []
    for wire in wiring:
        if re.search(r"(^|[/\s\"'])" + re.escape(name) + r"($|[\s\"'])", wire["command"]):
            label = wire["event"] + (f" on {wire['matcher']}" if wire["matcher"] else "")
            if label not in seen:
                seen.append(label)
    return seen


def scan(config: dict) -> list[ConnectorResult]:
    home = config.get("claude_home") or ""
    if not home:
        return []
    home = os.path.abspath(os.path.expanduser(home))
    rules_dir = os.path.join(home, "rules")
    hooks_dir = os.path.join(home, "hooks")
    wiring = _wiring(os.path.join(home, "settings.json"))

    hooks = {}
    if os.path.isdir(hooks_dir):
        for name in sorted(os.listdir(hooks_dir)):
            path = os.path.join(hooks_dir, name)
            if not os.path.isfile(path) or not name.endswith(_SCRIPT_SUFFIXES):
                continue
            if any(marker in name for marker in _SKIP_MARKERS):
                continue
            hooks[name] = {"name": name, "path": path, "does": _hook_does(_read(path)),
                           "runs_on": _runs_on(name, wiring), "enforces": []}

    rules = []
    if os.path.isdir(rules_dir):
        for name in sorted(os.listdir(rules_dir)):
            path = os.path.join(rules_dir, name)
            if not os.path.isfile(path) or not name.endswith(".md"):
                continue
            text = _read(path)
            fields, body = _frontmatter(text)
            named = sorted(set(re.findall(r"hooks/([A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*)", text)))
            enforced, broken = [], []
            for hook_name in named:
                hook = hooks.get(hook_name)
                if hook and hook["runs_on"]:
                    enforced.append(hook_name)
                    hook["enforces"].append(name)
                elif hook:
                    broken.append(f"{hook_name} (file is there, settings.json does not wire it)")
                else:
                    broken.append(f"{hook_name} (no such file)")
            rules.append({"name": name, "path": path, "says": _rule_says(fields, body),
                          "enforced_by": enforced, "broken": broken,
                          "loaded": "only for matching paths" if "paths" in fields else "every session"})

    results = []
    for rule in rules:
        if rule["enforced_by"]:
            hook_line = ", ".join(
                f"hooks/{h} ({'; '.join(hooks[h]['runs_on'])})" for h in rule["enforced_by"])
            title = f"Rule {rule['name']}: enforced by hook {', '.join('hooks/' + h for h in rule['enforced_by'])}"
        else:
            hook_line = "none. This rule holds only if the agent reads it."
            title = f"Rule {rule['name']}: no hook enforces it"
        lines = [f"Rule: {rule['name']}", f"Enforced by hook: {hook_line}"]
        if rule["broken"]:
            lines.append("Names a hook that does not enforce it: " + "; ".join(rule["broken"]))
        lines += [f"Says: {rule['says']}", f"Loaded: {rule['loaded']}", f"Path: {rule['path']}"]
        results.append(ConnectorResult(
            source="setup-rules", source_ref=f"rules/{rule['name']}", type="agent_rule",
            title=title, content="\n".join(lines), created_at=_mdate(rule["path"]),
            tags=["setup-rules", "rule", "hook-enforced" if rule["enforced_by"] else "not-enforced"],
            metadata={"kind": "rule", "rule": rule["name"], "says": rule["says"],
                      "enforced_by_hook": [os.path.join(hooks_dir, h) for h in rule["enforced_by"]],
                      "hook_enforced": bool(rule["enforced_by"]), "unenforced_hook_claims": rule["broken"],
                      "loaded": rule["loaded"], "file_path": rule["path"]},
        ))

    for hook in hooks.values():
        runs = "; ".join(hook["runs_on"]) or "not wired in settings.json"
        if hook["enforces"]:
            title = f"Hook {hook['name']}: enforces rule {', '.join(hook['enforces'])}"
        else:
            title = f"Hook {hook['name']}: {hook['runs_on'][0] if hook['runs_on'] else 'not wired'}"
        lines = [f"Hook: {hook['name']}", f"Runs on: {runs}",
                 f"Enforces rule: {', '.join(hook['enforces']) or 'no rule file names it'}",
                 f"Does: {hook['does']}", f"Path: {hook['path']}"]
        results.append(ConnectorResult(
            source="setup-rules", source_ref=f"hooks/{hook['name']}", type="agent_hook",
            title=title, content="\n".join(lines), created_at=_mdate(hook["path"]),
            tags=["setup-rules", "hook", "wired" if hook["runs_on"] else "not-wired"],
            metadata={"kind": "hook", "hook": hook["name"], "does": hook["does"],
                      "runs_on": hook["runs_on"], "enforces_rule": hook["enforces"],
                      "wired": bool(hook["runs_on"]), "file_path": hook["path"]},
        ))

    if rules:
        enforced = [r for r in rules if r["enforced_by"]]
        loose = [r["name"] for r in rules if not r["enforced_by"]]
        lines = ["Rules enforced by a hook: " + (
            "; ".join(f"{r['name']} by {', '.join('hooks/' + h for h in r['enforced_by'])}" for r in enforced)
            or "none")]
        lines.append("Rules with no hook, held only by being read: " + (", ".join(loose) or "none"))
        lines.append(f"Read from: {home}")
        newest = max((_mdate(r["path"]) for r in rules), default="")
        results.append(ConnectorResult(
            source="setup-rules", source_ref="rules#enforced-by-hook", type="agent_rule",
            title="Which rules are enforced by a hook: " + (
                ", ".join(f"{r['name']} ({', '.join(r['enforced_by'])})" for r in enforced) or "none"),
            content="\n".join(lines), created_at=newest,
            tags=["setup-rules", "rule", "index"],
            metadata={"kind": "index", "hook_enforced_rules": {r["name"]: r["enforced_by"] for r in enforced},
                      "rules_without_hook": loose, "file_path": rules_dir},
        ))
    return results
