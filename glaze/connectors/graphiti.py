"""Graphiti connector — temporal knowledge-graph edges as memory cubes.

Graphiti (getzep/graphiti) stores facts as RELATES_TO edges between Entity
nodes, each edge carrying Graphiti's bi-temporal model:

  - created_at / expired_at : when the fact entered / left the GRAPH
  - valid_at / invalid_at   : when the fact was true / stopped being true
                              in the WORLD

That bi-temporal data is exactly what Helicon's battery needs: an edge with
invalid_at or expired_at set is memory the graph itself has marked stale,
so it gets the `invalidated` tag and the full temporal fields ride along in
metadata for the Freshness/staleness tests downstream.

Talks bolt via the neo4j Python driver, so it works against Neo4j and
against FalkorDB's bolt endpoint alike. The driver is imported lazily:
missing dep -> install hint + [], never a crashed scan.

Opt-in: no `uri` in config -> return [] silently.
Config: {"uri", "user", "password", "group_id" (optional), "limit" (optional)}
"""
from glaze.models import ConnectorResult

EDGE_QUERY = """
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE $group_id IS NULL OR r.group_id = $group_id
RETURN r.uuid AS uuid,
       r.name AS name,
       r.fact AS fact,
       r.group_id AS group_id,
       r.created_at AS created_at,
       r.valid_at AS valid_at,
       r.invalid_at AS invalid_at,
       r.expired_at AS expired_at,
       r.episodes AS episodes,
       a.name AS source_entity,
       b.name AS target_entity
ORDER BY r.created_at
LIMIT $limit
"""


def _iso(value) -> str:
    """Neo4j temporal types / datetimes / strings -> ISO string ('' for None)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for attr in ("iso_format", "isoformat"):
        fn = getattr(value, attr, None)
        if callable(fn):
            return fn()
    return str(value)


def scan(config: dict) -> list[ConnectorResult]:
    uri = config.get("uri", "")
    if not uri:
        return []

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("  [!] graphiti: neo4j driver not installed — pip install neo4j")
        return []

    user = config.get("user", "neo4j")
    password = config.get("password", "")
    group_id = config.get("group_id") or None
    limit = config.get("limit", 1000)
    database = config.get("database")  # neo4j driver picks default if None

    results = []
    try:
        with GraphDatabase.driver(uri, auth=(user, password)) as driver:
            with driver.session(database=database) as session:
                records = session.run(EDGE_QUERY, group_id=group_id, limit=limit)
                for rec in records:
                    fact = rec.get("fact") or ""
                    if not fact.strip():
                        continue

                    created_at = _iso(rec.get("created_at"))
                    valid_at = _iso(rec.get("valid_at"))
                    invalid_at = _iso(rec.get("invalid_at"))
                    expired_at = _iso(rec.get("expired_at"))

                    tags = ["graphiti"]
                    if invalid_at or expired_at:
                        tags.append("invalidated")

                    name = rec.get("name") or ""
                    title = name or (fact[:60] + "…" if len(fact) > 60 else fact)

                    results.append(ConnectorResult(
                        source="graphiti",
                        source_ref=f"graphiti/{rec.get('uuid') or 'edge'}",
                        type="graph_fact",
                        title=title,
                        content=fact[:2000],
                        created_at=valid_at or created_at,
                        tags=tags,
                        metadata={
                            "uuid": rec.get("uuid"),
                            "edge_name": name,
                            "group_id": rec.get("group_id"),
                            "created_at": created_at,
                            "valid_at": valid_at,
                            "invalid_at": invalid_at,
                            "expired_at": expired_at,
                            "episodes": list(rec.get("episodes") or []),
                            "source_entity": rec.get("source_entity"),
                            "target_entity": rec.get("target_entity"),
                        },
                    ))
    except Exception as e:
        print(f"  [!] graphiti: could not read graph at {uri}: {e}")
        return []

    return results
