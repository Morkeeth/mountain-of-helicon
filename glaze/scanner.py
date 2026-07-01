import hashlib
import uuid
from datetime import datetime

from glaze.models import ConnectorResult, GlazeCube
from glaze.connectors import scan_all
from glaze.db import init_db, insert_cube
from glaze.qwen import get_client, summarize_cube, check_novelty, resolve_model


def make_id() -> str:
    return f"gc_{uuid.uuid4().hex[:12]}"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def result_to_cube(result: ConnectorResult) -> GlazeCube:
    now = datetime.utcnow().isoformat()
    return GlazeCube(
        id=make_id(),
        source=result.source,
        source_ref=result.source_ref,
        type=result.type,
        title=result.title,
        content=result.content,
        content_hash=content_hash(result.content),
        created_at=result.created_at or now,
        valid_from=result.created_at or now,
        last_reinforced=result.created_at or now,
        confidence=1.0,
        tags=result.tags,
        metadata=result.metadata,
    )


def enrich_with_qwen(cube: GlazeCube, qwen_client, existing_titles: list[str], config: dict | None = None) -> GlazeCube:
    if not qwen_client:
        return cube

    if cube.type in ("code", "file_created") and len(cube.content) < 100:
        return cube

    fast_model = resolve_model("fast", config)
    default_model = resolve_model("default", config)

    try:
        summary = summarize_cube(qwen_client, cube.content, model=fast_model)
        if summary:
            cube.summary = summary.get("summary", "")
            if summary.get("tags"):
                cube.tags = list(set(cube.tags + summary["tags"]))
    except Exception:
        pass

    if existing_titles and cube.type in ("memory", "project", "draft", "idea"):
        try:
            novelty = check_novelty(qwen_client, cube.content[:300], existing_titles[:15], model=fast_model)
            if novelty:
                cube.novelty_action = novelty.get("action", "ADD")
                cube.novelty_score = 1.0 if novelty.get("action") == "ADD" else 0.3
        except Exception:
            pass

    return cube


def run_scan(config: dict, use_qwen: bool = False) -> dict:
    db_path = config.get("db_path", "data/glaze.db")
    conn = init_db(db_path)

    qwen_client = None
    if use_qwen:
        qwen_client = get_client(config)

    existing_titles = []
    if qwen_client:
        rows = conn.execute("SELECT title FROM glaze_cubes WHERE type IN ('memory','project','draft') LIMIT 50").fetchall()
        existing_titles = [r["title"] for r in rows]

    print("Scanning all connectors...")
    results = scan_all(config)
    print(f"  Found {len(results)} raw items")

    added = 0
    skipped = 0
    enriched = 0
    for result in results:
        cube = result_to_cube(result)
        if qwen_client and cube.type in ("memory", "project", "draft", "idea"):
            cube = enrich_with_qwen(cube, qwen_client, existing_titles)
            enriched += 1
        if insert_cube(conn, cube):
            added += 1
        else:
            skipped += 1

    conn.commit()

    stats = {
        "total_raw": len(results),
        "added": added,
        "skipped": skipped,
        "enriched": enriched,
        "qwen_enabled": qwen_client is not None,
    }

    cursor = conn.execute("SELECT source, COUNT(*) as cnt FROM glaze_cubes GROUP BY source")
    stats["by_source"] = {row["source"]: row["cnt"] for row in cursor.fetchall()}

    cursor = conn.execute("SELECT type, COUNT(*) as cnt FROM glaze_cubes GROUP BY type")
    stats["by_type"] = {row["type"]: row["cnt"] for row in cursor.fetchall()}

    total = conn.execute("SELECT COUNT(*) FROM glaze_cubes").fetchone()[0]
    stats["total_in_db"] = total

    conn.close()
    return stats
