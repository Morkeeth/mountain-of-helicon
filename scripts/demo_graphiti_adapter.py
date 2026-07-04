"""Demo: read a Graphiti temporal knowledge graph through the graphiti connector.

End-to-end, zero fake data:

  1. Start a disposable Neo4j 5 container (Graphiti's default backend).
  2. Seed it with Graphiti-schema edges ((:Entity)-[:RELATES_TO]->(:Entity))
     whose facts are REAL sections of this repo's own CLAUDE.md, with
     valid_at taken from the file's actual git history. Sections that
     existed in the first committed CLAUDE.md but are gone from HEAD are
     seeded as genuinely invalidated edges (invalid_at = last edit date).
  3. Run helicon.connectors.graphiti.scan() against it and print the
     retrieved ConnectorResults, bi-temporal metadata included.
  4. Remove the container.

Degrades honestly: no docker -> says so and exits; nothing is simulated.

Run:  python3 scripts/demo_graphiti_adapter.py
      python3 scripts/demo_graphiti_adapter.py --keep   (leave container up)
"""
import os
import shutil
import subprocess
import sys
import time
import uuid as uuidlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helicon.connectors import graphiti
from helicon.connectors.agent_rules import _split_sections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTAINER = "helicon-neo4j"
BOLT_URI = "bolt://localhost:7687"
AUTH = ("neo4j", "heliconpass")
GROUP_ID = "helicon-demo"


def banner(msg):
    print(f"\n{'='*66}\n{msg}\n{'='*66}")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def git_out(args):
    proc = sh(["git", *args], cwd=REPO)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def real_edges_from_claude_md():
    """Build Graphiti-schema edges from the repo's own CLAUDE.md + git history."""
    path = os.path.join(REPO, "CLAUDE.md")
    with open(path, encoding="utf-8") as f:
        head_text = f.read()
    head_sections = dict(_split_sections(head_text))

    last_edit = git_out(["log", "-1", "--format=%cI", "--", "CLAUDE.md"])
    first_commit = git_out(["log", "--format=%H %cI", "--follow", "--", "CLAUDE.md"]
                           ).splitlines()
    first_hash, first_date = (first_commit[-1].split(" ", 1)
                              if first_commit else ("", last_edit))

    edges = []
    for heading, body in head_sections.items():
        edges.append({
            "uuid": str(uuidlib.uuid4()),
            "name": "DOCUMENTS",
            "fact": f"CLAUDE.md '{heading}': {body[:300]}",
            "source": "Mount Helicon",
            "target": heading,
            "created_at": last_edit,
            "valid_at": last_edit,
            "invalid_at": None,
            "expired_at": None,
            "episodes": [f"git:CLAUDE.md@HEAD"],
        })

    # Sections in the FIRST committed CLAUDE.md that no longer exist in HEAD
    # are real invalidated memory: true once, removed at the last edit.
    if first_hash:
        old_text = git_out(["show", f"{first_hash}:CLAUDE.md"])
        if old_text:
            for heading, body in _split_sections(old_text):
                if heading not in head_sections:
                    edges.append({
                        "uuid": str(uuidlib.uuid4()),
                        "name": "DOCUMENTED",
                        "fact": f"CLAUDE.md '{heading}' (removed): {body[:300]}",
                        "source": "Mount Helicon",
                        "target": heading,
                        "created_at": first_date,
                        "valid_at": first_date,
                        "invalid_at": last_edit,
                        "expired_at": last_edit,
                        "episodes": [f"git:CLAUDE.md@{first_hash[:10]}"],
                    })
    return edges


def wait_for_bolt(timeout=120):
    from neo4j import GraphDatabase
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with GraphDatabase.driver(BOLT_URI, auth=AUTH) as d:
                d.verify_connectivity()
            return True
        except Exception:
            time.sleep(2)
    return False


def main():
    keep = "--keep" in sys.argv

    docker = shutil.which("docker")
    if not docker:
        print("docker not found on PATH — cannot run the live Graphiti demo.")
        print("Install Docker (or start OrbStack once so its CLI installs), then re-run.")
        print("Nothing was simulated; exiting.")
        return 0

    try:
        import neo4j  # noqa: F401
    except ImportError:
        print("neo4j driver not installed — pip install neo4j, then re-run.")
        return 0

    banner(f"1. START Neo4j 5 container ({CONTAINER})")
    sh([docker, "rm", "-f", CONTAINER])  # idempotent
    proc = sh([docker, "run", "-d", "--name", CONTAINER,
               "-p", "7687:7687", "-p", "7474:7474",
               "-e", f"NEO4J_AUTH={AUTH[0]}/{AUTH[1]}", "neo4j:5"])
    if proc.returncode != 0:
        print(f"docker run failed: {proc.stderr.strip()}")
        return 1
    print(f"   container {proc.stdout.strip()[:12]} — waiting for bolt...")
    if not wait_for_bolt():
        print("   Neo4j never came up; cleaning up.")
        sh([docker, "rm", "-f", CONTAINER])
        return 1
    print("   bolt is up")

    banner("2. SEED Graphiti-schema edges from this repo's REAL CLAUDE.md")
    edges = real_edges_from_claude_md()
    live = [e for e in edges if not e["invalid_at"]]
    dead = [e for e in edges if e["invalid_at"]]
    print(f"   {len(live)} live sections, {len(dead)} genuinely-removed sections")

    from neo4j import GraphDatabase
    with GraphDatabase.driver(BOLT_URI, auth=AUTH) as driver:
        with driver.session() as session:
            for e in edges:
                session.run(
                    """
                    MERGE (a:Entity {name: $source})
                      ON CREATE SET a.uuid = randomUUID(), a.group_id = $group_id
                    MERGE (b:Entity {name: $target})
                      ON CREATE SET b.uuid = randomUUID(), b.group_id = $group_id
                    MERGE (a)-[r:RELATES_TO {uuid: $uuid}]->(b)
                    SET r.name = $name, r.fact = $fact, r.group_id = $group_id,
                        r.created_at = datetime($created_at),
                        r.valid_at = datetime($valid_at),
                        r.invalid_at = CASE WHEN $invalid_at IS NULL THEN NULL
                                            ELSE datetime($invalid_at) END,
                        r.expired_at = CASE WHEN $expired_at IS NULL THEN NULL
                                            ELSE datetime($expired_at) END,
                        r.episodes = $episodes
                    """,
                    group_id=GROUP_ID, **e,
                )
    print(f"   seeded {len(edges)} RELATES_TO edges")

    banner("3. RUN helicon.connectors.graphiti.scan() against the live graph")
    results = graphiti.scan({
        "uri": BOLT_URI, "user": AUTH[0], "password": AUTH[1],
        "group_id": GROUP_ID,
    })
    print(f"   retrieved {len(results)} ConnectorResults\n")
    for r in results:
        flag = " [INVALIDATED]" if "invalidated" in r.tags else ""
        print(f"   - {r.title}{flag}")
        print(f"       created_at={r.created_at}")
        print(f"       valid_at={r.metadata['valid_at'] or '-'}  "
              f"invalid_at={r.metadata['invalid_at'] or '-'}  "
              f"expired_at={r.metadata['expired_at'] or '-'}")
        print(f"       episodes={r.metadata['episodes']}")
        print(f"       {r.content[:100]}...")

    if keep:
        banner(f"DONE — container {CONTAINER} left running (--keep)")
    else:
        banner("4. CLEAN UP")
        sh([docker, "rm", "-f", CONTAINER])
        print(f"   removed {CONTAINER}")

    invalidated = sum(1 for r in results if "invalidated" in r.tags)
    print(f"\n-> {len(results)} facts pulled through the adapter, "
          f"{invalidated} carrying real invalid_at timestamps for the "
          f"battery's Freshness tests.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
