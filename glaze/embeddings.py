"""Embedding layer: local sentence-transformers + numpy vector search.

Uses a regular SQLite table to store embeddings as BLOBs. Vector similarity
is computed in Python with numpy -- no native extensions needed.

Model: all-MiniLM-L6-v2 (384 dims, 80MB, runs on CPU in ~50ms per query).
"""

import sqlite3
from datetime import datetime

import numpy as np

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _serialize(vec) -> bytes:
    if isinstance(vec, np.ndarray):
        return vec.astype(np.float32).tobytes()
    return np.array(vec, dtype=np.float32).tobytes()


def _deserialize(blob: bytes, dim: int = 384) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32, count=dim)


def init_embedding_table(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS cube_embeddings (
        cube_id TEXT PRIMARY KEY,
        embedding BLOB NOT NULL,
        embedded_at TEXT NOT NULL,
        model TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
        dim INTEGER NOT NULL DEFAULT 384
    )""")
    conn.commit()


def embed_text(text: str) -> np.ndarray:
    model = _get_model()
    return model.encode(text, normalize_embeddings=True)


def embed_batch(texts: list[str]) -> np.ndarray:
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True, batch_size=32)


def store_embedding(conn: sqlite3.Connection, cube_id: str, embedding):
    conn.execute(
        "INSERT OR REPLACE INTO cube_embeddings (cube_id, embedding, embedded_at, model, dim) "
        "VALUES (?, ?, ?, ?, ?)",
        (cube_id, _serialize(embedding), datetime.utcnow().isoformat(),
         "all-MiniLM-L6-v2", 384),
    )


def embed_all_cubes(conn: sqlite3.Connection, batch_size: int = 64) -> dict:
    init_embedding_table(conn)

    already = set()
    try:
        rows = conn.execute("SELECT cube_id FROM cube_embeddings").fetchall()
        already = {r[0] if isinstance(r, tuple) else r["cube_id"] for r in rows}
    except Exception:
        pass

    cubes = conn.execute(
        "SELECT id, title, content, type FROM glaze_cubes WHERE merged_into IS NULL"
    ).fetchall()

    to_embed = [c for c in cubes if c["id"] not in already]
    if not to_embed:
        return {"embedded": 0, "total": len(cubes), "skipped": len(already)}

    embedded = 0
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i:i + batch_size]
        texts = [f"{c['title']} {(c['content'] or '')[:500]}" for c in batch]
        vectors = embed_batch(texts)

        for cube, vec in zip(batch, vectors):
            store_embedding(conn, cube["id"], vec)
            embedded += 1

        if (i + batch_size) % (batch_size * 4) == 0:
            conn.commit()

    conn.commit()
    return {"embedded": embedded, "total": len(cubes), "skipped": len(already)}


def _load_all_embeddings(conn: sqlite3.Connection) -> tuple[list[str], np.ndarray]:
    rows = conn.execute(
        "SELECT ce.cube_id, ce.embedding FROM cube_embeddings ce "
        "JOIN glaze_cubes gc ON ce.cube_id = gc.id "
        "WHERE gc.merged_into IS NULL "
        "AND gc.review_status IN ('approved', 'pending')"
    ).fetchall()

    if not rows:
        return [], np.array([])

    ids = []
    vecs = []
    for r in rows:
        cid = r[0] if isinstance(r, tuple) else r["cube_id"]
        blob = r[1] if isinstance(r, tuple) else r["embedding"]
        ids.append(cid)
        vecs.append(_deserialize(blob))

    return ids, np.vstack(vecs)


def semantic_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    threshold: float = 0.3,
) -> list[dict]:
    init_embedding_table(conn)

    query_vec = embed_text(query)
    ids, matrix = _load_all_embeddings(conn)

    if len(ids) == 0:
        return []

    similarities = matrix @ query_vec
    top_indices = np.argsort(similarities)[::-1][:limit * 2]

    cube_ids = [ids[i] for i in top_indices if similarities[i] >= threshold]
    if not cube_ids:
        return []

    placeholders = ",".join("?" for _ in cube_ids)
    rows = conn.execute(
        f"SELECT id, title, type, source, confidence, content, created_at "
        f"FROM glaze_cubes WHERE id IN ({placeholders})",
        cube_ids,
    ).fetchall()

    cube_map = {r["id"]: r for r in rows}

    results = []
    for i in top_indices:
        if similarities[i] < threshold:
            continue
        cid = ids[i]
        if cid not in cube_map:
            continue
        r = cube_map[cid]
        results.append({
            "id": cid,
            "title": r["title"],
            "type": r["type"],
            "source": r["source"],
            "confidence": r["confidence"],
            "content": (r["content"] or "")[:300],
            "created_at": r["created_at"] if "created_at" in r.keys() else "",
            "similarity": round(float(similarities[i]), 4),
        })
        if len(results) >= limit:
            break

    return results


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    semantic_weight: float = 0.6,
    fts_weight: float = 0.4,
) -> list[dict]:
    from glaze.db import search_cubes

    sem_results = semantic_search(conn, query, limit=limit * 2)
    try:
        fts_results = search_cubes(conn, query, limit * 2)
    except Exception:
        fts_results = []

    scores = {}
    details = {}

    for r in sem_results:
        cid = r["id"]
        sem_score = r["similarity"]
        scores[cid] = scores.get(cid, 0) + sem_score * semantic_weight
        details[cid] = {
            "id": cid, "title": r["title"], "type": r["type"],
            "source": r["source"], "confidence": r["confidence"],
            "content": r["content"], "created_at": r["created_at"],
            "semantic_score": sem_score, "fts_rank": None,
        }

    for i, r in enumerate(fts_results):
        cid = r["id"]
        fts_score = max(0, 1.0 - i * 0.05)
        scores[cid] = scores.get(cid, 0) + fts_score * fts_weight
        if cid not in details:
            details[cid] = {
                "id": cid, "title": r["title"], "type": r["type"],
                "source": r["source"], "confidence": r["confidence"],
                "content": (r["content"] or "")[:300],
                "created_at": r["created_at"] if "created_at" in r.keys() else "",
                "semantic_score": None, "fts_rank": i,
            }
        else:
            details[cid]["fts_rank"] = i

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [
        {**details[cid], "hybrid_score": round(score, 4)}
        for cid, score in ranked
    ]


def get_embedding_stats(conn: sqlite3.Connection) -> dict:
    init_embedding_table(conn)
    total_cubes = conn.execute(
        "SELECT COUNT(*) FROM glaze_cubes WHERE merged_into IS NULL"
    ).fetchone()[0]

    embedded = conn.execute("SELECT COUNT(*) FROM cube_embeddings").fetchone()[0]

    return {
        "total_cubes": total_cubes,
        "embedded": embedded,
        "coverage": round(embedded / total_cubes * 100, 1) if total_cubes > 0 else 0,
        "model": "all-MiniLM-L6-v2",
        "dim": 384,
    }
