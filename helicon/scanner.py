import hashlib
import uuid
from datetime import datetime

from helicon.models import ConnectorResult, HeliconCube
from helicon.connectors import scan_all
from helicon.db import init_db, insert_cube, log_scan_complete, log_scan_start
from helicon.qwen import get_client, summarize_cube, check_novelty, resolve_model


def make_id() -> str:
    return f"gc_{uuid.uuid4().hex[:12]}"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def result_to_cube(result: ConnectorResult) -> HeliconCube:
    now = datetime.utcnow().isoformat()
    return HeliconCube(
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


def collect_present_hashes(config: dict, source: str | None = None) -> dict:
    """Re-scan configured sources and group content hashes by (source, file-scope).

    Returns {(source, scope): set(content_hash)} where scope is the file part of
    source_ref (source_ref_scope). Hashes are computed exactly the way ingestion
    does — content_hash over the raw connector content, the same call
    result_to_cube makes — so reconcile comparisons against stored cubes match.
    """
    from helicon.reconcile import source_ref_scope

    scopes: dict = {}
    for result in scan_all(config):
        if source and result.source != source:
            continue
        key = (result.source, source_ref_scope(result.source_ref))
        scopes.setdefault(key, set()).add(content_hash(result.content))
    return scopes


def enrich_with_qwen(cube: HeliconCube, qwen_client, existing_titles: list[str], config: dict | None = None) -> HeliconCube:
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
    db_path = config.get("db_path", "data/helicon.db")
    conn = init_db(db_path)
    # A scan_log row per scan: an incomplete row (no completed_at) marks a
    # crashed scan, and battery verdicts read the last completed row to say
    # whether memory is stale or the scan is.
    scan_id = log_scan_start(conn, list(config.get("connectors", {}).keys()))

    qwen_client = None
    if use_qwen:
        qwen_client = get_client(config)

    existing_titles = []
    if qwen_client:
        rows = conn.execute("SELECT title FROM helicon_cubes WHERE type IN ('memory','project','draft') LIMIT 50").fetchall()
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
    log_scan_complete(conn, scan_id, added=added, skipped=skipped)

    stats = {
        "scan_id": scan_id,
        "total_raw": len(results),
        "added": added,
        "skipped": skipped,
        "enriched": enriched,
        "qwen_enabled": qwen_client is not None,
    }

    cursor = conn.execute("SELECT source, COUNT(*) as cnt FROM helicon_cubes GROUP BY source")
    stats["by_source"] = {row["source"]: row["cnt"] for row in cursor.fetchall()}

    cursor = conn.execute("SELECT type, COUNT(*) as cnt FROM helicon_cubes GROUP BY type")
    stats["by_type"] = {row["type"]: row["cnt"] for row in cursor.fetchall()}

    total = conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
    stats["total_in_db"] = total

    conn.close()
    return stats
