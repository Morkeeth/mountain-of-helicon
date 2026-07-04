"""Mem0 connector — memories from the store Alibaba itself recommends.

Alibaba Cloud documents three memory backends for Qwen agents: Model Studio
Memory Bank, Mem0 + Hologres, and Mem0 + AnalyticDB. This read-side adapter
lets Mount Helicon audit all the Mem0-shaped ones: pull every memory for a
user and hand it to the same battery/snapshot/reconcile machinery as any
other source. We audit; the store keeps the write path.

Two access modes, both lazy so a missing dep or key never crashes a scan:

  - platform: {"api_key": "...", "user_id": "..."} — Mem0 Platform REST
    (GET /v1/memories/ with Token auth, stdlib urllib, no SDK needed)
  - local OSS: {"local": true, "user_id": "..."} — `from mem0 import Memory`,
    Memory().get_all(user_id=...)

Mem0 memories carry created_at / updated_at, and the platform adds an
optional expiration_date. updated_at != created_at means the fact was
REWRITTEN — that plus expiry rides along in metadata for the freshness
tests, the same way Graphiti's bi-temporal fields do.

Opt-in: neither "api_key" nor "local" in config -> return [] silently.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from helicon.models import ConnectorResult

PLATFORM_URL = "https://api.mem0.ai/v1/memories/"


def _fetch_platform(api_key: str, user_id: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode({"user_id": user_id, "page_size": min(limit, 100)})
    req = urllib.request.Request(
        f"{PLATFORM_URL}?{params}",
        headers={"Authorization": f"Token {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    # v1 returns either a bare list or {"results": [...]} depending on plan
    items = data.get("results", data) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def _fetch_local(user_id: str, limit: int) -> list[dict]:
    from mem0 import Memory
    data = Memory().get_all(user_id=user_id, limit=limit)
    items = data.get("results", data) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def _to_result(item: dict, user_id: str) -> ConnectorResult | None:
    text = (item.get("memory") or item.get("text") or "").strip()
    if not text:
        return None
    mem_id = str(item.get("id", ""))
    created = item.get("created_at") or ""
    updated = item.get("updated_at") or ""
    expiration = item.get("expiration_date") or ""
    categories = item.get("categories") or []

    tags = ["mem0"] + [str(c).lower() for c in categories]
    if updated and created and updated != created:
        tags.append("rewritten")
    if expiration:
        tags.append("expiring")

    return ConnectorResult(
        source="mem0",
        source_ref=f"mem0/{user_id}/{mem_id}",
        type="mem0_memory",
        title=text[:80],
        content=text[:2000],
        created_at=created,
        tags=tags,
        metadata={
            "mem0_id": mem_id,
            "user_id": user_id,
            "created_at": created,
            "updated_at": updated,
            "expiration_date": expiration,
            "categories": categories,
        },
    )


def scan(config: dict) -> list[ConnectorResult]:
    api_key = config.get("api_key", "")
    local = bool(config.get("local"))
    if not api_key and not local:
        return []

    user_id = config.get("user_id", "default")
    limit = config.get("limit", 1000)

    try:
        if api_key:
            items = _fetch_platform(api_key, user_id, limit)
        else:
            items = _fetch_local(user_id, limit)
    except ImportError:
        print("  [!] mem0: SDK not installed — pip install mem0ai (or use api_key mode)")
        return []
    except urllib.error.HTTPError as e:
        print(f"  [!] mem0: platform API {e.code} — check api_key/user_id")
        return []
    except Exception as e:
        print(f"  [!] mem0: {e}")
        return []

    results = []
    for item in items:
        r = _to_result(item, user_id)
        if r:
            results.append(r)
    return results
