"""The measurement bench — instruments for your own agent stack."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from helicon import measure, science, store_truth


def run(config: dict, *, weeks: int = 12) -> str:
    from helicon.db import init_db

    db_path = config["db_path"]
    conn = init_db(db_path)
    measure.ensure_schema(conn)

    parts = [
        "#" * 72,
        "# THE MEASUREMENT BENCH — instruments for your own agent stack",
        "#" * 72,
        "",
        science.run(config).strip(),
        "",
        measure.render_series(measure.series(conn, weeks=weeks)).strip(),
        "",
        store_truth.render(conn, db_path).strip(),
        "",
        "Reproduce: helicon measurement-bench",
    ]
    return "\n".join(parts)


def run_json(config: dict, *, weeks: int = 12) -> dict:
    """Structured witness for Firestore / ADK — numbers from probes only."""
    from helicon.db import init_db

    db_path = config["db_path"]
    conn = init_db(db_path)
    measure.ensure_schema(conn)

    return {
        "repro_command": "helicon measurement-bench --json",
        "store_path": db_path,
        "recorded_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(
            timespec="seconds"),
        "science": science.collect(conn, config, db_path),
        "measure": measure.series(conn, weeks=weeks),
        "store_truth": {"findings": store_truth.findings(conn)},
    }


def run_json_text(config: dict, *, weeks: int = 12) -> str:
    return json.dumps(run_json(config, weeks=weeks), indent=2)
