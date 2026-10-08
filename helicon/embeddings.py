"""Embedding layer: local sentence-transformers + numpy vector search.

Uses a regular SQLite table to store embeddings as BLOBs. Vector similarity
is computed in Python with numpy -- no native extensions needed.

Model: all-MiniLM-L6-v2 (384 dims, 80MB, runs on CPU in ~50ms per query).
"""
from __future__ import annotations

import glob
import os
import sqlite3
from datetime import datetime, timezone

# numpy is behind the `retrieval` extra. The keyword-only context policy in this file
# (title_matches, diversify, apply_context_policy) is what every retrieval path ends
# in, including the FTS fallback a store takes before its first `helicon embed`, so
# the module must import without it. Vector work fails at first use, by name.
from helicon.extras import LazyModule
np = LazyModule("numpy")

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
    """Which embedding backend to use, resolved once from config.

    There is no default vendor and no default remote model. Remote embeddings
    are used only when the config `embeddings` block names all three of
    base_url, model and dim (any OpenAI-compatible embeddings endpoint, a
    local one included, in which case api_key may be empty). Anything less
    means the local all-MiniLM-L6-v2 model.

    Returns (kind, client, model_name, dim)."""
    global _provider_cache
    if _provider_cache is not None:
        return _provider_cache
    prov = ("local", None, "all-MiniLM-L6-v2", 384)
    try:
        from helicon.config import load_config
        e = (load_config().get("embeddings") or {})
        base_url, model, dim = e.get("base_url"), e.get("model"), int(e.get("dim") or 0)
        if base_url and model and dim > 0:
            from openai import OpenAI
            # A local endpoint needs no key, but the SDK refuses an empty one.
            client = OpenAI(api_key=e.get("api_key") or "not-needed", base_url=base_url)
            prov = ("remote", client, model, dim)
    except Exception:
        pass
    _provider_cache = prov
    return prov


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return (v / n) if n else v


def embed_text(text: str) -> np.ndarray:
    kind, client, model, dim = _embed_provider()
    if kind == "remote":
        r = client.embeddings.create(model=model, input=[text[:8000]],
                                     dimensions=dim, encoding_format="float")
        return _normalize(np.array(r.data[0].embedding, dtype=np.float32))
    return _get_model().encode(text, normalize_embeddings=True)


def embed_batch(texts: list[str]) -> np.ndarray:
    kind, client, model, dim = _embed_provider()
    if kind == "remote":
        out = []
        for i in range(0, len(texts), 10):  # some endpoints cap a call at 10 inputs
            r = client.embeddings.create(model=model, input=[t[:8000] for t in texts[i:i + 10]],
                                         dimensions=dim, encoding_format="float")
            out.extend(_normalize(np.array(d.embedding, dtype=np.float32)) for d in r.data)
        return np.array(out, dtype=np.float32)
    return _get_model().encode(texts, normalize_embeddings=True, batch_size=32)


def store_embedding(conn: sqlite3.Connection, cube_id: str, embedding):
    kind, _c, model, dim = _embed_provider()
    mname = model if kind == "remote" else "all-MiniLM-L6-v2"
    d = dim if kind == "remote" else 384
    conn.execute(
        "INSERT OR REPLACE INTO cube_embeddings (cube_id, embedding, embedded_at, model, dim) "
        "VALUES (?, ?, ?, ?, ?)",
        (cube_id, _serialize(embedding), datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), mname, d),
    )


def embed_all_cubes(conn: sqlite3.Connection, batch_size: int = 64) -> dict:
    init_embedding_table(conn)

    # "Already embedded" means embedded with the CURRENT provider's dimension.
    # Switching models (say MiniLM 384 -> a 1024-dim remote model) makes old rows not count, so a
    # plain `helicon embed` re-embeds everything with the new model (store_embedding
    # REPLACEs the stale row by cube_id).
    _k, _c, _m, _dim = _embed_provider()
    cur_dim = _dim if _k == "remote" else 384
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
    cur_dim = _dim if _k == "remote" else 384
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
    # Stable, and tie-broken on a real key. np.argsort defaults to quicksort,
    # which is NOT stable, so equal-scoring memories came back in an arbitrary
    # order that changed between identical runs — and near-duplicate cubes tie
    # constantly. A regression test cannot sit on top of a ranking that will not
    # reproduce itself. Sort by (-similarity, id): score first, id to break ties.
    order = sorted(range(len(ids)), key=lambda i: (-float(similarities[i]), ids[i]))
    top_indices = order[:limit * 2]

    cube_ids = [ids[i] for i in top_indices if similarities[i] >= threshold]
    if not cube_ids:
        return []

    placeholders = ",".join("?" for _ in cube_ids)
    rows = conn.execute(
        f"SELECT id, title, type, source, confidence, content, created_at, "
        f"metadata FROM helicon_cubes WHERE id IN ({placeholders})",
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
            # carried so ranking can tell what a memory is ABOUT, not just
            # which session produced it (see _subject_key)
            "metadata": r["metadata"] if "metadata" in r.keys() else None,
            "similarity": round(float(similarities[i]), 4),
        })
        if len(results) >= limit:
            break

    return results


def _norm_title(s: str) -> str:
    """Lowercase, collapse whitespace, drop edge punctuation. Deliberately not
    a stemmer: this is an EXACT-name signal, and fuzziness is what buried the
    memory in the first place."""
    import re
    return re.sub(r"\s+", " ", (s or "").strip().lower()).strip(" .:-—–")


def title_matches(conn: sqlite3.Connection, query: str,
                  limit: int = 2) -> list[str]:
    """Live memories whose TITLE is the query — exact, or the query followed by
    a qualifier ("Orchestrator Closeout" -> "Orchestrator Closeout - May 15,
    2026").

    Why this exists. Snapshot 21 'Orchestrator Closeout' lost all five baseline
    hits (overlap 0.0, live_overlap 0.0). The cube gc_417d8dc99346, titled
    "Orchestrator Closeout - May 15, 2026", review_status approved, merged_into
    NULL, was not in its own top-5 — a live memory whose title IS the query did
    not appear for that query. Measured on a copy of the real store: rank 10 on
    the FTS branch, absent from the semantic branch, buried under file-write
    events for a same-named artifact.

    Neither branch can fix this on its own. Cosine over 2.5k live memories does
    not distinguish a title from a mention, and bm25 rewards the many short
    near-duplicate rows that repeat the words. So the exact-name signal is its
    own branch, and it is a PIN rather than a weight: a weight can always be
    outvoted by a large enough flood of near-duplicates, which is precisely the
    failure being fixed.

    Capped at `limit` (2 by default) so a query can never be wholly hijacked by
    title matches, and ordered deterministically: exact before prefix, then
    confidence, then id.
    """
    q = _norm_title(query)
    if not q or len(q) < 4:
        return []
    rows = conn.execute(
        "SELECT id, title, confidence FROM helicon_cubes "
        "WHERE merged_into IS NULL "
        "AND review_status NOT IN ('killed', 'superseded') "
        "AND LOWER(title) LIKE ?",
        (f"{q}%",),
    ).fetchall()
    scored = []
    for r in rows:
        t = _norm_title(r["title"])
        if t == q:
            rank = 0
        elif t.startswith(q) and t[len(q):len(q) + 1] in (" ", "-", ":", ",", "—", "–"):
            rank = 1
        else:
            continue  # LIKE prefix caught a longer word ("closeouts"), not the name
        scored.append((rank, -(r["confidence"] or 0), r["id"]))
    return [cid for _r, _c, cid in sorted(scored)][:limit]


def _subject_key(detail: dict) -> str:
    """What a memory is ABOUT, for diversity purposes.

    source_ref is the wrong key: the five hits that ate snapshot 21's entire
    top-5 carried four DIFFERENT source_refs (session_3d0e6a50, session_eedf16ac,
    session_7eb2a4c2, session_872514a3) while describing writes to one file,
    `closeout-2026-07-23-orchestrator.md`. Session identity is provenance, not
    subject. metadata.file_path is the artifact the memory is about.
    """
    meta = detail.get("metadata")
    if isinstance(meta, str):
        try:
            import json as _json
            meta = _json.loads(meta)
        except Exception:
            meta = None
    if isinstance(meta, dict) and meta.get("file_path"):
        return "file:" + os.path.basename(str(meta["file_path"])).lower()
    return "cube:" + str(detail.get("id"))


def diversify(details: list[dict], limit: int, per_subject_cap: int = 1,
              overflow_fill: bool = False) -> list[dict]:
    """At most `per_subject_cap` hits per subject inside the top-K.

    An agent's context budget is the scarce resource being allocated. Three of
    five slots — five of five once the semantic branch was unavailable — went to
    file-write events for a single artifact, ingested within four minutes of
    each other with distinct content hashes, so dedup by hash could never catch
    them. That is 60-100% of a top-5 context window spent re-reading one file.

    `overflow_fill=False` is deliberate and is the argument this function makes:
    a second copy of an artifact already in the window is not recall, it is
    redundancy, and padding an unfilled slot with one buys nothing. So the cap
    is hard and the result may be SHORTER than `limit`. Returning four distinct
    memories beats returning five where the fifth repeats the third.

    The measurement that settled it, on a copy of the real 48 MB store: the hard
    cap scores the same P@3 0.615 / MRR 0.577 as the padded version and returns
    strictly fewer redundant rows. Callers that genuinely need exactly `limit`
    rows can pass overflow_fill=True.
    """
    picked, overflow, seen = [], [], {}
    for d in details:
        key = _subject_key(d)
        if seen.get(key, 0) < per_subject_cap:
            seen[key] = seen.get(key, 0) + 1
            picked.append(d)
        else:
            overflow.append(d)
        if len(picked) >= limit:
            break
    if overflow_fill and len(picked) < limit:
        picked.extend(overflow[: limit - len(picked)])
    return picked[:limit]


def apply_context_policy(conn: sqlite3.Connection, query: str,
                         hits: list[dict], limit: int,
                         per_subject_cap: int = 1,
                         pin_title_matches: bool = True) -> list[dict]:
    """How an agent's context budget is spent — one policy, every branch.

    Order is deliberate: PIN first (the memory the query names cannot be
    outvoted), then DIVERSIFY (nothing may spend the rest of the window on
    copies of one artifact). Both run after the fused ranking, so no later
    stage can re-flood the window.

    This lives outside hybrid_search because retrieval has two branches and the
    policy must hold on both. snapshots._retrieve falls back to plain FTS
    whenever nothing is embedded, and that fallback is exactly the state a
    store is in before its first `helicon embed` — the moment a new user's
    ranking matters most.
    """
    out = list(hits)
    if pin_title_matches:
        pins = title_matches(conn, query, limit=max(1, limit // 3))
        have = {d["id"]: d for d in out}
        pinned = []
        for cid in pins:
            if cid in have:
                pinned.append(have[cid])
                continue
            row = conn.execute(
                "SELECT id, title, type, source, confidence, content, "
                "created_at, metadata FROM helicon_cubes WHERE id = ?",
                (cid,)).fetchone()
            if row is None:
                continue
            pinned.append({
                "id": row["id"], "title": row["title"], "type": row["type"],
                "source": row["source"], "confidence": row["confidence"],
                "content": (row["content"] or "")[:300],
                "created_at": row["created_at"], "metadata": row["metadata"],
                "semantic_score": None, "fts_rank": None,
                "hybrid_score": None, "title_pin": True,
            })
        if pinned:
            pin_ids = {d["id"] for d in pinned}
            out = pinned + [d for d in out if d["id"] not in pin_ids]

    if per_subject_cap:
        out = diversify(out, limit, per_subject_cap=per_subject_cap)
    return out[:limit]


def semantic_health(conn: sqlite3.Connection) -> dict:
    """Whether the semantic half of hybrid search can contribute AT ALL.

    Found by probing rather than trusting. `_load_all_embeddings` filters `ce.dim = <current provider dim>`,
    and on a mismatch it returns an empty list, `semantic_search` returns [],
    and `hybrid_search` quietly becomes FTS-only. No error is raised, no
    warning is printed, and the caller's answer has exactly the same shape.

    Measured on a copy of the real store: all 4,214 stored vectors are dim=1024
    (a remote embedding model), so with config.json absent — the fresh-clone and
    cloud-VM case this repo's own AGENTS.md sets up — the provider resolves to
    local/384, the filter matches zero rows, and 60% of the documented ranking
    signal is silently gone. "60% semantic / 40% FTS5" then describes something
    the code is not doing.
    """
    init_embedding_table(conn)
    _k, _c, model, dim = _embed_provider()
    cur_dim = dim if _k == "remote" else 384
    stored = {r["dim"]: r["c"] for r in conn.execute(
        "SELECT dim, COUNT(*) c FROM cube_embeddings GROUP BY dim")}
    usable = conn.execute(
        "SELECT COUNT(*) FROM cube_embeddings ce JOIN helicon_cubes gc "
        "ON ce.cube_id = gc.id WHERE gc.merged_into IS NULL "
        "AND gc.review_status IN ('approved', 'pending') AND ce.dim = ?",
        (cur_dim,)).fetchone()[0]
    if usable:
        return {"ok": True, "usable": usable, "provider_dim": cur_dim,
                "stored_dims": stored,
                "reason": f"{usable} live memories embedded at dim {cur_dim} "
                          f"({model})"}
    if not stored:
        return {"ok": False, "usable": 0, "provider_dim": cur_dim,
                "stored_dims": stored,
                "reason": "no embeddings stored — run: helicon embed. Retrieval "
                          "is FTS-only until then"}
    return {"ok": False, "usable": 0, "provider_dim": cur_dim,
            "stored_dims": stored,
            "reason": f"DIMENSION MISMATCH: provider is {model} (dim {cur_dim}) "
                      f"but stored vectors are {stored}. Every semantic query "
                      f"returns nothing and hybrid search silently degrades to "
                      f"FTS-only. Re-embed (helicon embed) or restore the "
                      f"provider that wrote them"}


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    semantic_weight: float = 0.6,
    fts_weight: float = 0.4,
    per_subject_cap: int = 1,
    pin_title_matches: bool = True,
) -> list[dict]:
    from helicon.db import search_cubes

    sem_results = semantic_search(conn, query, limit=limit * 2)
    try:
        fts_results = search_cubes(conn, query, limit * 2)
    except Exception:
        fts_results = []

    scores = {}
    details = {}

    # Reciprocal Rank Fusion (Cormack et al., SIGIR 2009): fuse the two ranked
    # lists by RANK, not raw score, so semantic cosine and FTS relevance stop
    # fighting over incomparable scales. k=60 is the standard constant; the
    # weights let one signal count more without re-introducing scale bias.
    RRF_K = 60
    for rank, r in enumerate(sem_results):
        cid = r["id"]
        scores[cid] = scores.get(cid, 0) + semantic_weight / (RRF_K + rank)
        details[cid] = {
            "id": cid, "title": r["title"], "type": r["type"],
            "source": r["source"], "confidence": r["confidence"],
            "content": r["content"], "created_at": r["created_at"],
            "metadata": r.get("metadata"),
            "semantic_score": r["similarity"], "fts_rank": None,
        }

    for rank, r in enumerate(fts_results):
        cid = r["id"]
        scores[cid] = scores.get(cid, 0) + fts_weight / (RRF_K + rank)
        if cid not in details:
            details[cid] = {
                "id": cid, "title": r["title"], "type": r["type"],
                "source": r["source"], "confidence": r["confidence"],
                "content": (r["content"] or "")[:300],
                "created_at": r["created_at"] if "created_at" in r.keys() else "",
                "metadata": r.get("metadata"),
                "semantic_score": None, "fts_rank": rank,
            }
        else:
            details[cid]["fts_rank"] = rank
            if details[cid].get("metadata") is None:
                details[cid]["metadata"] = r.get("metadata")

    # Same reason: fuse deterministically. `key=score, reverse=True` left ties
    # in whatever order the two source lists happened to populate the dict.
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    # One stage. There is no reranker: the fused order is the order, so the
    # same query over the same store returns the same ranking every time.
    out = [{**details[cid], "hybrid_score": round(score, 4)}
           for cid, score in ranked]

    return apply_context_policy(conn, query, out, limit,
                               per_subject_cap=per_subject_cap,
                               pin_title_matches=pin_title_matches)


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
