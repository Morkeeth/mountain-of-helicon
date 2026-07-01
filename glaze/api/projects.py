from fastapi import APIRouter

from glaze.api.app import get_conn, get_config

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def project_rollup():
    from glaze.projects import get_project_rollup
    conn = get_conn()
    return {"projects": get_project_rollup(conn)}


@router.get("/recommend")
async def project_recommend():
    from glaze.projects import get_recommendations, get_weekly_summary
    conn = get_conn()
    config = get_config()
    return {
        "recommendations": get_recommendations(conn, config),
        "weekly": get_weekly_summary(conn),
    }


@router.get("/weekly")
async def weekly_summary():
    from glaze.projects import get_weekly_summary
    conn = get_conn()
    return get_weekly_summary(conn)


@router.get("/context-switches")
async def context_switches(weeks: int = 4):
    from glaze.projects import get_context_switches
    conn = get_conn()
    return get_context_switches(conn, weeks)
