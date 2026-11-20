"""Firestore witness store — optional; skipped when GOOGLE_CLOUD_PROJECT unset."""
from __future__ import annotations

import os
from typing import Any


def project_id() -> str | None:
    return os.environ.get("GOOGLE_CLOUD_PROJECT") or None


def write_run(run_id: str, doc: dict[str, Any]) -> None:
    pid = project_id()
    if not pid:
        return
    from google.cloud import firestore

    client = firestore.Client(project=pid)
    client.collection("runs").document(run_id).set(doc)


def latest_run() -> dict[str, Any] | None:
    pid = project_id()
    if not pid:
        return None
    from google.cloud import firestore

    client = firestore.Client(project=pid)
    docs = (
        client.collection("runs")
        .order_by("finished_at", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    for snap in docs:
        data = snap.to_dict() or {}
        data.setdefault("run_id", snap.id)
        return data
    return None
