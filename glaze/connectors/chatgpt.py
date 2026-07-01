import json
import os
from datetime import datetime

from glaze.models import ConnectorResult


def scan(config: dict) -> list[ConnectorResult]:
    export_path = os.path.expanduser(config.get("export_path", ""))
    if not export_path or not os.path.exists(export_path):
        return []

    results = []

    conversations_path = os.path.join(export_path, "conversations.json")
    if os.path.exists(conversations_path):
        with open(conversations_path) as f:
            conversations = json.load(f)

        for conv in conversations:
            title = conv.get("title", "Untitled")
            create_time = conv.get("create_time", 0)
            created_at = datetime.fromtimestamp(create_time).isoformat() if create_time else ""

            messages = []
            mapping = conv.get("mapping", {})
            for node_id, node in mapping.items():
                msg = node.get("message")
                if not msg:
                    continue
                role = msg.get("author", {}).get("role", "")
                parts = msg.get("content", {}).get("parts", [])
                text = " ".join(str(p) for p in parts if isinstance(p, str))

                if role == "assistant" and len(text) > 50:
                    messages.append(text[:500])

            if not messages:
                continue

            content = f"ChatGPT conversation: {title}\n\n" + "\n---\n".join(messages[:5])
            tags = ["chatgpt", "conversation"]

            results.append(ConnectorResult(
                source="chatgpt",
                source_ref=f"chatgpt/{conv.get('id', title[:30])}",
                type="session",
                title=f"ChatGPT: {title[:60]}",
                content=content[:2000],
                created_at=created_at,
                tags=tags,
                metadata={"message_count": len(messages)},
            ))

    return results
