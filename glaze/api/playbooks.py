from fastapi import APIRouter

from glaze.api.app import get_conn
from glaze.playbooks import build_playbooks, get_playbooks, get_playbook_for_task
from glaze.context_impact import compute_context_impact, get_memory_usefulness
from glaze.compiler import compile_core_memory, compile_all_skills, compile_claude_md_patch, write_compiled_files
from glaze.utility import get_utility_stats
from glaze.embeddings import embed_all_cubes, semantic_search, hybrid_search, get_embedding_stats

router = APIRouter()


@router.get("/playbooks")
async def list_playbooks():
    conn = get_conn()
    playbooks = get_playbooks(conn)
    if not playbooks:
        playbooks = build_playbooks(conn)
    return {"playbooks": playbooks}


@router.post("/playbooks/build")
async def rebuild_playbooks():
    conn = get_conn()
    return {"playbooks": build_playbooks(conn)}


@router.get("/playbooks/match")
async def match_playbook(task: str = ""):
    conn = get_conn()
    result = get_playbook_for_task(conn, task)
    if result:
        return result
    return {"error": "No matching playbook found", "task": task}


@router.get("/context/impact")
async def context_impact():
    conn = get_conn()
    return compute_context_impact(conn)


@router.get("/context/impact/{cube_id}")
async def memory_usefulness(cube_id: str):
    conn = get_conn()
    return get_memory_usefulness(conn, cube_id)


@router.get("/utility")
async def utility_stats():
    conn = get_conn()
    return get_utility_stats(conn)


@router.get("/compiler/core-memory")
async def get_core_memory():
    conn = get_conn()
    return {"content": compile_core_memory(conn)}


@router.get("/compiler/skills")
async def get_compiled_skills():
    conn = get_conn()
    return {"skills": compile_all_skills(conn)}


@router.get("/compiler/claude-md")
async def get_claude_md_patch():
    conn = get_conn()
    return {"content": compile_claude_md_patch(conn)}


@router.post("/compiler/write")
async def write_compiled(output_dir: str = "data/compiled"):
    conn = get_conn()
    return write_compiled_files(conn, output_dir)


@router.get("/embeddings/stats")
async def embedding_stats():
    conn = get_conn()
    return get_embedding_stats(conn)


@router.post("/embeddings/build")
async def build_embeddings():
    conn = get_conn()
    return embed_all_cubes(conn)


@router.get("/embeddings/search")
async def search_embeddings(query: str, limit: int = 10):
    conn = get_conn()
    return {"results": hybrid_search(conn, query, limit=limit)}
