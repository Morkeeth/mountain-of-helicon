import json
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime

import numpy as np

from glaze.qwen import complete_json


def make_id() -> str:
    return f"cons_{uuid.uuid4().hex[:10]}"


# Tokens that make terrible memory "topics": source-code filenames, extensions,
# and scan-artifact metadata labels. A cluster themed "app.tsx" or "created:" is
# noise, not a concept. We refuse to build title-word clusters around these.
_CODE_EXTENSIONS = (".tsx", ".ts", ".py", ".js", ".jsx", ".md", ".json",
                    ".sol", ".css", ".html", ".sh", ".yml", ".yaml", ".toml")
_ARTIFACT_TOKENS = {"created:", "edited:", "created", "edited", "code", "commit",
                    "markdown", "file", "files", "update", "updated", "change",
                    "changes", "uncommitted", "index", "config", "app", "main",
                    "git", "diff", "merge", "branch", "repo"}


def _is_junk_topic_word(word: str) -> bool:
    """A title word that would make a meaningless cluster topic."""
    w = word.lower().strip().strip("[]()")
    if w in _ARTIFACT_TOKENS:
        return True
    if w.isdigit():  # bare years / numbers like "2026" are not topics
        return True
    if w.endswith(_CODE_EXTENSIONS):
        return True
    if w.endswith(":"):  # metadata labels like "created:"
        return True
    return False


def _embedding_clusters(conn: sqlite3.Connection, threshold: float = 0.75) -> list[dict]:
    """Find clusters using embedding cosine similarity. Items with similarity
    above threshold get grouped together."""
    try:
        from glaze.embeddings import _load_all_embeddings, _deserialize
        ids, matrix = _load_all_embeddings(conn)
    except Exception:
        return []

    if len(ids) < 2:
        return []

    sim_matrix = matrix @ matrix.T

    assigned = set()
    clusters = []

    for i in range(len(ids)):
        if ids[i] in assigned:
            continue
        neighbors = []
        for j in range(len(ids)):
            if i == j or ids[j] in assigned:
                continue
            if sim_matrix[i, j] >= threshold:
                neighbors.append(j)

        if len(neighbors) < 2:
            continue

        cluster_indices = [i] + neighbors[:19]
        cluster_ids = [ids[idx] for idx in cluster_indices]
        for cid in cluster_ids:
            assigned.add(cid)

        cubes_data = conn.execute(
            f"SELECT id, title, type, source, confidence FROM glaze_cubes "
            f"WHERE id IN ({','.join('?' for _ in cluster_ids)})",
            cluster_ids,
        ).fetchall()
        cube_map = {r["id"]: r for r in cubes_data}

        avg_sim = float(np.mean([sim_matrix[i, j] for j in neighbors[:19]]))
        anchor = cube_map.get(ids[i])
        raw_title = anchor["title"] if anchor else ids[i]
        # Strip scan-artifact prefixes ("Created: route.ts" -> "route.ts") so the
        # seed reads as a concept, not a git action. Final topic is Qwen's title anyway.
        for prefix in ("Created:", "Edited:", "Deleted:", "[world-relay]", "[glaze]"):
            if raw_title.startswith(prefix):
                raw_title = raw_title[len(prefix):].strip()
        topic = raw_title[:40]

        clusters.append({
            "topic": topic,
            "method": "embedding_similarity",
            "avg_similarity": round(avg_sim, 3),
            "cubes": [{"id": cube_map[cid]["id"], "title": cube_map[cid]["title"],
                        "type": cube_map[cid]["type"], "source": cube_map[cid]["source"],
                        "confidence": cube_map[cid]["confidence"]}
                       for cid in cluster_ids if cid in cube_map],
            "count": len(cluster_ids),
        })

    return sorted(clusters, key=lambda c: -c["count"])


def find_clusters(conn: sqlite3.Connection, min_overlap: int = 2) -> list[dict]:
    embedding_clusters = _embedding_clusters(conn)

    rows = conn.execute(
        "SELECT id, title, tags, type, source, confidence, created_at "
        "FROM glaze_cubes WHERE merged_into IS NULL AND review_status != 'killed' "
        "ORDER BY created_at DESC LIMIT 500"
    ).fetchall()

    tag_to_cubes = defaultdict(list)
    for row in rows:
        tags = json.loads(row["tags"]) if row["tags"] else []
        for tag in tags:
            tag_to_cubes[tag.lower()].append(row)

    title_words = defaultdict(list)
    for row in rows:
        words = set(row["title"].lower().replace("-", " ").replace("_", " ").split())
        stopwords = {"the", "a", "an", "is", "of", "for", "and", "in", "to", "with", "on", "at", "by", "from"}
        meaningful = words - stopwords
        for word in meaningful:
            if len(word) > 3 and not _is_junk_topic_word(word):
                title_words[word].append(row)

    clusters = list(embedding_clusters)
    seen_ids = set()
    for ec in embedding_clusters:
        cube_ids = tuple(sorted(c["id"] for c in ec["cubes"]))
        seen_ids.add(cube_ids)

    for tag, cubes in sorted(tag_to_cubes.items(), key=lambda x: -len(x[1])):
        if len(cubes) < min_overlap:
            continue
        # A tag like "code"/"markdown"/"git" is a category spanning hundreds of
        # unrelated cubes, not a coherent memory to merge. Skip it.
        if _is_junk_topic_word(tag):
            continue
        cube_ids = tuple(sorted(c["id"] for c in cubes))
        if cube_ids in seen_ids:
            continue
        seen_ids.add(cube_ids)
        clusters.append({
            "topic": tag,
            "method": "tag_overlap",
            "cubes": [{"id": c["id"], "title": c["title"], "type": c["type"],
                       "source": c["source"], "confidence": c["confidence"]} for c in cubes[:20]],
            "count": len(cubes),
        })

    for word, cubes in sorted(title_words.items(), key=lambda x: -len(x[1])):
        if len(cubes) < 3:
            continue
        cube_ids = tuple(sorted(c["id"] for c in cubes))
        if cube_ids in seen_ids:
            continue
        seen_ids.add(cube_ids)
        clusters.append({
            "topic": word,
            "method": "title_similarity",
            "cubes": [{"id": c["id"], "title": c["title"], "type": c["type"],
                       "source": c["source"], "confidence": c["confidence"]} for c in cubes[:20]],
            "count": len(cubes),
        })

    return sorted(clusters, key=lambda c: -c["count"])[:30]


def consolidate_cluster(conn: sqlite3.Connection, qwen_client, cluster: dict) -> dict | None:
    cube_ids = [c["id"] for c in cluster["cubes"][:15]]
    contents = []
    for cid in cube_ids:
        row = conn.execute("SELECT title, content, type, source FROM glaze_cubes WHERE id = ?", (cid,)).fetchone()
        if row:
            contents.append(f"[{row['source']}/{row['type']}] {row['title']}: {row['content'][:300]}")

    combined = "\n\n".join(contents)

    if qwen_client:
        result = complete_json(
            qwen_client,
            "You are a memory consolidation engine. Like the brain during sleep, merge related memories into a single coherent summary.",
            f"""These {len(contents)} memory items are about "{cluster['topic']}". Consolidate them into one clear summary.

Items:
{combined}

Return JSON:
{{
  "title": "consolidated title (under 60 chars)",
  "summary": "2-4 sentence synthesis of all items - what matters, what's current, what's outdated",
  "confidence": 0.0-1.0 (how reliable is this consolidated view),
  "insights": ["key insight 1", "key insight 2"],
  "outdated": ["anything in these items that is now stale"]
}}""",
        )
    else:
        result = {
            "title": f"Consolidated: {cluster['topic']}",
            "summary": f"{len(contents)} items about {cluster['topic']} from {len(set(c['source'] for c in cluster['cubes']))} sources",
            "confidence": sum(c["confidence"] for c in cluster["cubes"]) / len(cluster["cubes"]),
            "insights": [],
            "outdated": [],
        }

    if not result:
        return None

    now = datetime.utcnow().isoformat()
    cons_id = make_id()

    # The stored topic drives both the UI label and the consolidation eval query.
    # Qwen's synthesized title is far cleaner than the raw cluster seed (which for
    # code/git cubes is a filename), so prefer it. Fall back to the seed only if
    # Qwen returned no title.
    topic = result.get("title") or cluster["topic"]

    conn.execute(
        "INSERT INTO consolidations (id, title, summary, cube_ids, cube_count, created_at, confidence, topic) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (cons_id, result.get("title", ""), result.get("summary", ""),
         json.dumps(cube_ids), len(cube_ids), now,
         result.get("confidence", 0.5), topic),
    )
    conn.commit()

    return {
        "id": cons_id,
        "title": result.get("title", ""),
        "summary": result.get("summary", ""),
        "cube_count": len(cube_ids),
        "insights": result.get("insights", []),
        "outdated": result.get("outdated", []),
        "confidence": result.get("confidence", 0.5),
    }


def run_consolidation(conn: sqlite3.Connection, qwen_client=None, max_clusters: int = 10) -> dict:
    clusters = find_clusters(conn)
    consolidated = []

    for cluster in clusters[:max_clusters]:
        result = consolidate_cluster(conn, qwen_client, cluster)
        if result:
            consolidated.append(result)

    return {
        "clusters_found": len(clusters),
        "consolidated": len(consolidated),
        "results": consolidated,
    }


def get_consolidations(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM consolidations ORDER BY created_at DESC"
    ).fetchall()
    results = []
    for row in rows:
        r = dict(row)
        r["cube_ids"] = json.loads(r["cube_ids"]) if r["cube_ids"] else []
        r["metadata"] = json.loads(r["metadata"]) if r["metadata"] else {}
        results.append(r)
    return results
