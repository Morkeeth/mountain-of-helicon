"""Read-only setup evidence across harnesses. Discovery is not delivery.

No prompts, secrets, command bodies, or memory contents are exported. Paths and
hashes identify the inspected local objects. Plugin activation and effective
model context require runtime receipts and remain explicitly unmeasured.
"""
import hashlib
import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from .context_history import HistoryError, read_source_bytes


SCHEMA = "helicon.setup-audit/1"


def audit_setup(home=None, project=None):
    home = Path(home or Path.home()).resolve()
    project = Path(project or Path.cwd()).resolve()
    findings, files, seen = [], [], set()

    def finding(fid, harness, title, evidence, action, status="attention"):
        findings.append(dict(id=fid, harness=harness, status=status,
                             title=title, evidence=evidence, action=action))

    def inspect(path, harness, stage):
        path = Path(path)
        if not path.exists() and not path.is_symlink():
            return None
        key = (str(path), harness, stage)
        if key in seen:
            return None
        seen.add(key)
        try:
            data = read_source_bytes(path)
            body = data.decode("utf-8")
        except (OSError, HistoryError, UnicodeError):
            finding("unreadable:" + str(path), harness, "Instruction file could not be read",
                    [str(path)], "Check access to this file.", "unmeasured")
            return None
        files.append(dict(path=str(path), harness=harness, stage=stage,
                          bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        return body

    if not project.is_dir():
        finding("project-unavailable", "all", "Project directory is unavailable",
                [str(project)], "Select an existing project directory.", "unmeasured")

    # Inspect only the current project and its ancestors through the git root.
    ancestors = [project]
    while not (ancestors[-1] / ".git").exists() and ancestors[-1].parent != ancestors[-1]:
        ancestors.append(ancestors[-1].parent)
    if not (ancestors[-1] / ".git").exists():
        ancestors = [project]

    for harness, root, names in (
        ("claude", home / ".claude", ["CLAUDE.md"]),
        ("codex", home / ".codex", ["AGENTS.override.md", "AGENTS.md"]),
    ):
        for name in names:
            body = inspect(root / name, harness, "global instruction candidate")
            if body and harness == "codex":
                break
    for directory in reversed(ancestors):
        for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            inspect(directory / name, "claude", "project instruction candidate")
        for name in ("AGENTS.override.md", "AGENTS.md"):
            body = inspect(directory / name, "codex", "project instruction candidate")
            if body:
                break
        inspect(directory / "AGENTS.md", "cursor", "project instruction candidate")
        inspect(directory / ".cursorrules", "cursor", "project instruction candidate")
    for harness, roots, pattern in (
        ("claude", [home / ".claude/rules", project / ".claude/rules"], "*.md"),
        ("cursor", [home / ".cursor/rules", project / ".cursor/rules"], "*.mdc"),
    ):
        for root in roots:
            if root.is_dir():
                for path in sorted(root.rglob(pattern)):
                    inspect(path, harness, "rule candidate; applicability not observed")

    memory_indexes = []
    memory_root = home / ".claude/projects"
    if memory_root.is_dir():
        for path in sorted(memory_root.glob("*/memory/MEMORY.md")):
            inspect(path, "claude", "memory index; active project mapping not observed")
            memory_indexes.append(dict(path=str(path),
                                       files=sum(1 for p in path.parent.glob("*.md") if p.is_file())))

    skills = []
    for harness, roots in (
        ("claude", [home / ".claude/skills", project / ".claude/skills"]),
        ("cursor", [home / ".cursor/skills", home / ".cursor/skills-cursor", project / ".cursor/skills"]),
        ("codex", [home / ".codex/skills", home / ".agents/skills", project / ".agents/skills"]),
    ):
        for root in roots:
            if root.is_dir():
                for path in sorted(root.rglob("SKILL.md")):
                    try:
                        data = read_source_bytes(path)
                        data.decode("utf-8")
                    except (OSError, HistoryError, UnicodeError):
                        finding("skill-unreadable:" + str(path), harness, "Skill could not be read",
                                [str(path)], "Check access to this skill.", "unmeasured")
                        continue
                    skills.append(dict(harness=harness, path=str(path), name=path.parent.name,
                                       sha256=hashlib.sha256(data).hexdigest()))

    # Read configuration as data. Never execute a hook during an audit.
    settings_path = home / ".claude/settings.json"
    hooks = []
    vault = None
    try:
        config = json.loads(read_source_bytes(home / ".helicon/config.json").decode("utf-8"))
        obsidian = config.get("connectors", {}).get("obsidian", {})
        if obsidian.get("enabled") and obsidian.get("vault_path"):
            vault = Path(obsidian["vault_path"].replace("~/", str(home) + "/", 1))
    except (OSError, ValueError, TypeError, AttributeError):
        pass  # No declared vault means no vault-reference check.
    if settings_path.exists():
        try:
            settings = json.loads(read_source_bytes(settings_path).decode("utf-8"))
            groups = settings.get("hooks", {})
            if not isinstance(groups, dict):
                raise ValueError("hooks must be an object")
            routes = {}
            for event, entries in groups.items():
                for group in entries:
                    matcher = group.get("matcher", "")
                    for hook in group.get("hooks", []):
                        command = hook.get("command", "")
                        if not isinstance(command, str):
                            continue
                        if event == "PostCompact":
                            # A literal cat input is inspectable without running the hook.
                            try:
                                tokens = shlex.split(command)
                            except ValueError:
                                tokens = []
                            if len(tokens) >= 2 and tokens[0] == "cat" and tokens[1].startswith(("/", "~/")):
                                reminder = Path(tokens[1].replace("~/", str(home) + "/", 1))
                                text = inspect(reminder, "claude", "post-compaction reminder")
                                if text is not None and vault and vault.is_dir():
                                    for ref in re.findall(r"\b\d{2} [A-Za-z ]+/[^\n()`]+?\.md", text):
                                        target = vault / ref
                                        if not target.is_file():
                                            finding("compact-reference:" + ref, "claude",
                                                    "Compaction reminder points to a missing vault file",
                                                    [str(reminder), str(target)],
                                                    "Update the reminder to the current canonical file.")
                        # Only standalone absolute/home script paths are inspected.
                        # Inline commands are opaque; no shell expansion is performed.
                        match = re.fullmatch(r"(?:bash |sh |python3 )?[\"']?((?:/|~/)[^\n\"']+\.(?:sh|py))[\"']?", command)
                        hooks.append(dict(event=event, matcher=matcher,
                                          inspected=bool(match)))
                        if not match:
                            continue
                        path = Path(match[1].replace("~/", str(home) + "/", 1))
                        if not path.is_file():
                            finding("hook-missing:" + str(path), "claude", "Configured hook script is missing",
                                    [str(settings_path), str(path)], "Restore the script or remove the obsolete route.")
                            continue
                        body = inspect(path, "claude", "hook script; execution not observed") or ""
                        if event == "PreToolUse":
                            routes.setdefault(str(path), {"body": body, "matchers": []})["matchers"].append(matcher)
            for path, route in routes.items():
                try:
                    bash_routed = any(m in ("", "*") or re.search(m, "Bash") for m in route["matchers"])
                except re.error:
                    finding("hook-matcher:" + path, "claude", "Hook matcher could not be inspected",
                            [str(settings_path), path], "Check the matcher in the harness.", "unmeasured")
                    continue
                if re.search(r'\btool\s*(?:==|in).*?[\"\']Bash[\"\']', route["body"]) and not bash_routed:
                    finding("hook-bash-route:" + path, "claude", "Hook handles Bash but no route sends Bash to it",
                            [str(settings_path), path], "Add Bash to this hook's matcher and exercise a harmless rejection.")
        except (OSError, ValueError, TypeError, AttributeError):
            finding("claude-settings", "claude", "Hook configuration could not be inspected",
                    [str(settings_path)], "Validate the settings file.", "unmeasured")

    # Explicitly avoid a health score based on file presence or chosen size limits.
    for harness in ("claude", "cursor", "codex"):
        finding("delivery:" + harness, harness, "Effective context has not been observed by this audit",
                [f["path"] for f in files if f["harness"] == harness],
                "Attach a harness receipt for the instructions delivered to a named run.", "unmeasured")
    return dict(schema=SCHEMA, observed_at=datetime.now(timezone.utc).isoformat(),
                project=str(project), scope="local file and routing audit; read-only",
                files=files, skills=skills, hooks=hooks, memory_indexes=memory_indexes, findings=findings,
                coverage=dict(harnesses=["claude", "cursor", "codex"],
                              not_observed=["effective model context", "hook execution",
                                            "plugin activation", "cloud settings", "skill benefit",
                                            "instruction imports and dynamic memory retrieval"]))


def render_audit(report):
    lines = ["SETUP AUDIT", report["project"], "Observed " + report["observed_at"], ""]
    for status in ("attention", "unmeasured"):
        for item in report["findings"]:
            if item["status"] == status:
                lines.extend([f"[{status.upper()}] {item['harness']}: {item['title']}",
                              "  Next: " + item["action"]])
                lines.extend("  Source: " + path for path in item["evidence"][:2])
    lines.extend(["", f"Inspected {len(report['files'])} instruction/hook files and {len(report['skills'])} skill files.",
                  "File discovery does not prove delivery, use, or benefit."])
    return "\n".join(lines)
