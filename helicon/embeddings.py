"""Embedding layer: local sentence-transformers + numpy vector search.

Uses a regular SQLite table to store embeddings as BLOBs. Vector similarity
is computed in Python with numpy -- no native extensions needed.

Model: all-MiniLM-L6-v2 (384 dims, 80MB, runs on CPU in ~50ms per query).
"""

import glob
import os
import sqlite3
from datetime import datetime

import numpy as np

_model = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def _hf_cache_dir() -> str:
    """The huggingface hub cache, honoring HF_HUB_CACHE / HF_HOME if set."""
    if os.environ.get("HF_HUB_CACHE"):
        return os.environ["HF_HUB_CACHE"]
    home = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    return os.path.join(home, "hub")


def _configure_hf_env():
    """Make the embedding model load fast and quiet — the cost that made
    `helicon battery` feel broken (8.9s wall, ~4.5s of it HF network re-checks
    of an already-cached model, plus a warning + progress bar on every call).
    Set BEFORE sentence_transformers imports huggingface_hub. All via
    setdefault, so an explicit user override always wins."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    # Only force offline when the model is already cached — a first run still
    # needs the network to download it. Offline skips the ~4.5s hub round-trip
    # (and the unauthenticated-requests warning it emits) on every later call.
    cached = glob.glob(os.path.join(
        _hf_cache_dir(), f"models--sentence-transformers--{_MODEL_NAME}"))
    if cached:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _get_model():
    global _model
    if _model is None:
        _configure_hf_env()
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
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


_provider_cache = None


def _embed_provider():
    """Which embedding backend to use, resolved once from config. If config has
    an `embeddings` block with api_key + base_url, the whole retrieval stack is
    Qwen-native (Alibaba Model Studio text-embedding-v4). Otherwise falls back to
    local MiniLM. Returns (kind, client, model_name, dim)."""
    global _provider_cache
    if _provider_cache is not None:
        return _provider_cache
    prov = ("local", None, "all-MiniLM-L6-v2", 384)
    try:
        from helicon.config import load_config
        e = (load_config().get("embeddings") or {})
        if e.get("api_key") and e.get("base_url"):
            from openai import OpenAI
            client = OpenAI(api_key=e["api_key"], base_url=e["base_url"])
            prov = ("qwen", client, e.get("model", "text-embedding-v4"), int(e.get("dim", 1024)))
    except Exception:
        pass
    _provider_cache = prov
    return prov


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return (v / n) if n else v


def embed_text(text: str) -> np.ndarray:
    kind, client, model, dim = _embed_provider()
    if kind == "qwen":
        r = client.embeddings.create(model=model, input=[text[:8000]],
                                     dimensions=dim, encoding_format="float")
        return _normalize(np.array(r.data[0].embedding, dtype=np.float32))
    return _get_model().encode(text, normalize_embeddings=True)


def embed_batch(texts: list[str]) -> np.ndarray:
    kind, client, model, dim = _embed_provider()
    if kind == "qwen":
        out = []
        for i in range(0, len(texts), 10):  # Model Studio caps at 10 inputs/call
            r = client.embeddings.create(model=model, input=[t[:8000] for t in texts[i:i + 10]],
                                         dimensions=dim, encoding_format="float")
            out.extend(_normalize(np.array(d.embedding, dtype=np.float32)) for d in r.data)
        return np.array(out, dtype=np.float32)
    return _get_model().encode(texts, normalize_embeddings=True, batch_size=32)


def store_embedding(conn: sqlite3.Connection, cube_id: str, embedding):
    kind, _c, model, dim = _embed_provider()
    mname = model if kind == "qwen" else "all-MiniLM-L6-v2"
    d = dim if kind == "qwen" else 384
    conn.execute(
        "INSERT OR REPLACE INTO cube_embeddings (cube_id, embedding, embedded_at, model, dim) "
        "VALUES (?, ?, ?, ?, ?)",
        (cube_id, _serialize(embedding), datetime.utcnow().isoformat(), mname, d),
    )


def embed_all_cubes(conn: sqlite3.Connection, batch_size: int = 64) -> dict:
    init_embedding_table(conn)

    # "Already embedded" means embedded with the CURRENT provider's dimension.
    # Switching models (MiniLM 384 -> Qwen 1024) makes old rows not count, so a
    # plain `helicon embed` re-embeds everything with the new model (store_embedding
    # REPLACEs the stale row by cube_id).
    _k, _c, _m, _dim = _embed_provider()
    cur_dim = _dim if _k == "qwen" else 384
    already = set()
    try:
        rows = conn.execute("SELECT cube_id FROM cube_embeddings WHERE dim = ?", (cur_dim,)).fetchall()
        already = {r[0] if isinstance(r, tuple) else r["cube_id"] for r in rows}
    except Exception:
        pass

    cubes = conn.execute(
        "SELECT id, title, content, type FROM helicon_cubes WHERE merged_into IS NULL"
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
    _k, _c, _m, _dim = _embed_provider()
    cur_dim = _dim if _k == "qwen" else 384
    rows = conn.execute(
        "SELECT ce.cube_id, ce.embedding FROM cube_embeddings ce "
        "JOIN helicon_cubes gc ON ce.cube_id = gc.id "
        "WHERE gc.merged_into IS NULL "
        "AND gc.review_status IN ('approved', 'pending') "
        "AND ce.dim = ?",
        (cur_dim,),
    ).fetchall()

    if not rows:
        return [], np.array([])

    ids = []
    vecs = []
    for r in rows:
        cid = r[0] if isinstance(r, tuple) else r["cube_id"]
        blob = r[1] if isinstance(r, tuple) else r["embedding"]
        ids.append(cid)
        vecs.append(_deserialize(blob, cur_dim))

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
        f"FROM helicon_cubes WHERE id IN ({placeholders})",
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


def rerank(query: str, documents: list[str], top_n: int):
    """Two-stage retrieval: reorder candidates with qwen3-rerank (Alibaba Model
    Studio, native rerank endpoint — flat OpenAI SDK has no rerank, so raw POST).
    Returns [(orig_index, relevance_score), ...] or None if reranking isn't
    configured/available, in which case the caller keeps the hybrid order."""
    kind, _c, _m, _d = _embed_provider()
    if kind != "qwen" or not documents:
        return None
    try:
        import requests
        from helicon.config import load_config
        e = load_config().get("embeddings") or {}
        host = e["base_url"].split("/compatible-mode")[0]
        r = requests.post(
            f"{host}/api/v1/services/rerank/text-rerank/text-rerank",
            headers={"Authorization": f"Bearer {e['api_key']}", "Content-Type": "application/json"},
            json={"model": "qwen3-rerank",
                  "input": {"query": query, "documents": documents},
                  "parameters": {"top_n": top_n, "return_documents": False}},
            timeout=20,
        )
        r.raise_for_status()
        return [(x["index"], x["relevance_score"]) for x in r.json()["output"]["results"]]
    except Exception:
        return None


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    semantic_weight: float = 0.6,
    fts_weight: float = 0.4,
) -> list[dict]:
    from helicon.db import search_cubes

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

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # Two-stage: over-fetch, then let qwen3-rerank re-order the top candidates.
    cand = ranked[: max(limit * 4, 20)]
    docs = [f"{details[cid]['title']} {(details[cid]['content'] or '')[:400]}" for cid, _ in cand]
    order = rerank(query, docs, limit)
    if order:
        return [
            {**details[cand[idx][0]], "hybrid_score": round(cand[idx][1], 4),
             "rerank_score": round(rscore, 4)}
            for idx, rscore in order
        ]
    return [
        {**details[cid], "hybrid_score": round(score, 4)}
        for cid, score in ranked[:limit]
    ]


def get_embedding_stats(conn: sqlite3.Connection) -> dict:
    init_embedding_table(conn)
    total_cubes = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE merged_into IS NULL"
    ).fetchone()[0]

    embedded = conn.execute("SELECT COUNT(*) FROM cube_embeddings").fetchone()[0]

    return {
        "total_cubes": total_cubes,
        "embedded": embedded,
        "coverage": round(embedded / total_cubes * 100, 1) if total_cubes > 0 else 0,
        "model": _embed_provider()[2],
        "dim": _embed_provider()[3],
    }
