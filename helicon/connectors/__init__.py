from helicon.connectors import claude_code, obsidian, git, chatgpt, cursor, agent_rules, skills, letta_memfs, graphiti, mem0, lifeos
from helicon.models import ConnectorResult

CONNECTORS = {
    "claude-code": claude_code.scan,
    "obsidian": obsidian.scan,
    "git": git.scan,
    "chatgpt": chatgpt.scan,
    "cursor": cursor.scan,
    "agent-rules": agent_rules.scan,
    # Skills are a durable agent-memory surface and rot like any other, but the
    # connector was written and never registered here — so the skills pillar was
    # dark for the one reason no config could fix. Opt-in via skill_roots.
    "skills": skills.scan,
    # Store adapters — opt-in: they return [] unless their key config
    # ("memfs_dir" / "uri" / "api_key" / "local") is present in
    # config["connectors"][name].
    "lifeos": lifeos.scan,
    "letta-memfs": letta_memfs.scan,
    "graphiti": graphiti.scan,
    "mem0": mem0.scan,
}


def scan_all(config: dict) -> list[ConnectorResult]:
    results = []
    connectors_config = config.get("connectors", {})
    for name, scan_fn in CONNECTORS.items():
        connector_config = connectors_config.get(name, {})
        if not connector_config.get("enabled", True):
            continue
        try:
            items = scan_fn(connector_config)
            results.extend(items)
        except Exception as e:
            print(f"  [!] Connector {name} failed: {e}")
    return results
