import json
import re
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import datetime

from glaze.qwen import complete_json


def make_id(prefix: str = "ent") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


ENTITY_PATTERNS = {
    "project": [
        r"\b(GLAZE)\b",
        r"\bproject[_\-\s](\w+)",
    ],
    "person": [
        r"\b[A-Z][a-z]+\s(?:said|mentioned|reviewed|approved|killed|decided)\b",
    ],
    "tool": [
        r"\b(Claude Code|Obsidian|Cursor|ChatGPT|Qwen|FastAPI|React|Vite|SQLite|Docker)\b",
        r"\b(MCP|Vercel|GitHub|Linear|Telegram|Slack)\b",
    ],
    "concept": [
        r"\b(Ebbinghaus|SAGE|SSGM|MetaMem|MemCube|GlazeCube)\b",
        r"\b(forgetting curve|novelty gate|memory audit|knowledge graph)\b",
    ],
}


def extract_entities_regex(content: str, title: str = "") -> list[dict]:
    text = f"{title} {content}"
    entities = []
    seen = set()
    for etype, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                name = match.group(1) if match.lastindex else match.group(0)
                name = name.strip()
                key = (name.lower(), etype)
                if key not in seen:
                    seen.add(key)
                    entities.append({"name": name, "type": etype})
    return entities


def extract_entities_qwen(client, content: str, title: str = "") -> list[dict]:
    text = f"Title: {title}\nContent: {content[:1500]}"
    result = complete_json(
        client,
        "Extract named entities from this AI agent output. Return entities that are specific and meaningful.",
        f"""Extract entities from this text and return JSON array:
[{{"name": "entity name", "type": "project|person|tool|concept|decision|file"}}]

Focus on: project names, people, tools/technologies, key decisions, specific files or artifacts.
Skip generic words. Max 15 entities.

{text}""",
    )
    if not result or not isinstance(result, list):
        return []
    return [e for e in result if isinstance(e, dict) and "name" in e and "type" in e]


def build_graph(conn: sqlite3.Connection, qwen_client=None, limit: int = 500):
    now = datetime.utcnow().isoformat()

    rows = conn.execute(
        "SELECT id, title, content, type, source, created_at, tags "
        "FROM glaze_cubes WHERE merged_into IS NULL "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()

    entity_index = {}
    cube_entities = defaultdict(list)

    for row in rows:
        if qwen_client:
            entities = extract_entities_qwen(qwen_client, row["content"], row["title"])
        else:
            entities = extract_entities_regex(row["content"], row["title"])

        for ent in entities:
            key = ent["name"].lower()
            if key not in entity_index:
                entity_index[key] = {
                    "id": make_id("ent"),
                    "name": ent["name"],
                    "entity_type": ent["type"],
                    "mention_count": 0,
                    "first_seen": row["created_at"],
                    "last_seen": row["created_at"],
                }
            entity_index[key]["mention_count"] += 1
            entity_index[key]["last_seen"] = max(entity_index[key]["last_seen"], row["created_at"])
            cube_entities[row["id"]].append(key)

    conn.execute("DELETE FROM entities")
    conn.execute("DELETE FROM edges")

    for key, ent in entity_index.items():
        conn.execute(
            "INSERT INTO entities (id, name, entity_type, mention_count, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ent["id"], ent["name"], ent["entity_type"], ent["mention_count"],
             ent["first_seen"], ent["last_seen"]),
        )

    for cube_id, ent_keys in cube_entities.items():
        ent_id = entity_index[ent_keys[0]]["id"] if ent_keys else None
        if ent_id:
            conn.execute(
                "INSERT INTO edges (source_id, target_id, source_kind, target_kind, relation, weight, created_at) "
                "VALUES (?, ?, 'cube', 'entity', 'mentions', 1.0, ?)",
                (cube_id, ent_id, now),
            )
        for i, k1 in enumerate(ent_keys):
            for k2 in ent_keys[i + 1:]:
                conn.execute(
                    "INSERT INTO edges (source_id, target_id, source_kind, target_kind, relation, weight, created_at) "
                    "VALUES (?, ?, 'entity', 'entity', 'co_occurs', 1.0, ?)",
                    (entity_index[k1]["id"], entity_index[k2]["id"], now),
                )

    audit_contradictions = conn.execute(
        "SELECT target_id, details FROM audit_log WHERE audit_type = 'factual' AND severity IN ('critical', 'warning')"
    ).fetchall()

    for row in audit_contradictions:
        details = json.loads(row["details"]) if row["details"] else {}
        cube_a = details.get("cube_a")
        cube_b = details.get("cube_b")
        if cube_a and cube_b:
            conn.execute(
                "INSERT INTO edges (source_id, target_id, source_kind, target_kind, relation, weight, created_at) "
                "VALUES (?, ?, 'cube', 'cube', 'contradicts', 2.0, ?)",
                (cube_a, cube_b, now),
            )

    conn.commit()

    return {
        "entities": len(entity_index),
        "cubes_processed": len(rows),
        "edges": conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
    }


def get_graph_data(conn: sqlite3.Connection) -> dict:
    entities = conn.execute(
        "SELECT id, name, entity_type, mention_count FROM entities ORDER BY mention_count DESC LIMIT 100"
    ).fetchall()

    cubes = conn.execute(
        "SELECT id, title, type, source, confidence, review_status "
        "FROM glaze_cubes WHERE merged_into IS NULL "
        "AND id IN (SELECT DISTINCT source_id FROM edges WHERE source_kind = 'cube' "
        "UNION SELECT DISTINCT target_id FROM edges WHERE target_kind = 'cube') "
        "LIMIT 200"
    ).fetchall()

    edges = conn.execute(
        "SELECT source_id, target_id, source_kind, target_kind, relation, weight FROM edges"
    ).fetchall()

    nodes = []
    for e in entities:
        nodes.append({
            "id": e["id"], "label": e["name"], "kind": "entity",
            "type": e["entity_type"], "size": e["mention_count"],
        })
    for c in cubes:
        nodes.append({
            "id": c["id"], "label": c["title"][:40], "kind": "cube",
            "type": c["type"], "size": 1, "confidence": c["confidence"],
            "review_status": c["review_status"], "source": c["source"],
        })

    links = [
        {
            "source": e["source_id"], "target": e["target_id"],
            "relation": e["relation"], "weight": e["weight"],
        }
        for e in edges
    ]

    return {"nodes": nodes, "links": links}


def get_entity_details(conn: sqlite3.Connection, entity_id: str) -> dict | None:
    ent = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not ent:
        return None

    cube_edges = conn.execute(
        "SELECT source_id FROM edges WHERE target_id = ? AND source_kind = 'cube' AND relation = 'mentions'",
        (entity_id,),
    ).fetchall()

    cube_ids = [e["source_id"] for e in cube_edges]
    cubes = []
    for cid in cube_ids[:20]:
        row = conn.execute(
            "SELECT id, title, type, source, confidence, review_status, created_at "
            "FROM glaze_cubes WHERE id = ?", (cid,)
        ).fetchone()
        if row:
            cubes.append(dict(row))

    related = conn.execute(
        "SELECT DISTINCT e2.target_id, ent.name, ent.entity_type "
        "FROM edges e1 "
        "JOIN edges e2 ON e1.source_id = e2.source_id AND e2.target_id != ? "
        "JOIN entities ent ON ent.id = e2.target_id "
        "WHERE e1.target_id = ? AND e1.relation = 'mentions' AND e2.relation = 'mentions'",
        (entity_id, entity_id),
    ).fetchall()

    return {
        "entity": dict(ent),
        "cubes": cubes,
        "related_entities": [dict(r) for r in related[:15]],
    }
