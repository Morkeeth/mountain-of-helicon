from glaze.connectors import claude_code, obsidian, git, chatgpt, cursor, agent_rules
from glaze.models import ConnectorResult

CONNECTORS = {
    "claude-code": claude_code.scan,
    "obsidian": obsidian.scan,
    "git": git.scan,
    "chatgpt": chatgpt.scan,
    "cursor": cursor.scan,
    "agent-rules": agent_rules.scan,
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
